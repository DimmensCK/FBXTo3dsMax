/*
FBXTo3dsMax v1.4.24 可恢复卸载器。

插件文件不会被永久删除；已验证的插件包、MacroScript 与图标会移动到
ApplicationPlugins 扫描路径之外的时间戳归档。
*/

global F2M_TopologyHelper
global F2M_SkinHelper
global F2M_Helper

(
    local fileClass = dotNetClass "System.IO.File"
    local directoryClass = dotNetClass "System.IO.Directory"
    local pathClass = dotNetClass "System.IO.Path"
    local guidClass = dotNetClass "System.Guid"
    local bitConverter = dotNetClass "System.BitConverter"
    local shaClass = dotNetClass "System.Security.Cryptography.SHA256"
    local movedFiles = #()
    local rollbackWarnings = #()
    local runtimeCleanupAttempted = false
    local runtimeWasStopped = false
    local packageMutationLock = undefined
    local finalDialogTitle = ""
    local finalDialogText = ""

    -- Display preference only; no license or 3ds Max configuration is changed.
    local displayEnglish = false
    try
    (
        local displayEnvironment = dotNetClass "System.Environment"
        local selectedLanguage = displayEnvironment.GetEnvironmentVariable "F2M_LANGUAGE"
        if selectedLanguage != "en" and selectedLanguage != "zh-CN" do
        (
            local localData = displayEnvironment.GetEnvironmentVariable "LOCALAPPDATA"
            if localData != undefined and localData != "" do
            (
                local preferencePath = pathClass.Combine localData "FBXTo3dsMax\\language.txt"
                if fileClass.Exists preferencePath do
                    selectedLanguage = trimRight (trimLeft (fileClass.ReadAllText preferencePath))
            )
        )
        displayEnglish = selectedLanguage == "en"
    )
    catch (displayEnglish = false)
    fn localized chineseText englishText =
    (
        if displayEnglish then englishText else chineseText
    )


    fn joinPath basePath childPath =
    (
        pathClass.GetFullPath (pathClass.Combine basePath childPath)
    )

    fn uniqueToken =
    (
        substituteString ((guidClass.NewGuid()).ToString()) "-" ""
    )

    fn ensureDirectory directoryPath =
    (
        if not directoryClass.Exists directoryPath do directoryClass.CreateDirectory directoryPath
        directoryClass.Exists directoryPath
    )

    fn acquirePackageMutationLock workRoot =
    (
        local lockDirectory = joinPath workRoot "Locks"
        if not (ensureDirectory lockDirectory) do
            throw ("无法准备安装互斥目录：" + lockDirectory)
        local lockPath = joinPath lockDirectory "package.lock"
        local fileMode = dotNetClass "System.IO.FileMode"
        local fileAccess = dotNetClass "System.IO.FileAccess"
        local fileShare = dotNetClass "System.IO.FileShare"
        local lockError = ""
        try
        (
            packageMutationLock = fileClass.Open lockPath fileMode.OpenOrCreate fileAccess.ReadWrite fileShare.None
        )
        catch
        (
            packageMutationLock = undefined
            lockError = getCurrentException()
        )
        if lockError != "" do
            throw "另一个 FBXTo3dsMax 安装或卸载事务正在运行。为避免插件目录损坏，本次卸载已取消；请等待前一次操作结束后重试。"
        if packageMutationLock == undefined do
            throw "无法取得 FBXTo3dsMax 安装互斥锁，本次卸载已取消。"
        true
    )

    fn releasePackageMutationLock =
    (
        if packageMutationLock != undefined do
        (
            try(packageMutationLock.Close())catch()
            try(packageMutationLock.Dispose())catch()
            packageMutationLock = undefined
        )
        true
    )

    fn sha256File filePath =
    (
        local stream = undefined
        local sha = undefined
        local result = ""
        if not fileClass.Exists filePath do return ""

        try
        (
            stream = fileClass.OpenRead filePath
            sha = shaClass.Create()
            result = bitConverter.ToString (sha.ComputeHash stream)
            result = substituteString result "-" ""
        )
        catch(result = "")

        try(if stream != undefined do stream.Close())catch()
        try(if sha != undefined do sha.Dispose())catch()
        result
    )

    fn textContainsAll filePath tokens =
    (
        if not fileClass.Exists filePath do return false
        local content = ""
        try(content = toLower (fileClass.ReadAllText filePath))catch(return false)
        for token in tokens where findString content (toLower token) == undefined do return false
        true
    )

    fn moveVerifiedFile originalPath archivePath tokens =
    (
        if not fileClass.Exists originalPath do return false
        if not textContainsAll originalPath tokens do
        (
            throw ("拒绝归档无法确认归属的文件：" + originalPath)
        )

        ensureDirectory (pathClass.GetDirectoryName archivePath)
        if fileClass.Exists archivePath do throw ("归档路径发生冲突：" + archivePath)

        local expectedHash = sha256File originalPath
        if expectedHash == "" do throw ("无法计算文件哈希：" + originalPath)
        fileClass.Move originalPath archivePath

        if sha256File archivePath != expectedHash do
        (
            if (fileClass.Exists archivePath) and (not (fileClass.Exists originalPath)) do fileClass.Move archivePath originalPath
            throw ("文件归档后的哈希不一致：" + originalPath)
        )

        append movedFiles #(originalPath, archivePath, expectedHash)
        true
    )

    fn restoreMovedFiles =
    (
        for i = movedFiles.count to 1 by -1 do
        (
            local originalPath = movedFiles[i][1]
            local archivePath = movedFiles[i][2]
            local expectedHash = movedFiles[i][3]
            try
            (
                if fileClass.Exists archivePath do
                (
                    ensureDirectory (pathClass.GetDirectoryName originalPath)
                    if fileClass.Exists originalPath and
                       sha256File originalPath != expectedHash do
                    (
                        -- 失败回滚已重新启动 Bootstrap 时，它可能先重建模板
                        -- Macro/Icon。先把该可重建文件移入同一归档，再恢复
                        -- 卸载前的精确字节，避免用户修改被模板占位。
                        local regeneratedPath = archivePath + ".rollback-generated"
                        if fileClass.Exists regeneratedPath do
                            throw ("回滚重建文件归档路径冲突：" + regeneratedPath)
                        fileClass.Move originalPath regeneratedPath
                    )
                    if not (fileClass.Exists originalPath) do
                        fileClass.Move archivePath originalPath
                    if sha256File originalPath != expectedHash do
                    (
                        append rollbackWarnings ("文件恢复后的哈希不一致：" + originalPath)
                    )
                )
            )
            catch
            (
                append rollbackWarnings ("无法恢复文件：" + originalPath + " | " + (getCurrentException()))
            )
        )
    )

    fn removeLiveRuntime =
    (
        local selfcheckStopError = ""
        local cleanupError = ""
        try
        (
            python.Execute "import builtins\n_f2m_controller = getattr(builtins, '_FBXTO3DSMAX_SELFCHECK_CONTROLLER', None)\nif _f2m_controller is not None:\n    _f2m_shutdown = getattr(_f2m_controller, 'shutdown', None)\n    if not callable(_f2m_shutdown):\n        raise RuntimeError('自检控制器缺少安全停止接口。')\n    _f2m_shutdown()\n    _f2m_is_running = getattr(_f2m_controller, 'is_running', None)\n    if callable(_f2m_is_running) and _f2m_is_running():\n        raise RuntimeError('自检子进程在停止后仍然运行。')\n    if getattr(builtins, '_FBXTO3DSMAX_SELFCHECK_CONTROLLER', None) is _f2m_controller:\n        delattr(builtins, '_FBXTO3DSMAX_SELFCHECK_CONTROLLER')\nfor _f2m_cleanup_name in ('_f2m_controller', '_f2m_shutdown', '_f2m_is_running', '_f2m_cleanup_name'):\n    globals().pop(_f2m_cleanup_name, None)\n" throwOnError:true clearUndoBuffer:false
            format "[FBXTo3dsMax 卸载器] 运行中的自检控制器已安全停止。\n"
        )
        catch
        (
            selfcheckStopError = getCurrentException()
        )
        if selfcheckStopError != "" do
        (
            format "[FBXTo3dsMax 卸载器] 错误：无法安全停止运行中的自检，卸载已阻止：%\n" selfcheckStopError
            throw ("无法安全停止运行中的自检，卸载已取消：" + selfcheckStopError)
        )
        try(callbacks.removeScripts id:#FBXTo3dsMax_Toolbar)catch()
        try
        (
            if ::FBXTo3dsMax_Bootstrap != undefined do ::FBXTo3dsMax_Bootstrap.shutdown()
        )
        catch()
        try(destroyDialog F2M_Transfer_Rollout)catch()
        try(destroyDialog FBXTo3dsMax_Rollout)catch()
        try(destroyDialog B2M_Transfer_Rollout)catch()
        try
        (
            python.Execute "import __main__, os, sys\n_f2m_pre_main = vars(__main__)\n_f2m_pre_b2m = _f2m_pre_main.get('b2m')\nif getattr(_f2m_pre_b2m, '__name__', None) in ('b2m_topology_transfer', 'b2m_skin_replace') and getattr(_f2m_pre_b2m, '__file__', None):\n    _f2m_pre_dir = os.path.normcase(os.path.abspath(os.path.dirname(_f2m_pre_b2m.__file__)))\n    sys.path[:] = [_f2m_pre_path for _f2m_pre_path in sys.path if not _f2m_pre_path or os.path.normcase(os.path.abspath(_f2m_pre_path)) != _f2m_pre_dir]\n    if isinstance(_f2m_pre_main.get('tool_dir'), str) and os.path.normcase(os.path.abspath(_f2m_pre_main['tool_dir'])) == _f2m_pre_dir:\n        _f2m_pre_main.pop('tool_dir', None)\n    _f2m_pre_main.pop('b2m', None)\nfor _f2m_pre_name in ('_f2m_pre_main', '_f2m_pre_b2m', '_f2m_pre_dir', '_f2m_pre_path', '_f2m_pre_name'):\n    globals().pop(_f2m_pre_name, None)\n" throwOnError:true clearUndoBuffer:false
            python.Execute "import __main__, builtins, os, sys\n_f2m_api = getattr(builtins, '_FBXTO3DSMAX_TOOLBAR_API', None)\nif _f2m_api:\n    _f2m_api.get('uninstall', lambda: 0)()\nif hasattr(builtins, '_FBXTO3DSMAX_TOOLBAR_API'):\n    delattr(builtins, '_FBXTO3DSMAX_TOOLBAR_API')\n_f2m_old_names = ('b2m_topology_transfer', 'b2m_skin_replace')\n_f2m_old_dirs = {os.path.normcase(os.path.abspath(os.path.dirname(getattr(sys.modules.get(_f2m_name), '__file__', '') or ''))) for _f2m_name in _f2m_old_names if getattr(sys.modules.get(_f2m_name), '__file__', None)}\n_f2m_known_modules = _f2m_old_names + ('f2m_i18n', 'f2m_report_i18n', '_fbx_to_3dsmax_i18n_runtime', '_f2m_report_i18n_runtime', 'f2m_topology_transfer', 'f2m_skin_replace', 'f2m_smoothing', 'f2m_fbx_metadata', 'f2m_selfcheck', 'f2m_test_fixtures', '_f2m_sc_fixture_integrity', '_f2m_sc_fixture_algorithm', '_f2m_sc_fixture_topology', '_fbx_to_3dsmax_toolbar_runtime', '_fbx_to_3dsmax_topology_runtime', '_fbx_to_3dsmax_skin_runtime', '_fbx_to_3dsmax_selfcheck_runtime', '_f2m_smoothing_runtime', '_f2m_fbx_metadata_runtime', '_f2m_sc_topology_integrity', '_f2m_sc_skin_integrity', '_f2m_sc_smoothing_integrity', '_f2m_sc_fbx_metadata_integrity', '_f2m_sc_smoothing_runtime', '_f2m_sc_fbx_metadata_runtime', '_f2m_sc_topology_procedural', '_f2m_sc_topology_fbx', '_f2m_sc_skin_fbx')\nfor _f2m_name in _f2m_known_modules:\n    sys.modules.pop(_f2m_name, None)\nif _f2m_old_dirs:\n    sys.path[:] = [_f2m_path for _f2m_path in sys.path if not _f2m_path or os.path.normcase(os.path.abspath(_f2m_path)) not in _f2m_old_dirs]\n_f2m_main = vars(__main__)\n_f2m_b2m = _f2m_main.get('b2m')\nif getattr(_f2m_b2m, '__name__', None) in _f2m_old_names:\n    _f2m_main.pop('b2m', None)\n_f2m_tool_dir = _f2m_main.get('tool_dir')\nif isinstance(_f2m_tool_dir, str) and _f2m_old_dirs and os.path.normcase(os.path.abspath(_f2m_tool_dir)) in _f2m_old_dirs:\n    _f2m_main.pop('tool_dir', None)\nfor _f2m_name in ('_f2m_module_path', '_f2m_module_name', '_f2m_spec', '_f2m_module', '__f2m_run_ok', '_f2m_sc_path', '_f2m_sc_name', '_f2m_sc_spec', '_f2m_sc', '_f2m_sc_result', '__f2m_sc_ok', '__f2m_sc_text', '__f2m_sc_report'):\n    _f2m_main.pop(_f2m_name, None)\nfor _f2m_cleanup_name in ('_f2m_api', '_f2m_old_names', '_f2m_old_dirs', '_f2m_known_modules', '_f2m_main', '_f2m_b2m', '_f2m_tool_dir', '_f2m_name', '_f2m_path', '_f2m_cleanup_name'):\n    globals().pop(_f2m_cleanup_name, None)\n" throwOnError:true clearUndoBuffer:false
            F2M_TopologyHelper = undefined
            F2M_SkinHelper = undefined
            F2M_Helper = undefined
            if F2M_TopologyHelper != undefined or
               F2M_SkinHelper != undefined or
               F2M_Helper != undefined do
                throw "无法清除旧版 MAXScript Helper 缓存。"
        )
        catch
        (
            cleanupError = getCurrentException()
        )
        if cleanupError != "" do
            throw ("无法完整清理插件运行模块，卸载已取消：" + cleanupError)
        true
    )

    local pluginBase = pathClass.GetFullPath (getDir #privateExchangeStoreInstallPath)
    local workRoot = joinPath pluginBase "..\\FBXTo3dsMaxInstaller"
    local packagePath = joinPath pluginBase "FBXTo3dsMax"
    local token = uniqueToken()
    local archiveRoot = joinPath workRoot ("UninstallBackups\\" + token)
    local packageArchive = joinPath archiveRoot "FBXTo3dsMax"
    local packageMoved = false

    try
    (
        acquirePackageMutationLock workRoot
        local packageXml = joinPath packagePath "PackageContents.xml"
        local versionPath = joinPath packagePath "contents\\FBXTo3dsMax.version"

        if directoryClass.Exists packagePath do
        (
            if (not (fileClass.Exists packageXml)) or (not (fileClass.Exists versionPath)) do
            (
                throw ("拒绝移动无法确认归属的插件目录：" + packagePath)
            )
            local xmlText = fileClass.ReadAllText packageXml
            local packageOwned = (findString xmlText "Name=\"FBXTo3dsMax\"" != undefined) and (findString xmlText "UpgradeCode=\"{B7AD0BB7-C64E-4F41-9767-CA72294639AE}\"" != undefined)
            if not packageOwned do
            (
                throw ("插件包缺少归属标记：" + packageXml)
            )
        )

        local userMacro = joinPath (getDir #userMacros) "FBXTo3dsMax-FBXTo3dsMax_Open.mcr"
        local deprecatedUserMacro = joinPath (getDir #userMacros) "FBXTo3dsMax.mcr"
        local lightIcon = joinPath (getDir #userIcons) "Light\\FBXTo3dsMax\\FBXTo3dsMax.svg"
        local darkIcon = joinPath (getDir #userIcons) "Dark\\FBXTo3dsMax\\FBXTo3dsMax.svg"
        local macroTokens = #("macroScript FBXTo3dsMax_Open", "category:\"FBXTo3dsMax\"")
        local iconTokens = #("<svg", "<title>FBXTo3dsMax</title>")

        if (fileClass.Exists userMacro) and (not (textContainsAll userMacro macroTokens)) do
        (
            throw ("拒绝归档无法确认归属的文件：" + userMacro)
        )
        if (fileClass.Exists deprecatedUserMacro) and (not (textContainsAll deprecatedUserMacro macroTokens)) do
        (
            throw ("拒绝归档无法确认归属的文件：" + deprecatedUserMacro)
        )
        if (fileClass.Exists lightIcon) and (not (textContainsAll lightIcon iconTokens)) do
        (
            throw ("拒绝归档无法确认归属的文件：" + lightIcon)
        )
        if (fileClass.Exists darkIcon) and (not (textContainsAll darkIcon iconTokens)) do
        (
            throw ("拒绝归档无法确认归属的文件：" + darkIcon)
        )

        -- 清理函数可能在已经移除回调/窗口后才因模块驱逐失败抛错。
        runtimeCleanupAttempted = true
        removeLiveRuntime()
        runtimeWasStopped = true
        ensureDirectory archiveRoot

        moveVerifiedFile userMacro (joinPath archiveRoot "UserMacros\\FBXTo3dsMax-FBXTo3dsMax_Open.mcr") macroTokens
        moveVerifiedFile deprecatedUserMacro (joinPath archiveRoot "UserMacros\\FBXTo3dsMax.mcr") macroTokens

        moveVerifiedFile lightIcon (joinPath archiveRoot "UserIcons\\Light\\FBXTo3dsMax.svg") iconTokens
        moveVerifiedFile darkIcon (joinPath archiveRoot "UserIcons\\Dark\\FBXTo3dsMax.svg") iconTokens

        if directoryClass.Exists packagePath do
        (
            directoryClass.Move packagePath packageArchive
            packageMoved = true

            local archivedVersion = joinPath packageArchive "contents\\FBXTo3dsMax.version"
            local archivedXml = joinPath packageArchive "PackageContents.xml"
            if (not (fileClass.Exists archivedVersion)) or (not (fileClass.Exists archivedXml)) do
            (
                throw "插件包归档读回失败。"
            )
        )

        local archiveManifest = joinPath archiveRoot "uninstall-archive.sha256"
        local stream = createFile archiveManifest
        if stream == undefined do throw ("无法创建卸载归档清单：" + archiveManifest)
        for record in movedFiles do format "%|%|%\n" record[1] record[2] record[3] to:stream
        if packageMoved do format "PACKAGE|%|%\n" packagePath packageArchive to:stream
        close stream
        stream = undefined

        finalDialogTitle = (localized "FBXTo3dsMax - 卸载完成" "FBXTo3dsMax - Uninstalled")
        finalDialogText = (
            (localized "FBXTo3dsMax 已从自动加载中移除。\n\n" "FBXTo3dsMax was removed from automatic loading.\n\n") +
            (localized "没有永久删除任何文件。可恢复归档位于：\n" "Files were archived for recovery at:\n") +
            archiveRoot +
            (localized "\n\n请重启 3ds Max，以清除当前会话中缓存的 MacroScript 动作。" "\n\nRestart 3ds Max to release cached MacroScript actions.")
        )
    )
    catch
    (
        local uninstallError = getCurrentException()
        local uninstallDiagnostic = joinPath archiveRoot "uninstall-error.txt"
        try
        (
            ensureDirectory archiveRoot
            fileClass.WriteAllText uninstallDiagnostic uninstallError
        )
        catch
        (
            uninstallDiagnostic = ""
        )

        try
        (
            if packageMoved and (directoryClass.Exists packageArchive) and (not (directoryClass.Exists packagePath)) do
            (
                directoryClass.Move packageArchive packagePath
                if (not (fileClass.Exists (joinPath packagePath "PackageContents.xml"))) or (not (fileClass.Exists (joinPath packagePath "contents\\FBXTo3dsMax.version"))) do
                (
                    append rollbackWarnings ("已恢复插件包的读回失败：" + packagePath)
                )
            )
        )
        catch
        (
            append rollbackWarnings ("无法恢复插件包：" + (getCurrentException()))
        )
        try
        (
            if runtimeCleanupAttempted do
            (
                local bootstrapPath = joinPath packagePath "contents\\FBXTo3dsMax_Bootstrap.ms"
                if fileClass.Exists bootstrapPath then
                (
                    if (fileIn bootstrapPath quiet:true) != true do
                    (
                        append rollbackWarnings ("已恢复插件包的启动引导没有返回成功状态：" + bootstrapPath)
                    )
                )
                else
                (
                    append rollbackWarnings ("已恢复插件包缺少启动引导：" + bootstrapPath)
                )
            )
        )
        catch
        (
            append rollbackWarnings ("无法重新启动已恢复的插件包：" + (getCurrentException()))
        )

        -- 启动引导会重建规范用户文件；随后恢复卸载前的精确字节，
        -- 确保卸载失败时不会丢弃用户修改。
        restoreMovedFiles()

        finalDialogTitle = (localized "FBXTo3dsMax - 卸载失败" "FBXTo3dsMax - Uninstall failed")
        finalDialogText = (
            (localized "FBXTo3dsMax 卸载失败，卸载器已尝试回滚。\n\n" "Uninstall failed; rollback was attempted.\n\n") +
            (if uninstallDiagnostic != "" then ((localized "内部诊断文件：\n" "Diagnostic file:\n") + uninstallDiagnostic) else (localized "内部诊断文件写入失败，请保留当前卸载归档。" "The diagnostic file could not be written. Preserve the uninstall archive.")) +
            (if rollbackWarnings.count > 0 then ((localized "\n\n警告：" "\n\nWarning: ") + (rollbackWarnings.count as string) + (localized " 项回滚检查失败。请保留归档，并在重试前检查相关路径。" " rollback checks failed. Preserve the archive and inspect the affected paths before retrying.")) else "")
        )
    )
    -- 先释放跨进程锁，再显示可能长期停留的结果对话框。
    releasePackageMutationLock()
    if finalDialogText != "" do
        messageBox finalDialogText title:finalDialogTitle
)
