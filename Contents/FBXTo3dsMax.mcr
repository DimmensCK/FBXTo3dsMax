macroScript FBXTo3dsMax_Open
category:"FBXTo3dsMax"
internalCategory:"FBXTo3dsMax"
buttonText:"FBX 转 MAX"
toolTip:"打开 FBXTo3dsMax"
iconName:"FBXTo3dsMax/FBXTo3dsMax"
autoUndoEnabled:false
(
    on execute do
    (
        try
        (
            local packageRoot = pathConfig.appendPath (getDir #privateExchangeStoreInstallPath) "FBXTo3dsMax"
            local uiPath = pathConfig.appendPath packageRoot "Contents\\FBXTo3dsMax_UI.ms"

            if not doesFileExist uiPath then
            (
                messageBox ("FBXTo3dsMax 安装不完整。\n\n缺少文件：\n" + uiPath + "\n\n请重新运行 Install_FBXTo3dsMax.ms。") title:"FBXTo3dsMax"
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
            messageBox "无法打开 FBXTo3dsMax。请重新安装插件；如果问题仍存在，请保留安装日志。" title:"FBXTo3dsMax"
        )
    )
)
