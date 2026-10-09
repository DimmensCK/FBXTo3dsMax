/*
FBXTo3dsMax v1.4.26 事务式拖放安装器。

源文件夹不会作为运行目录。安装器先完整暂存插件包、核对哈希，再以目录
切换方式放入当前用户的 ApplicationPlugins；旧版插件包和已确认归属的
BlenderToMax 自动加载文件会归档到所有 ApplicationPlugins 扫描路径之外。
*/

global F2M_Installer_RunStatus
global F2M_Installer_LastLogPath
global F2M_Installer_FinalDialogTitle
global F2M_Installer_FinalDialogText
global F2M_TopologyHelper
global F2M_SkinHelper
global F2M_Helper
F2M_Installer_RunStatus = -1
F2M_Installer_LastLogPath = ""
F2M_Installer_FinalDialogTitle = ""
F2M_Installer_FinalDialogText = ""

(
    local installerVersion = "1.4.26"
    local installerPath = getSourceFileName()
    local fileClass = dotNetClass "System.IO.File"
    local directoryClass = dotNetClass "System.IO.Directory"
    local pathClass = dotNetClass "System.IO.Path"
    local guidClass = dotNetClass "System.Guid"
    local bitConverter = dotNetClass "System.BitConverter"
    local shaClass = dotNetClass "System.Security.Cryptography.SHA256"
    local logLines = #()
    local legacyMoves = #()
    local legacyConflicts = #()
    local managedFileSnapshots = #()
    local previousPackageRecords = #()
    local previousPackageExisted = false
    local rollbackFailures = #()
    local packageOwnershipTokens = #(
        "Name=\"FBXTo3dsMax\"",
        "UpgradeCode=\"{B7AD0BB7-C64E-4F41-9767-CA72294639AE}\""
    )
    local packageMovedToBackup = false
    local newPackageActivationAttempted = false
    local newPackageActivated = false
    local runtimeCleanupAttempted = false
    local runtimeWasStopped = false
    local previousPackageRestored = false
    local previousPackagePath = ""
    local targetPackage = ""
    local failedPackage = ""
    local environmentClass = dotNetClass "System.Environment"
    local launchedSilently = false
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


    -- PowerShell 备用启动器以 -silent 抑制欢迎页和安全消息，避免它们在
    -- 安装时禁用 Max 主窗口。命令行脚本会在 Max 完成启动后执行；到这里
    -- 立即恢复正常对话框行为，因此安装结果仍会以中文显示。
    try
    (
        launchedSilently = (environmentClass.GetEnvironmentVariable "F2M_POWERSHELL_LAUNCH") == "1"
        if launchedSilently do
        (
            setSilentMode false
            environmentClass.SetEnvironmentVariable "F2M_POWERSHELL_LAUNCH" ""
        )
    )
    catch()

    fn writeInstallerLog message =
    (
        local line = "[FBXTo3dsMax 安装器] " + (message as string)
        append logLines line
        format "%\n" line
    )

    fn recordRollbackFailure message =
    (
        local text = message as string
        append rollbackFailures text
        writeInstallerLog ("回滚错误：" + text)
        false
    )

    fn joinPath basePath childPath =
    (
        pathClass.GetFullPath (pathClass.Combine basePath childPath)
    )

    fn uniqueToken =
    (
        substituteString ((guidClass.NewGuid()).ToString()) "-" ""
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
            throw "另一个 FBXTo3dsMax 安装或卸载事务正在运行。为避免插件目录损坏，本次安装已取消；请等待前一次操作结束后重试。"
        if packageMutationLock == undefined do
            throw "无法取得 FBXTo3dsMax 安装互斥锁，本次安装已取消。"
        writeInstallerLog ("已取得安装互斥锁：" + lockPath)
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

    fn safeRelativePath relativePath =
    (
        local p = relativePath as string
        if p == "" do return false
        if findString p ".." != undefined do return false
        if (substring p 1 1) == "\\" or (substring p 1 1) == "/" do return false
        if p.count >= 2 and (substring p 2 1) == ":" do return false
        true
    )

    fn copyVerified sourcePath destinationPath =
    (
        if not fileClass.Exists sourcePath do throw ("缺少源文件：" + sourcePath)

        local destinationDir = pathClass.GetDirectoryName destinationPath
        ensureDirectory destinationDir

        local sourceHash = sha256File sourcePath
        if sourceHash == "" do throw ("无法计算源文件哈希：" + sourcePath)

        fileClass.Copy sourcePath destinationPath true

        local destinationHash = sha256File destinationPath
        if destinationHash != sourceHash do
        (
            throw ("文件复制后的哈希读回不一致：" + destinationPath)
        )
        sourceHash
    )

    fn textContainsAll filePath tokens =
    (
        if not fileClass.Exists filePath do return false
        local content = ""
        try(content = toLower (fileClass.ReadAllText filePath))catch(return false)
        for token in tokens where findString content (toLower token) == undefined do return false
        true
    )

    fn snapshotPreviousPackage packageRoot =
    (
        previousPackageRecords = #()
        if not (directoryClass.Exists packageRoot) do return false
        if not textContainsAll (joinPath packageRoot "PackageContents.xml") packageOwnershipTokens do
            throw ("旧插件包归属读回失败：" + packageRoot)

        local searchOption = dotNetClass "System.IO.SearchOption"
        local packageFiles = directoryClass.GetFiles packageRoot "*" searchOption.AllDirectories
        for packageFile in packageFiles do
        (
            local absolutePath = packageFile as string
            local relativePath = substituteString absolutePath (packageRoot + "\\") ""
            local expectedHash = sha256File absolutePath
            if expectedHash == "" do
                throw ("无法计算旧插件包文件哈希：" + absolutePath)
            append previousPackageRecords #(relativePath, expectedHash)
        )
        if previousPackageRecords.count < 1 do
            throw ("旧插件包没有可验证文件：" + packageRoot)
        true
    )

    fn verifyPreviousPackageSnapshot packageRoot =
    (
        local allOk = true
        if not (directoryClass.Exists packageRoot) then
        (
            writeInstallerLog ("旧插件包读回失败，目录不存在：" + packageRoot)
            return false
        )
        if not textContainsAll (joinPath packageRoot "PackageContents.xml") packageOwnershipTokens do
        (
            writeInstallerLog ("旧插件包归属标记读回失败：" + packageRoot)
            allOk = false
        )

        local searchOption = dotNetClass "System.IO.SearchOption"
        local liveFiles = directoryClass.GetFiles packageRoot "*" searchOption.AllDirectories
        if liveFiles.count != previousPackageRecords.count do
        (
            writeInstallerLog (
                "旧插件包文件数量读回不一致：" + packageRoot +
                " | 预期 " + (previousPackageRecords.count as string) +
                "，实际 " + (liveFiles.count as string)
            )
            allOk = false
        )
        for record in previousPackageRecords do
        (
            local livePath = joinPath packageRoot record[1]
            if not (fileClass.Exists livePath) then
            (
                writeInstallerLog ("旧插件包文件缺失：" + livePath)
                allOk = false
            )
            else if sha256File livePath != record[2] do
            (
                writeInstallerLog ("旧插件包文件 SHA-256 读回不一致：" + livePath)
                allOk = false
            )
        )
        allOk
    )

    fn snapshotManagedFile originalPath snapshotPath newTemplatePath ownershipTokens =
    (
        local existedBefore = fileClass.Exists originalPath
        local originalHash = ""
        local newHash = sha256File newTemplatePath
        if newHash == "" do throw ("无法计算受管文件模板哈希：" + newTemplatePath)

        if existedBefore do
        (
            if not textContainsAll originalPath ownershipTokens do
            (
                throw ("拒绝覆盖无法确认归属的受管文件：" + originalPath)
            )
            originalHash = copyVerified originalPath snapshotPath
        )

        append managedFileSnapshots #(originalPath, snapshotPath, existedBefore, originalHash, newHash, ownershipTokens)
        true
    )

    fn verifyManagedFiles =
    (
        local allOk = true
        for record in managedFileSnapshots do
        (
            local originalPath = record[1]
            local existedBefore = record[3]
            local originalHash = record[4]
            local ownershipTokens = record[6]

            if existedBefore then
            (
                if not (fileClass.Exists originalPath) then
                (
                    writeInstallerLog ("受管文件恢复后不存在：" + originalPath)
                    allOk = false
                )
                else
                (
                    if sha256File originalPath != originalHash do
                    (
                        writeInstallerLog ("受管文件恢复后的 SHA-256 不一致：" + originalPath)
                        allOk = false
                    )
                    if not textContainsAll originalPath ownershipTokens do
                    (
                        writeInstallerLog ("受管文件恢复后的归属标记不一致：" + originalPath)
                        allOk = false
                    )
                )
            )
            else if fileClass.Exists originalPath do
            (
                writeInstallerLog ("安装前不存在的受管文件在回滚后仍然存在：" + originalPath)
                allOk = false
            )
        )
        allOk
    )

    fn previousBootstrapPreservesManagedFiles packageRoot =
    (
        local allOk = true
        for record in managedFileSnapshots do
        (
            local originalPath = record[1]
            local existedBefore = record[3]
            local originalHash = record[4]
            local extension = toLower (pathClass.GetExtension originalPath)
            local oldTemplate = if extension == ".mcr" then
                (joinPath packageRoot "contents\\FBXTo3dsMax.mcr")
            else
                (joinPath packageRoot "contents\\icons\\FBXTo3dsMax.svg")

            if not existedBefore then
            (
                writeInstallerLog (
                    "旧 Bootstrap 会重新生成安装前不存在的受管文件：" +
                    originalPath
                )
                allOk = false
            )
            else if (not (fileClass.Exists oldTemplate)) or
                    (sha256File oldTemplate != originalHash) do
            (
                writeInstallerLog (
                    "旧 Bootstrap 模板与安装前受管文件不一致：" +
                    originalPath
                )
                allOk = false
            )
        )
        allOk
    )

    fn restoreManagedFiles failureStateRoot =
    (
        local allOk = true
        for record in managedFileSnapshots do
        (
            local originalPath = record[1]
            local snapshotPath = record[2]
            local existedBefore = record[3]
            local originalHash = record[4]
            local newHash = record[5]
            local ownershipTokens = record[6]

            try
            (
                if existedBefore then
                (
                    if not (fileClass.Exists snapshotPath) do
                        throw ("受管文件快照不存在：" + snapshotPath)
                    if sha256File snapshotPath != originalHash do
                        throw ("受管文件快照 SHA-256 不一致：" + snapshotPath)
                    if not textContainsAll snapshotPath ownershipTokens do
                        throw ("受管文件快照归属标记不一致：" + snapshotPath)
                    if fileClass.Exists originalPath do
                    (
                        local currentHash = sha256File originalPath
                        if currentHash == "" do
                            throw ("无法计算回滚前受管文件哈希：" + originalPath)
                        if currentHash != originalHash then
                        (
                            if (currentHash == newHash) or (textContainsAll originalPath ownershipTokens) then
                            (
                                ensureDirectory failureStateRoot
                                local regeneratedPath = joinPath failureStateRoot (pathClass.GetFileName originalPath)
                                if fileClass.Exists regeneratedPath do
                                    regeneratedPath = joinPath failureStateRoot ((uniqueToken()) + "-" + (pathClass.GetFileName originalPath))
                                fileClass.Move originalPath regeneratedPath
                                if (fileClass.Exists originalPath) or (not (fileClass.Exists regeneratedPath)) do
                                    throw ("受管文件回滚前归档的存在性读回失败：" + originalPath)
                                if sha256File regeneratedPath != currentHash do
                                    throw ("受管文件回滚前归档的 SHA-256 读回失败：" + regeneratedPath)
                                if not textContainsAll regeneratedPath ownershipTokens do
                                    throw ("受管文件回滚前归档的归属标记读回失败：" + regeneratedPath)
                                writeInstallerLog (
                                    "已保留并验证 Bootstrap 生成的受管文件：" +
                                    regeneratedPath
                                )
                            )
                            else
                            (
                                throw ("拒绝覆盖无法确认归属的意外受管文件：" + originalPath)
                            )
                        )
                    )
                    if not (fileClass.Exists originalPath) do
                        copyVerified snapshotPath originalPath
                )
                else if fileClass.Exists originalPath do
                (
                    if (sha256File originalPath == newHash) or (textContainsAll originalPath ownershipTokens) then
                    (
                        local failedStateHash = sha256File originalPath
                        if failedStateHash == "" do
                            throw ("无法计算待移出的受管文件哈希：" + originalPath)
                        ensureDirectory failureStateRoot
                        local failedStatePath = joinPath failureStateRoot (pathClass.GetFileName originalPath)
                        if fileClass.Exists failedStatePath do
                        (
                            failedStatePath = joinPath failureStateRoot ((uniqueToken()) + "-" + (pathClass.GetFileName originalPath))
                        )
                        fileClass.Move originalPath failedStatePath
                        if (fileClass.Exists originalPath) or (not (fileClass.Exists failedStatePath)) do
                            throw ("新建受管文件移出后的存在性读回失败：" + originalPath)
                        if sha256File failedStatePath != failedStateHash do
                            throw ("新建受管文件移出后的 SHA-256 读回失败：" + failedStatePath)
                        if not textContainsAll failedStatePath ownershipTokens do
                            throw ("新建受管文件移出后的归属标记读回失败：" + failedStatePath)
                        writeInstallerLog (
                            "回滚时已移出并验证新建的受管文件：" +
                            originalPath + " -> " + failedStatePath
                        )
                    )
                    else
                    (
                        recordRollbackFailure (
                            "发现无法确认归属的意外受管文件，已保持不动：" +
                            originalPath
                        )
                        allOk = false
                    )
                )
            )
            catch
            (
                recordRollbackFailure (
                    "无法恢复受管文件：" + originalPath +
                    " | " + (getCurrentException())
                )
                allOk = false
            )
        )
        if not verifyManagedFiles() do
        (
            recordRollbackFailure "一个或多个受管 Macro/Icon 文件没有恢复到安装前状态。"
            allOk = false
        )
        allOk
    )

    fn archiveOwnedLegacyFile originalPath archiveDir tokens =
    (
        if not fileClass.Exists originalPath do return false

        if not textContainsAll originalPath tokens then
        (
            append legacyConflicts originalPath
            writeInstallerLog ("发现旧版同名文件，但归属标记不匹配，已保持不动：" + originalPath)
            return false
        )

        ensureDirectory archiveDir
        local archivePath = joinPath archiveDir (pathClass.GetFileName originalPath)
        local beforeHash = sha256File originalPath
        if beforeHash == "" do throw ("无法计算旧版文件哈希：" + originalPath)
        if fileClass.Exists archivePath do throw ("旧版归档路径发生冲突：" + archivePath)

        fileClass.Move originalPath archivePath
        local afterHash = sha256File archivePath
        if afterHash != beforeHash then
        (
            if (fileClass.Exists archivePath) and (not (fileClass.Exists originalPath)) do
            (
                fileClass.Move archivePath originalPath
            )
            throw ("旧版文件归档后的哈希不一致：" + originalPath)
        )

        append legacyMoves #(originalPath, archivePath, beforeHash, tokens)
        writeInstallerLog ("已归档旧版自动加载文件：" + originalPath)
        true
    )

    fn removeLiveRuntime =
    (
        local selfcheckStopError = ""
        local cleanupError = ""
        try
        (
            python.Execute "import builtins\n_f2m_controller = getattr(builtins, '_FBXTO3DSMAX_SELFCHECK_CONTROLLER', None)\nif _f2m_controller is not None:\n    _f2m_shutdown = getattr(_f2m_controller, 'shutdown', None)\n    if not callable(_f2m_shutdown):\n        raise RuntimeError('自检控制器缺少安全停止接口。')\n    _f2m_shutdown()\n    _f2m_is_running = getattr(_f2m_controller, 'is_running', None)\n    if callable(_f2m_is_running) and _f2m_is_running():\n        raise RuntimeError('自检子进程在停止后仍然运行。')\n    if getattr(builtins, '_FBXTO3DSMAX_SELFCHECK_CONTROLLER', None) is _f2m_controller:\n        delattr(builtins, '_FBXTO3DSMAX_SELFCHECK_CONTROLLER')\nfor _f2m_cleanup_name in ('_f2m_controller', '_f2m_shutdown', '_f2m_is_running', '_f2m_cleanup_name'):\n    globals().pop(_f2m_cleanup_name, None)\n" throwOnError:true clearUndoBuffer:false
            writeInstallerLog "运行中的自检控制器已安全停止。"
        )
        catch
        (
            selfcheckStopError = getCurrentException()
        )
        if selfcheckStopError != "" do
        (
            writeInstallerLog ("错误：无法安全停止运行中的自检，覆盖安装已阻止：" + selfcheckStopError)
            throw ("无法安全停止运行中的自检，覆盖安装已取消：" + selfcheckStopError)
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
            writeInstallerLog ("错误：无法完整清理旧版 Python 运行模块：" + cleanupError)
        )
        if cleanupError != "" do
            throw ("无法完整清理旧版运行模块，覆盖安装已取消：" + cleanupError)
        true
    )

    fn verifyLegacyMoves =
    (
        local allOk = true
        for i = legacyMoves.count to 1 by -1 do
        (
            local originalPath = legacyMoves[i][1]
            local archivePath = legacyMoves[i][2]
            local expectedHash = legacyMoves[i][3]
            local ownershipTokens = legacyMoves[i][4]

            if not (fileClass.Exists originalPath) then
            (
                writeInstallerLog ("旧版文件恢复后不存在：" + originalPath)
                allOk = false
            )
            else
            (
                if sha256File originalPath != expectedHash do
                (
                    writeInstallerLog ("旧版文件恢复后的 SHA-256 不一致：" + originalPath)
                    allOk = false
                )
                if not textContainsAll originalPath ownershipTokens do
                (
                    writeInstallerLog ("旧版文件恢复后的归属标记不一致：" + originalPath)
                    allOk = false
                )
            )
            if fileClass.Exists archivePath do
            (
                writeInstallerLog ("旧版文件恢复后归档副本仍占用事务路径：" + archivePath)
                allOk = false
            )
        )
        allOk
    )

    fn restoreLegacyMoves =
    (
        local allOk = true
        for i = legacyMoves.count to 1 by -1 do
        (
            local originalPath = legacyMoves[i][1]
            local archivePath = legacyMoves[i][2]
            try
            (
                if (fileClass.Exists archivePath) and (not (fileClass.Exists originalPath)) do
                (
                    ensureDirectory (pathClass.GetDirectoryName originalPath)
                    fileClass.Move archivePath originalPath
                )
            )
            catch
            (
                recordRollbackFailure (
                    "无法恢复旧版文件：" + originalPath +
                    " | " + (getCurrentException())
                )
                allOk = false
            )
        )
        if not verifyLegacyMoves() do
        (
            recordRollbackFailure "一个或多个旧版启动脚本或 MacroScript 没有恢复到安装前状态。"
            allOk = false
        )
        allOk
    )

    fn restorePreviousPackageState targetPath backupPath expectedToExist =
    (
        local allOk = true
        try
        (
            if expectedToExist then
            (
                if (not (directoryClass.Exists targetPath)) and (directoryClass.Exists backupPath) do
                (
                    directoryClass.Move backupPath targetPath
                )
                if not (directoryClass.Exists targetPath) do
                    throw ("旧插件包目录没有恢复：" + targetPath)
                if directoryClass.Exists backupPath do
                    throw ("旧插件包恢复后备份目录仍然存在：" + backupPath)
                if not verifyPreviousPackageSnapshot targetPath do
                    throw ("旧插件包逐文件 SHA-256 或归属读回失败：" + targetPath)
                previousPackageRestored = true
                writeInstallerLog "旧插件包已按逐文件 SHA-256 和归属标记完整恢复。"
            )
            else
            (
                if directoryClass.Exists targetPath do
                    throw ("安装前不存在插件包，但回滚后目录仍然存在：" + targetPath)
                if directoryClass.Exists backupPath do
                    throw ("安装前不存在插件包，但回滚备份目录仍然存在：" + backupPath)
            )
        )
        catch
        (
            recordRollbackFailure (
                "旧插件包恢复不完整：" + (getCurrentException())
            )
            allOk = false
        )
        allOk
    )

    fn restartPreviousBootstrap packageRoot =
    (
        local allOk = true
        try
        (
            local oldBootstrap = joinPath packageRoot "contents\\FBXTo3dsMax_Bootstrap.ms"
            if not (fileClass.Exists oldBootstrap) do
                throw ("已恢复插件包缺少启动引导：" + oldBootstrap)
            if (fileIn oldBootstrap quiet:true) != true do
                throw ("已恢复插件包的启动引导没有返回成功状态：" + oldBootstrap)
            if ::FBXTo3dsMax_Bootstrap == undefined do
                throw "已恢复插件包没有建立启动引导对象。"
            if not ::FBXTo3dsMax_Bootstrap.verifyToolbar() do
                throw "已恢复插件包的顶部按钮没有通过读回验证。"
            writeInstallerLog "已恢复插件包的启动引导和顶部按钮已重新验证。"
        )
        catch
        (
            recordRollbackFailure (
                "无法安全重新启动已恢复的旧插件包：" +
                (getCurrentException())
            )
            allOk = false
        )
        allOk
    )

    fn writeLog logPath =
    (
        try
        (
            ensureDirectory (pathClass.GetDirectoryName logPath)
            local logText = ""
            for line in logLines do logText += ((line as string) + "\r\n")
            local utf8NoBom = dotNetObject "System.Text.UTF8Encoding" false
            fileClass.WriteAllText logPath logText utf8NoBom
        )
        catch()
    )

    if installerPath == undefined or installerPath == "" then
    (
        F2M_Installer_RunStatus = 0
        F2M_Installer_FinalDialogTitle = (localized "FBXTo3dsMax - 安装失败" "FBXTo3dsMax - Installation failed")
        F2M_Installer_FinalDialogText = (localized "请把 Install_FBXTo3dsMax.ms 文件直接拖入 3ds Max 视口。复制脚本文本后运行将无法定位安装文件。" "Drag the complete Install_FBXTo3dsMax.ms file into a 3ds Max viewport. Pasting its text cannot locate the package.")
        messageBox F2M_Installer_FinalDialogText title:F2M_Installer_FinalDialogTitle
    )
    else
    (
        local sourceRoot = pathClass.GetFullPath (getFilenamePath installerPath)
        local sourceManifest = joinPath sourceRoot "contents\\FBXTo3dsMax.files"
        local pluginBase = pathClass.GetFullPath (getDir #privateExchangeStoreInstallPath)
        local workRoot = joinPath pluginBase "..\\FBXTo3dsMaxInstaller"
        local token = uniqueToken()
        local stageRoot = joinPath workRoot ("Staging\\" + token)
        local stagePackage = joinPath stageRoot "FBXTo3dsMax"
        local backupRoot = joinPath workRoot ("Backups\\" + installerVersion + "-" + token)
        local packageBackup = joinPath backupRoot "FBXTo3dsMax"
        local failureRoot = joinPath workRoot ("Failed\\" + token)
        local legacyRoot = joinPath (getDir #maxData) ("FBXTo3dsMax\\LegacyArchive\\" + token)
        local logPath = joinPath workRoot ("Logs\\Install-" + token + ".log")
        local manifestEntries = #()
        local hashRecords = #()

        targetPackage = joinPath pluginBase "FBXTo3dsMax"
        failedPackage = joinPath failureRoot "FBXTo3dsMax"
        previousPackagePath = packageBackup

        try
        (
            writeInstallerLog ("正在安装 FBXTo3dsMax " + installerVersion)
            writeInstallerLog ("源目录：" + sourceRoot)
            writeInstallerLog ("安装目录：" + targetPackage)
            if not (ensureDirectory pluginBase) do throw ("无法准备 ApplicationPlugins 目录：" + pluginBase)
            acquirePackageMutationLock workRoot

            if not fileClass.Exists sourceManifest do throw ("缺少源文件清单：" + sourceManifest)

            local manifestLines = fileClass.ReadAllLines sourceManifest
            for rawLine in manifestLines do
            (
                local line = rawLine as string
                if line.count > 0 and (substring line 1 1) != "#" do
                (
                    local parts = filterString line "|"
                    if parts.count != 2 do throw ("文件清单行格式无效：" + line)
                    if (not (safeRelativePath parts[1])) or (not (safeRelativePath parts[2])) do
                    (
                        throw ("文件清单包含不安全路径：" + line)
                    )
                    append manifestEntries #(parts[1], parts[2])
                )
            )
            if manifestEntries.count == 0 do throw "源文件清单中没有任何文件。"
            local requiredManifestDestinations = #(
                "PackageContents.xml",
                "contents\\FBXTo3dsMax_Bootstrap.ms",
                "contents\\FBXTo3dsMax.files",
                "contents\\FBXTo3dsMax.version",
                "contents\\FBXTo3dsMax_UI.ms",
                "contents\\FBXTo3dsMax.mcr",
                "contents\\f2m_toolbar.py",
                "contents\\f2m_topology_transfer.py",
                "contents\\f2m_skin_replace.py",
                "contents\\f2m_smoothing.py",
                "contents\\f2m_fbx_metadata.py",
                "contents\\f2m_selfcheck.py",
                "contents\\f2m_i18n.py",
                "contents\\f2m_report_i18n.py",
                "contents\\f2m_test_fixtures.py",
                "contents\\LICENSE",
                "contents\\FBXTo3dsMax_详细说明书.md",
                "contents\\tests\\max_normals_safety.py"
            )
            for requiredDestination in requiredManifestDestinations do
            (
                local requiredFound = false
                for entry in manifestEntries where entry[2] == requiredDestination do
                (
                    requiredFound = true
                    exit
                )
                if not requiredFound do
                (
                    throw ("源文件清单缺少必要目标：" + requiredDestination)
                )
            )

            ensureDirectory stagePackage
            for entry in manifestEntries do
            (
                local sourcePath = joinPath sourceRoot entry[1]
                local stagePath = joinPath stagePackage entry[2]
                local fileHash = copyVerified sourcePath stagePath
                append hashRecords #(entry[2], fileHash)
                writeInstallerLog ("已暂存：" + entry[2])
            )

            local installedHashManifest = joinPath stagePackage "contents\\FBXTo3dsMax.install-manifest.sha256"
            local hashManifestText = ""
            for record in hashRecords do
                hashManifestText += (record[1] + "|" + record[2] + "\r\n")
            local utf8NoBom = dotNetObject "System.Text.UTF8Encoding" false
            fileClass.WriteAllText installedHashManifest hashManifestText utf8NoBom
            if not fileClass.Exists installedHashManifest do throw "安装哈希清单读回失败。"

            local stagedVersionPath = joinPath stagePackage "contents\\FBXTo3dsMax.version"
            local stagedVersionText = fileClass.ReadAllText stagedVersionPath
            stagedVersionText = substituteString stagedVersionText "\r" ""
            stagedVersionText = substituteString stagedVersionText "\n" ""
            if stagedVersionText != installerVersion do
            (
                throw ("版本文件与安装器版本不一致：" + installerVersion)
            )

            local packageXmlText = fileClass.ReadAllText (joinPath stagePackage "PackageContents.xml")
            if findString packageXmlText ("AppVersion=\"" + installerVersion + "\"") == undefined do
            (
                throw "PackageContents.xml 版本与安装器不一致。"
            )
            if (findString packageXmlText "Name=\"FBXTo3dsMax\"" == undefined) or (findString packageXmlText "UpgradeCode=\"{B7AD0BB7-C64E-4F41-9767-CA72294639AE}\"" == undefined) do
            (
                throw "PackageContents.xml 的归属标记与本安装器不一致。"
            )

            if directoryClass.Exists targetPackage do
            (
                local currentPackageXml = joinPath targetPackage "PackageContents.xml"
                local currentPackageOwned = textContainsAll currentPackageXml packageOwnershipTokens
                if not currentPackageOwned do
                (
                    throw ("拒绝替换无法确认归属的插件目录：" + targetPackage)
                )

                local currentVersionPath = joinPath targetPackage "contents\\FBXTo3dsMax.version"
                if not (fileClass.Exists currentVersionPath) do
                (
                    throw ("拒绝替换缺少版本标记的插件包：" + currentVersionPath)
                )
                local currentVersionText = fileClass.ReadAllText currentVersionPath
                currentVersionText = substituteString currentVersionText "\r" ""
                currentVersionText = substituteString currentVersionText "\n" ""
                local versionClass = dotNetClass "System.Version"
                local currentVersion = versionClass.Parse currentVersionText
                local requestedVersion = versionClass.Parse installerVersion
                if (currentVersion.CompareTo requestedVersion) > 0 do
                (
                    throw ("拒绝把 FBXTo3dsMax 从 " + currentVersionText + " 降级到 " + installerVersion + "。请使用更新的安装器，或先明确卸载当前版本。")
                )
                if not snapshotPreviousPackage targetPackage do
                    throw ("无法建立旧插件包逐文件快照：" + targetPackage)
                previousPackageExisted = true
            )

            local managedMacro = joinPath (getDir #userMacros) "FBXTo3dsMax-FBXTo3dsMax_Open.mcr"
            local deprecatedManagedMacro = joinPath (getDir #userMacros) "FBXTo3dsMax.mcr"
            local managedLightIcon = joinPath (getDir #userIcons) "Light\\FBXTo3dsMax\\FBXTo3dsMax.svg"
            local managedDarkIcon = joinPath (getDir #userIcons) "Dark\\FBXTo3dsMax\\FBXTo3dsMax.svg"
            local macroTemplate = joinPath stagePackage "contents\\FBXTo3dsMax.mcr"
            local iconTemplate = joinPath stagePackage "contents\\icons\\FBXTo3dsMax.svg"
            snapshotManagedFile managedMacro (joinPath backupRoot "UserState\\UserMacros\\FBXTo3dsMax-FBXTo3dsMax_Open.mcr") macroTemplate #(
                "macroScript FBXTo3dsMax_Open",
                "category:\"FBXTo3dsMax\""
            )
            snapshotManagedFile managedLightIcon (joinPath backupRoot "UserState\\UserIcons\\Light\\FBXTo3dsMax.svg") iconTemplate #(
                "<svg",
                "<title>FBXTo3dsMax</title>"
            )
            snapshotManagedFile managedDarkIcon (joinPath backupRoot "UserState\\UserIcons\\Dark\\FBXTo3dsMax.svg") iconTemplate #(
                "<svg",
                "<title>FBXTo3dsMax</title>"
            )

            local legacyStartup = joinPath (getDir #userStartupScripts) "BlenderToMaxTransfer_AutoLoader.ms"
            local legacyStartupTokens = #(
                "Auto generated loader for BlenderToMaxTransfer",
                "BlenderToMaxTransfer_UI.ms"
            )
            local oldMacro1 = joinPath (getDir #userMacros) "BlenderToMaxTransfer.mcr"
            local oldMacro2 = joinPath (getDir #userMacros) "BlenderToMax-BlenderToMaxTransfer.mcr"
            local oldMacroTokens = #(
                "macroScript BlenderToMaxTransfer",
                "BlenderToMax",
                "BlenderToMaxTransfer_UI.ms"
            )
            local legacyChecks = #(
                #(legacyStartup, legacyStartupTokens),
                #(oldMacro1, oldMacroTokens),
                #(oldMacro2, oldMacroTokens),
                #(deprecatedManagedMacro, #("macroScript FBXTo3dsMax_Open", "category:\"FBXTo3dsMax\""))
            )
            for legacyCheck in legacyChecks do
            (
                if (fileClass.Exists legacyCheck[1]) and (not (textContainsAll legacyCheck[1] legacyCheck[2])) do
                (
                    throw ("无法安全确认一个旧版同名文件的归属，已保持不动：" + legacyCheck[1])
                )
            )

            -- removeLiveRuntime 会先移除回调/窗口，再驱逐 Python 模块；即使
            -- 后半段抛错，catch 也必须知道运行态已经可能被部分改变。
            runtimeCleanupAttempted = true
            removeLiveRuntime()
            runtimeWasStopped = true
            ensureDirectory backupRoot

            if directoryClass.Exists targetPackage do
            (
                directoryClass.Move targetPackage packageBackup
                packageMovedToBackup = true
                if (not (directoryClass.Exists packageBackup)) or (directoryClass.Exists targetPackage) do
                (
                    throw "旧插件包归档读回失败。"
                )
                if not (fileClass.Exists (joinPath packageBackup "PackageContents.xml")) do
                (
                    throw "旧插件包归档缺少 PackageContents.xml。"
                )
                if not verifyPreviousPackageSnapshot packageBackup do
                (
                    throw "旧插件包归档后的逐文件 SHA-256 或归属读回失败。"
                )
                writeInstallerLog ("已归档旧插件包：" + packageBackup)
            )

            newPackageActivationAttempted = true
            directoryClass.Move stagePackage targetPackage
            newPackageActivated = true
            if (not (directoryClass.Exists targetPackage)) or (directoryClass.Exists stagePackage) do
            (
                throw "暂存插件包启用后的读回失败。"
            )
            writeInstallerLog "暂存插件包已启用。"

            for record in hashRecords do
            (
                local installedPath = joinPath targetPackage record[1]
                if sha256File installedPath != record[2] do
                (
                    throw ("已安装文件的哈希不一致：" + installedPath)
                )
            )

            -- The old drag installer created only this exact AutoLoader.
            archiveOwnedLegacyFile legacyStartup (joinPath legacyRoot "Startup") legacyStartupTokens

            -- The PowerShell installer wrote the first name.  Evaluating the
            -- same macro can also produce the category-name backing filename.
            archiveOwnedLegacyFile oldMacro1 (joinPath legacyRoot "Macros") oldMacroTokens
            archiveOwnedLegacyFile oldMacro2 (joinPath legacyRoot "Macros") oldMacroTokens
            -- Earlier development builds copied this non-canonical short name.
            -- Archive it so only Max's category-macro backing filename remains.
            archiveOwnedLegacyFile deprecatedManagedMacro (joinPath legacyRoot "Macros") #(
                "macroScript FBXTo3dsMax_Open",
                "category:\"FBXTo3dsMax\""
            )

            if legacyConflicts.count > 0 do
            (
                throw ("无法安全确认一个旧版启动脚本或 MacroScript 的归属。该文件已保持不动；请查看安装日志并解决归属冲突后重试。")
            )

            if legacyMoves.count > 0 do
            (
                local legacyManifestPath = joinPath legacyRoot "legacy-archive.sha256"
                local legacyStream = createFile legacyManifestPath
                if legacyStream == undefined do throw ("无法创建旧版归档清单：" + legacyManifestPath)
                for moveRecord in legacyMoves do
                (
                    format "%|%|%\n" moveRecord[1] moveRecord[2] moveRecord[3] to:legacyStream
                )
                close legacyStream
                legacyStream = undefined
            )

            local bootstrapPath = joinPath targetPackage "contents\\FBXTo3dsMax_Bootstrap.ms"
            local bootstrapResult = fileIn bootstrapPath quiet:true
            if bootstrapResult != true do
            (
                local bootstrapDetail = ""
                try
                (
                    if ::FBXTo3dsMax_Bootstrap != undefined do
                        bootstrapDetail = ::FBXTo3dsMax_Bootstrap.lastError as string
                )
                catch()
                throw (
                    "已安装的启动引导没有返回成功状态。" +
                    (if bootstrapDetail != "" then (" " + bootstrapDetail) else "")
                )
            )
            if ::FBXTo3dsMax_Bootstrap == undefined or (not ::FBXTo3dsMax_Bootstrap.verifyToolbar()) do
            (
                throw "顶部“FBX 转 MAX”按钮没有通过可见区域和点击命中验证。"
            )

            local installedMacroTemplate = joinPath targetPackage "contents\\FBXTo3dsMax.mcr"
            local userMacro = joinPath (getDir #userMacros) "FBXTo3dsMax-FBXTo3dsMax_Open.mcr"
            if sha256File installedMacroTemplate != sha256File userMacro do
            (
                throw "已注册 MacroScript 的哈希读回失败。"
            )

            writeInstallerLog ("安装完成。已归档旧版文件数：" + (legacyMoves.count as string))
            if legacyConflicts.count > 0 do
            (
                writeInstallerLog ("保持不动的旧版归属冲突数：" + (legacyConflicts.count as string))
            )
            writeLog logPath
            F2M_Installer_LastLogPath = logPath
            F2M_Installer_RunStatus = 1

            local backupMessage = if packageMovedToBackup then ((localized "\n旧插件包备份：\n" "\nPrevious package backup:\n") + packageBackup + "\n") else ""
            local legacyMessage = if legacyMoves.count > 0 then ((localized "\n旧版自动加载文件归档：\n" "\nLegacy startup archive:\n") + legacyRoot + (localized "\n完成本次验证后请重启一次 3ds Max，以清除内存中的旧 MacroScript 条目。\n" "\nAfter verification, restart 3ds Max to release cached legacy MacroScript actions.\n")) else ""
            local conflictMessage = if legacyConflicts.count > 0 then ((localized "\n警告：" "\nWarning: ") + (legacyConflicts.count as string) + (localized " 个旧版同名文件与已知归属标记不匹配，因此保持不动。详情请查看安装日志。\n" " legacy files have unrecognized ownership and were preserved. See the installation log.\n")) else ""

            finalDialogTitle = "FBXTo3dsMax"
            finalDialogText = (
            (localized "FBXTo3dsMax v1.4.26 安装成功。\n\n" "FBXTo3dsMax v1.4.26 installed successfully.\n\n") +
                (localized "3ds Max 顶部已经创建一个显眼的“FBX 转 MAX”按钮，并通过可见区域与点击命中验证。\n" "The FBX to MAX toolbar button passed visibility and hit-area checks.\n") +
                (localized "安装完成时不会自动打开主窗口；需要时请点击顶部按钮。\n\n" "Click the toolbar button when you want to open the plug-in.\n\n") +
                (localized "安装目录：\n" "Installation directory:\n") + targetPackage + "\n" +
                backupMessage + legacyMessage + conflictMessage +
                (localized "\n安装日志：\n" "\nInstallation log:\n") + logPath
            )
        )
        catch
        (
            local installError = getCurrentException()
            writeInstallerLog ("错误：" + installError)
            F2M_Installer_RunStatus = 0
            local rollbackNeeded = (
                runtimeCleanupAttempted or runtimeWasStopped or
                packageMovedToBackup or newPackageActivationAttempted or
                newPackageActivated or legacyMoves.count > 0
            )
            local runtimeRollbackOk = true
            local failedPackageRollbackOk = true
            local packageRollbackOk = true
            local legacyRollbackOk = true
            local managedRollbackOk = true
            local bootstrapRollbackOk = true
            local failedPackageError = ""

            if rollbackNeeded do
            (
                -- 第二次运行态清理失败也必须继续恢复磁盘，但最终结果必须明确
                -- 标记为“回滚不完整”，不能把仍存活的新模块伪装成旧版状态。
                try
                (
                    if runtimeCleanupAttempted or runtimeWasStopped or newPackageActivated do
                    (
                        removeLiveRuntime()
                        runtimeWasStopped = true
                    )
                )
                catch
                (
                    recordRollbackFailure (
                        "回滚前无法完整清理失败的运行模块；仍将继续恢复磁盘状态：" +
                        (getCurrentException())
                    )
                    runtimeRollbackOk = false
                )

                try
                (
                    if (newPackageActivated or newPackageActivationAttempted) and (directoryClass.Exists targetPackage) do
                    (
                        ensureDirectory failureRoot
                        if directoryClass.Exists failedPackage then
                        (
                            failedPackageError = "失败包诊断路径已被占用：" + failedPackage
                            failedPackageRollbackOk = false
                        )
                        else
                        (
                            directoryClass.Move targetPackage failedPackage
                            if (directoryClass.Exists targetPackage) or (not (directoryClass.Exists failedPackage)) then
                            (
                                failedPackageError = "失败的新插件包移出后的存在性读回失败。"
                                failedPackageRollbackOk = false
                            )
                            else if not textContainsAll (joinPath failedPackage "PackageContents.xml") packageOwnershipTokens then
                            (
                                failedPackageError = "失败的新插件包移出后的归属标记读回失败。"
                                failedPackageRollbackOk = false
                            )
                            else
                            (
                                writeInstallerLog ("已保留并验证失败的新插件包：" + failedPackage)
                            )
                        )
                    )
                )
                catch
                (
                    failedPackageError = getCurrentException()
                    failedPackageRollbackOk = false
                )
                if failedPackageError != "" do
                    recordRollbackFailure ("无法完整移出失败的新插件包：" + failedPackageError)

                -- 先恢复所有磁盘状态，最后才允许旧 Bootstrap 重新读取这些文件。
                packageRollbackOk = restorePreviousPackageState targetPackage packageBackup previousPackageExisted
                legacyRollbackOk = restoreLegacyMoves()
                managedRollbackOk = restoreManagedFiles (joinPath failureRoot "UserState")

                if previousPackageExisted then
                (
                    local bootstrapInputsOk = previousBootstrapPreservesManagedFiles targetPackage
                    if not bootstrapInputsOk do
                    (
                        bootstrapRollbackOk = false
                        recordRollbackFailure "旧 Bootstrap 会改变已恢复的受管文件；为保持安装前字节，未重新启动旧插件。"
                    )
                    if runtimeRollbackOk and runtimeWasStopped and
                       failedPackageRollbackOk and packageRollbackOk and
                       legacyRollbackOk and managedRollbackOk and bootstrapInputsOk and
                       rollbackFailures.count == 0 then
                    (
                        bootstrapRollbackOk = restartPreviousBootstrap targetPackage
                        if bootstrapRollbackOk do
                        (
                            -- Bootstrap 可能重新生成 Macro/Icon；启动后必须再次
                            -- 证明旧包和用户文件仍与安装前快照完全一致。
                            if not verifyPreviousPackageSnapshot targetPackage do
                            (
                                recordRollbackFailure "重新启动旧插件后，旧包逐文件读回不一致。"
                                bootstrapRollbackOk = false
                            )
                            if not verifyLegacyMoves() do
                            (
                                recordRollbackFailure "重新启动旧插件后，旧版文件读回不一致。"
                                bootstrapRollbackOk = false
                            )
                            if not verifyManagedFiles() do
                            (
                                recordRollbackFailure "重新启动旧插件后，受管 Macro/Icon 读回不一致。"
                                bootstrapRollbackOk = false
                            )
                        )
                        if not bootstrapRollbackOk do
                        (
                            try
                            (
                                if ::FBXTo3dsMax_Bootstrap != undefined do
                                    ::FBXTo3dsMax_Bootstrap.shutdown()
                            )
                            catch
                            (
                                recordRollbackFailure (
                                    "旧插件重启验证失败后也无法停止其运行态：" +
                                    (getCurrentException())
                                )
                            )
                            if not verifyManagedFiles() do
                            (
                                writeInstallerLog "正在再次恢复被旧 Bootstrap 改写的受管文件。"
                                restoreManagedFiles (joinPath failureRoot "UserState")
                            )
                        )
                    )
                    else
                    (
                        bootstrapRollbackOk = false
                        recordRollbackFailure "磁盘或运行模块尚未完整恢复；为避免混合状态，未重新启动旧插件。"
                    )
                )
            )

            local rollbackComplete = (
                rollbackFailures.count == 0 and runtimeRollbackOk and
                failedPackageRollbackOk and packageRollbackOk and
                legacyRollbackOk and managedRollbackOk and
                bootstrapRollbackOk
            )
            if rollbackComplete then
                writeInstallerLog "回滚最终状态：完整。"
            else
                writeInstallerLog (
                    "回滚最终状态：不完整，共 " +
                    (rollbackFailures.count as string) + " 项失败。"
                )
            writeLog logPath
            F2M_Installer_LastLogPath = logPath

            if rollbackComplete then
            (
                finalDialogTitle = (localized "FBXTo3dsMax - 安装失败" "FBXTo3dsMax - Installation failed")
                finalDialogText = (
                    (localized "FBXTo3dsMax 安装失败。" "FBXTo3dsMax installation failed.") +
                    (
                        if rollbackNeeded then
                            (localized "\n\n安装器已按存在性、SHA-256 和归属标记完整恢复安装前状态。" "\n\nThe previous installation was restored and verified by existence, SHA-256 and ownership.")
                        else
                            (localized "\n\n错误发生在修改插件状态之前，没有需要回滚的改动。" "\n\nThe error occurred before changing plug-in state; no rollback was needed.")
                    ) +
                    (localized "\n\n具体技术信息已写入安装日志。\n\n日志：\n" "\n\nFull technical diagnostics are retained in the installation log:\n") + logPath
                )
            )
            else
            (
                local rollbackPreview = ""
                local previewCount = rollbackFailures.count
                if previewCount > 5 do previewCount = 5
                for i = 1 to previewCount do
                    rollbackPreview += ("\n- " + rollbackFailures[i])
                finalDialogTitle = (localized "FBXTo3dsMax - 安装失败（回滚不完整）" "FBXTo3dsMax - Installation failed; rollback incomplete")
                finalDialogText = (
                    (localized "FBXTo3dsMax 安装失败，而且回滚不完整。\n\n" "FBXTo3dsMax installation failed and rollback is incomplete.\n\n") +
                    (localized "当前插件磁盘文件或运行状态没有完全恢复。为避免继续产生旧包与新用户文件混合状态，请先保留诊断日志并重新启动 3ds Max。" "Plug-in files or runtime state were not fully restored. Preserve the diagnostic log and restart 3ds Max before retrying.") +
                    (localized "\n\n未恢复项目：" "\n\nItems not restored: ") + (rollbackFailures.count as string) + (localized " 项" " item(s)") +
                    rollbackPreview +
                    (localized "\n\n完整诊断日志：\n" "\n\nFull diagnostic log:\n") + logPath
                )
            )
        )
        -- 文件锁在任何结果对话框之前释放；即使用户长时间不关闭对话框，
        -- 也不会阻塞另一个 Max 会话中的安全安装/卸载。
        F2M_Installer_FinalDialogTitle = finalDialogTitle
        F2M_Installer_FinalDialogText = finalDialogText
        releasePackageMutationLock()
        if finalDialogText != "" do
            messageBox finalDialogText title:finalDialogTitle
    )
)
