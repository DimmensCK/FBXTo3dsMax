macroScript FBXTo3dsMax_Open
category:"FBXTo3dsMax"
internalCategory:"FBXTo3dsMax"
buttonText:"FBXTo3dsMax"
toolTip:"FBXTo3dsMax"
iconName:"FBXTo3dsMax/FBXTo3dsMax"
autoUndoEnabled:false
(
    fn localizedMessage text packageRoot =
    (
        global F2M_Macro_LocalizedText
        F2M_Macro_LocalizedText = text
        local languagePath = pathConfig.appendPath packageRoot "contents\\f2m_i18n.py"
        if not doesFileExist languagePath do return text
        local escapedPath = substituteString languagePath "\\" "\\\\"
        escapedPath = substituteString escapedPath "'" "\\'"
        try
        (
            local code =
                "import importlib.util, os, sys\nfrom pymxs import runtime as rt\n" +
                "p = os.path.abspath('" + escapedPath + "')\nname = '_fbx_to_3dsmax_i18n_runtime'\nm = sys.modules.get(name)\n" +
                "if m is None or os.path.normcase(os.path.abspath(getattr(m, '__file__', '') or '')) != os.path.normcase(p) or getattr(m, 'TOOL_VERSION', '') != '1.4.26' or getattr(m, '_F2M_IMPORT_COMPLETE', False) is not True:\n" +
                "    sys.modules.pop(name, None)\n    spec = importlib.util.spec_from_file_location(name, p)\n" +
                "    if spec is None or spec.loader is None: raise RuntimeError('Language loader missing')\n" +
                "    m = importlib.util.module_from_spec(spec)\n    sys.modules[name] = m\n" +
                "    try: spec.loader.exec_module(m)\n    except BaseException:\n        if sys.modules.get(name) is m: sys.modules.pop(name, None)\n        raise\n" +
                "if os.path.normcase(os.path.abspath(m.__file__)) != os.path.normcase(p) or getattr(m, 'TOOL_VERSION', '') != '1.4.26' or getattr(m, '_F2M_IMPORT_COMPLETE', False) is not True or not callable(getattr(m, 'translate', None)): raise RuntimeError('Language identity/version/API mismatch')\n" +
                "rt.globalVars.set(rt.Name('F2M_Macro_LocalizedText'), m.translate(str(rt.globalVars.get(rt.Name('F2M_Macro_LocalizedText')))))\n"
            python.Execute code throwOnError:true clearUndoBuffer:false
            F2M_Macro_LocalizedText
        )
        catch(text)
    )

    on execute do
    (
        try
        (
            local packageRoot = pathConfig.appendPath (getDir #privateExchangeStoreInstallPath) "FBXTo3dsMax"
            local uiPath = pathConfig.appendPath packageRoot "contents\\FBXTo3dsMax_UI.ms"

            if not doesFileExist uiPath then
            (
                messageBox (localizedMessage ("FBXTo3dsMax 安装不完整。\n\n缺少文件：\n" + uiPath + "\n\n请重新运行 Install_FBXTo3dsMax.ms。") packageRoot) title:"FBXTo3dsMax"
            )
            else
            (
                -- A development copy may already have imported these names from
                -- another folder.  Remove only this plug-in's modules so the UI
                -- imports the canonical installed copy.
                try
                (
                    python.Execute "import sys\nfor _f2m_name in ('b2m_topology_transfer', 'b2m_skin_replace', 'f2m_topology_transfer', 'f2m_skin_replace', 'f2m_smoothing', 'f2m_fbx_metadata', 'f2m_selfcheck', '_fbx_to_3dsmax_toolbar_runtime', '_fbx_to_3dsmax_topology_runtime', '_fbx_to_3dsmax_skin_runtime', '_fbx_to_3dsmax_selfcheck_runtime', '_f2m_smoothing_runtime', '_f2m_fbx_metadata_runtime', '_f2m_sc_fbx_metadata_integrity', '_f2m_sc_fbx_metadata_runtime'):\n    sys.modules.pop(_f2m_name, None)\n" throwOnError:true clearUndoBuffer:false
                )
                catch()

                fileIn uiPath quiet:true
            )
        )
        catch
        (
            local failedPackageRoot = pathConfig.appendPath (getDir #privateExchangeStoreInstallPath) "FBXTo3dsMax"
            messageBox (localizedMessage "无法打开 FBXTo3dsMax。请重新安装插件；如果问题仍存在，请保留安装日志。" failedPackageRoot) title:"FBXTo3dsMax"
        )
    )
)
