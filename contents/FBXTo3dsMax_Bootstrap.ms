/*
FBXTo3dsMax v1.4.24 启动引导。

这里只注册稳定的 MacroScript 和顶部按钮；主窗口只会在用户点击按钮后打开。
*/

global FBXTo3dsMax_Bootstrap

struct FBXTo3dsMax_BootstrapStruct
(
    version = "1.4.24",
    contentDir = getFilenamePath (getSourceFileName()),
    callbackId = #FBXTo3dsMax_Toolbar,
    lastError = "",
    shutdownInProgress = false,

    fn writeBootstrapLog message =
    (
        format "[FBXTo3dsMax] %\n" message
    ),

    fn sha256File filePath =
    (
        local fileClass = dotNetClass "System.IO.File"
        local shaClass = dotNetClass "System.Security.Cryptography.SHA256"
        local bitConverter = dotNetClass "System.BitConverter"
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
        catch
        (
            result = ""
        )

        try(if stream != undefined do stream.Close())catch()
        try(if sha != undefined do sha.Dispose())catch()
        result
    ),

    fn textContainsAll filePath tokens =
    (
        local fileClass = dotNetClass "System.IO.File"
        if not fileClass.Exists filePath do return false
        local content = ""
        try(content = toLower (fileClass.ReadAllText filePath))catch(return false)
        for token in tokens where findString content (toLower token) == undefined do return false
        true
    ),

    fn copyVerified sourcePath destinationPath ownershipTokens:#() =
    (
        local fileClass = dotNetClass "System.IO.File"
        local directoryClass = dotNetClass "System.IO.Directory"
        local pathClass = dotNetClass "System.IO.Path"

        if not fileClass.Exists sourcePath do
        (
            writeBootstrapLog ("缺少源文件：" + sourcePath)
            return false
        )

        local parentDir = pathClass.GetDirectoryName destinationPath
        if not directoryClass.Exists parentDir do directoryClass.CreateDirectory parentDir

        local sourceHash = sha256File sourcePath
        local destinationHash = sha256File destinationPath
        if sourceHash == "" do return false

        if sourceHash != destinationHash do
        (
            if fileClass.Exists destinationPath and ownershipTokens.count > 0 and (not (textContainsAll destinationPath ownershipTokens)) do
            (
                writeBootstrapLog ("文件归属冲突，已保留原文件：" + destinationPath)
                return false
            )
            try
            (
                fileClass.Copy sourcePath destinationPath true
            )
            catch
            (
                writeBootstrapLog ("无法更新文件：" + destinationPath + " | " + (getCurrentException()))
                return false
            )
        )

        (sha256File destinationPath) == sourceHash
    ),

    fn installMacro =
    (
        local macroSource = pathConfig.appendPath contentDir "FBXTo3dsMax.mcr"
        -- 3ds Max 会把已求值的宏保存为“类别-宏名.mcr”。
        -- 直接使用规范文件名，避免启动时扫描两个副本。
        local macroTarget = pathConfig.appendPath (getDir #userMacros) "FBXTo3dsMax-FBXTo3dsMax_Open.mcr"

        if not copyVerified macroSource macroTarget ownershipTokens:#(
            "macroScript FBXTo3dsMax_Open",
            "category:\"FBXTo3dsMax\""
        ) do return false

        try
        (
            fileIn macroTarget quiet:true
            true
        )
        catch
        (
            writeBootstrapLog ("无法注册 MacroScript：" + (getCurrentException()))
            false
        )
    ),

    fn installIcons =
    (
        local iconSource = pathConfig.appendPath contentDir "icons\\FBXTo3dsMax.svg"
        local userIconRoot = getDir #userIcons
        local lightTarget = pathConfig.appendPath userIconRoot "Light\\FBXTo3dsMax\\FBXTo3dsMax.svg"
        local darkTarget = pathConfig.appendPath userIconRoot "Dark\\FBXTo3dsMax\\FBXTo3dsMax.svg"
        local iconTokens = #("<svg", "<title>FBXTo3dsMax</title>")
        local lightOk = copyVerified iconSource lightTarget ownershipTokens:iconTokens
        local darkOk = copyVerified iconSource darkTarget ownershipTokens:iconTokens
        lightOk and darkOk
    ),

    fn ensureToolbar =
    (
        -- 退出期间 Max 仍可能保存 CUI 并发送 postSavingCuiToolbars。
        -- 此时 Qt 主窗口正被拆除，绝不能重新创建按钮或安排延迟回调。
        if shutdownInProgress do return true

        local toolbarScript = pathConfig.appendPath contentDir "f2m_toolbar.py"
        if not doesFileExist toolbarScript do
        (
            writeBootstrapLog ("缺少工具栏脚本：" + toolbarScript)
            return false
        )

        try
        (
            lastError = ""
            -- 通过绝对路径装载为独立模块，避免 python.ExecuteFile 共用
            -- __main__.__file__ 与 Qt 延迟回调发生时序冲突。
            local escapedPath = substituteString toolbarScript "\\" "\\\\"
            escapedPath = substituteString escapedPath "'" "\\'"
            local pythonCode =
                "import builtins, importlib.util, os, sys\n" +
                "_f2m_toolbar_path = os.path.abspath('" + escapedPath + "')\n" +
                "_f2m_toolbar_name = '_fbx_to_3dsmax_toolbar_runtime'\n" +
                "_f2m_toolbar_module = sys.modules.get(_f2m_toolbar_name)\n" +
                "_f2m_toolbar_origin = os.path.abspath(getattr(_f2m_toolbar_module, '__file__', '') or '') if _f2m_toolbar_module else ''\n" +
                "if _f2m_toolbar_module is None or os.path.normcase(_f2m_toolbar_origin) != os.path.normcase(_f2m_toolbar_path) or str(getattr(_f2m_toolbar_module, 'TOOL_VERSION', '')) != '1.4.24' or getattr(_f2m_toolbar_module, '_F2M_IMPORT_COMPLETE', False) is not True or not callable(getattr(_f2m_toolbar_module, 'install_and_schedule', None)):\n" +
                "    _f2m_old_api = getattr(builtins, '_FBXTO3DSMAX_TOOLBAR_API', None)\n" +
                "    if _f2m_old_api:\n" +
                "        _f2m_old_api.get('uninstall', lambda: 0)()\n" +
                "    sys.modules.pop(_f2m_toolbar_name, None)\n" +
                "    _f2m_toolbar_spec = importlib.util.spec_from_file_location(_f2m_toolbar_name, _f2m_toolbar_path)\n" +
                "    if _f2m_toolbar_spec is None or _f2m_toolbar_spec.loader is None:\n" +
                "        raise RuntimeError('无法创建工具栏模块加载器。')\n" +
                "    _f2m_toolbar_module = importlib.util.module_from_spec(_f2m_toolbar_spec)\n" +
                "    sys.modules[_f2m_toolbar_name] = _f2m_toolbar_module\n" +
                "    try:\n" +
                "        _f2m_toolbar_spec.loader.exec_module(_f2m_toolbar_module)\n" +
                "    except BaseException:\n" +
                "        if sys.modules.get(_f2m_toolbar_name) is _f2m_toolbar_module:\n" +
                "            sys.modules.pop(_f2m_toolbar_name, None)\n" +
                "        raise\n" +
                "    setattr(_f2m_toolbar_module, '_F2M_IMPORT_COMPLETE', True)\n" +
                "if os.path.normcase(os.path.abspath(_f2m_toolbar_module.__file__)) != os.path.normcase(_f2m_toolbar_path):\n" +
                "    raise RuntimeError('工具栏模块来源校验失败。')\n" +
                "if str(getattr(_f2m_toolbar_module, 'TOOL_VERSION', '')) != '1.4.24':\n" +
                "    raise RuntimeError('Toolbar module version mismatch.')\n" +
                "_f2m_toolbar_status = _f2m_toolbar_module.install_and_schedule()\n" +
                "if not _f2m_toolbar_status.get('ok', False):\n" +
                "    raise RuntimeError(_f2m_toolbar_status.get('message', '顶部按钮验证失败。'))\n"
            -- 注意：python.Execute 的 fileName: 并非“诊断文件名”；Autodesk
            -- 的实现会在提供该参数时改为执行指定文件，并忽略前面的代码
            -- 字符串。这里必须执行上面的装载与 install_and_schedule() 代码。
            local result = python.Execute pythonCode throwOnError:true clearUndoBuffer:false
            result == #success
        )
        catch
        (
            lastError = getCurrentException()
            writeBootstrapLog ("无法创建顶部按钮：" + lastError)
            false
        )
    ),

    fn verifyToolbar =
    (
        if shutdownInProgress do return true

        try
        (
            local pythonCode =
                "import builtins\n" +
                "_f2m_toolbar_api = getattr(builtins, '_FBXTO3DSMAX_TOOLBAR_API', None)\n" +
                "if not _f2m_toolbar_api:\n" +
                "    raise RuntimeError('工具栏运行接口不存在。')\n" +
                "_f2m_toolbar_status = _f2m_toolbar_api.get('verify', lambda: {'ok': False, 'message': '缺少验证函数。'})()\n" +
                "if not _f2m_toolbar_status.get('ok', False):\n" +
                "    raise RuntimeError(_f2m_toolbar_status.get('message', '顶部按钮验证失败。'))\n"
            (python.Execute pythonCode throwOnError:true clearUndoBuffer:false) == #success
        )
        catch
        (
            lastError = getCurrentException()
            writeBootstrapLog ("顶部按钮验证失败：" + lastError)
            false
        )
    ),

    fn suspendToolbar =
    (
        try
        (
            python.Execute "import builtins\n_f2m_api = getattr(builtins, '_FBXTO3DSMAX_TOOLBAR_API', None)\nif _f2m_api:\n    _f2m_api.get('suspend', lambda: 0)()\n" throwOnError:true clearUndoBuffer:false
            true
        )
        catch
        (
            writeBootstrapLog ("临时移除顶部按钮失败：" + (getCurrentException()))
            false
        )
    ),

    fn beginSystemShutdown =
    (
        if shutdownInProgress do return true
        shutdownInProgress = true
        try
        (
            python.Execute "import builtins\n_f2m_api = getattr(builtins, '_FBXTO3DSMAX_TOOLBAR_API', None)\nif _f2m_api:\n    _f2m_api.get('begin_shutdown', lambda: 0)()\n" throwOnError:true clearUndoBuffer:false
            true
        )
        catch
        (
            -- 退出阶段不再访问可能已经拆除的界面，也不尝试重建按钮。
            false
        )
    ),

    fn cancelSystemShutdown =
    (
        local wasShuttingDown = shutdownInProgress
        shutdownInProgress = false
        try
        (
            python.Execute "import builtins\n_f2m_api = getattr(builtins, '_FBXTO3DSMAX_TOOLBAR_API', None)\nif _f2m_api:\n    _f2m_api.get('cancel_shutdown', lambda: 0)()\n" throwOnError:true clearUndoBuffer:false
        )
        catch()

        if wasShuttingDown then ensureToolbar() else true
    ),

    fn restoreToolbarAfterCui =
    (
        if shutdownInProgress then true else ensureToolbar()
    ),

    fn removeToolbar =
    (
        try
        (
            python.Execute "import builtins\n_f2m_api = getattr(builtins, '_FBXTO3DSMAX_TOOLBAR_API', None)\nif _f2m_api:\n    _f2m_api.get('uninstall', lambda: 0)()\n" throwOnError:true clearUndoBuffer:false
            true
        )
        catch(false)
    ),

    fn registerCallbacks =
    (
        callbacks.removeScripts id:callbackId
        callbacks.addScript #preWorkspaceChange "try(::FBXTo3dsMax_Bootstrap.suspendToolbar())catch()" id:callbackId persistent:false
        callbacks.addScript #postWorkspaceChange "try(::FBXTo3dsMax_Bootstrap.ensureToolbar())catch()" id:callbackId persistent:false
        callbacks.addScript #preLoadingCuiToolbars "try(::FBXTo3dsMax_Bootstrap.suspendToolbar())catch()" id:callbackId persistent:false
        callbacks.addScript #postLoadingCuiToolbars "try(::FBXTo3dsMax_Bootstrap.restoreToolbarAfterCui())catch()" id:callbackId persistent:false
        callbacks.addScript #preSavingCuiToolbars "try(::FBXTo3dsMax_Bootstrap.suspendToolbar())catch()" id:callbackId persistent:false
        callbacks.addScript #postSavingCuiToolbars "try(::FBXTo3dsMax_Bootstrap.restoreToolbarAfterCui())catch()" id:callbackId persistent:false
        -- Max 2023+ 会先广播“可能退出”；若用户取消退出，再明确恢复按钮。
        -- 一旦检查通过，后续 CUI 保存回调只能保持停用状态。
        callbacks.addScript #systemShutdownCheck "try(::FBXTo3dsMax_Bootstrap.beginSystemShutdown())catch()" id:callbackId persistent:false
        callbacks.addScript #systemShutdownCheckFailed "try(::FBXTo3dsMax_Bootstrap.cancelSystemShutdown())catch()" id:callbackId persistent:false
        callbacks.addScript #systemShutdownCheckPassed "try(::FBXTo3dsMax_Bootstrap.beginSystemShutdown())catch()" id:callbackId persistent:false
        callbacks.addScript #preSystemShutdown "try(::FBXTo3dsMax_Bootstrap.beginSystemShutdown())catch()" id:callbackId persistent:false
        callbacks.addScript #postAppThemeChange "try(::FBXTo3dsMax_Bootstrap.ensureToolbar())catch()" id:callbackId persistent:false
        -- 某些版本/工作区会在欢迎界面关闭后再次构建主工具栏。
        -- Max 版本若不支持该通知，忽略此项且不影响其它启动回调。
        try
        (
            callbacks.addScript #welcomeScreenDone "try(::FBXTo3dsMax_Bootstrap.ensureToolbar())catch()" id:callbackId persistent:false
        )
        catch
        (
            writeBootstrapLog "当前 3ds Max 不支持欢迎界面完成回调，已使用其它工具栏恢复回调。"
        )
        true
    ),

    fn shutdown removeToolbarUI:true =
    (
        callbacks.removeScripts id:callbackId
        if removeToolbarUI do removeToolbar()
        true
    ),

    fn startup =
    (
        shutdownInProgress = false
        local macroOk = installMacro()
        local iconsOk = installIcons()
        local callbacksOk = false
        local toolbarOk = false

        if macroOk then
        (
            callbacksOk = registerCallbacks()
            toolbarOk = ensureToolbar()
        )
        else
        (
            -- 如果同名宏因归属检查而被保留，不能显示一个可能调用未知宏的按钮。
            shutdown()
        )

        if not iconsOk do writeBootstrapLog "一个或多个可选图标副本未能更新。"
        if macroOk and callbacksOk and toolbarOk and verifyToolbar() then
        (
            true
        )
        else
        (
            local startupSummary = (
                "启动引导未完成。宏脚本=" + (macroOk as string) +
                " 回调=" + (callbacksOk as string) +
                " 顶部按钮=" + (toolbarOk as string)
            )
            if lastError == "" do lastError = startupSummary
            writeBootstrapLog (startupSummary + " | " + lastError)
            false
        )
    )
)

try
(
    if FBXTo3dsMax_Bootstrap != undefined do FBXTo3dsMax_Bootstrap.shutdown()
)
catch()

FBXTo3dsMax_Bootstrap = FBXTo3dsMax_BootstrapStruct()
(
    local FBXTo3dsMax_IsSelfCheckChild = false
    local FBXTo3dsMax_IsBatchSession = false
    try
    (
        FBXTo3dsMax_IsSelfCheckChild =
            (systemTools.getEnvVariable "F2M_SELFCHECK_CHILD") == "1"
    )
    catch()
    try
    (
        for argument in sysInfo.getCommandLineArgs() where
            (toLower argument) == "-batch" do
        (
            FBXTo3dsMax_IsBatchSession = true
        )
    )
    catch()

    if FBXTo3dsMax_IsSelfCheckChild or FBXTo3dsMax_IsBatchSession then
    (
        -- Batch 和独立自检进程不需要任何界面控件。跳过 Qt 工具栏可减少
        -- 启动时间，也避免无界面的进程持有延迟界面回调。
        FBXTo3dsMax_Bootstrap.writeBootstrapLog "批处理进程已跳过顶部按钮初始化。"
        true
    )
    else
    (
        FBXTo3dsMax_Bootstrap.startup()
    )
)
