/*
FBX 到 3ds Max 数据传递工具
中文 / English 启动界面
*/

try(destroyDialog F2M_Transfer_Rollout)catch()

global F2M_UI_RunStatus
global F2M_UI_LanguageCode
global F2M_UI_SourceTexts
global F2M_UI_EnglishTexts

rollout F2M_Transfer_Rollout "FBX 到 3ds Max 数据传递" width:460 height:466
(
    local toolAuthor = "Dimmens"
    local toolVersion = "1.4.26"
    local scriptDir = getFilenamePath (getSourceFileName())
    local pyTopologyFile = scriptDir + "f2m_topology_transfer.py"
    local pyReplaceFile = scriptDir + "f2m_skin_replace.py"
    local pySelfCheckFile = scriptDir + "f2m_selfcheck.py"
    local pyLanguageFile = scriptDir + "f2m_i18n.py"
    local currentLanguage = "zh-CN"
    local changingLanguage = false
    local warningTextSource = "传递数据前优先检查 FBX，报告无异常后再执行；正式执行前建议保存 Max 文件。"
    local currentMode = 1
    local advancedOpen = false
    local checkDone = false
    local checkedKey = ""
    local lastFbxKey = ""
    local executeConfirmSelectionKey = ""


    groupBox grp_mode "选择模式" pos:[12,12] width:436 height:92
    label lbl_language "Language" pos:[270,16] width:60 height:16
    checkbutton btn_language_zh "中文" pos:[334,12] width:44 height:22 checked:true toolTip:"中文"
    checkbutton btn_language_en "EN" pos:[382,12] width:44 height:22 checked:false toolTip:"English"
    dotNetControl btn_mode_topo "System.Windows.Forms.Button" pos:[28,38] width:190 height:48
    dotNetControl btn_mode_replace "System.Windows.Forms.Button" pos:[238,38] width:190 height:48

    groupBox grp_file "FBX 文件" pos:[12,112] width:436 height:86
    editText edt_fbx "FBX 文件：" pos:[24,138] width:330 height:20 text:""
    button btn_pick "选择..." pos:[360,136] width:70 height:24
    label lbl_target "传递数据前优先检查 FBX" pos:[24,170] width:286 height:24
    button btn_check "检查 FBX/匹配" pos:[306,168] width:124 height:24

    groupBox grp_topo "传递数据" pos:[12,208] width:436 height:116
    checkbox chk_shape "变形" pos:[28,234] width:80 height:18 checked:true
    checkbox chk_matid "材质与 ID" pos:[138,234] width:100 height:18 checked:false
    checkbox chk_normals "顶点法线" pos:[258,234] width:110 height:18 checked:false
    checkbox chk_uv1 "传递 UV 1" pos:[28,260] width:110 height:18 checked:false
    checkbox chk_uv2 "传递 UV 2" pos:[158,260] width:110 height:18 checked:false
    checkbox chk_uv3 "传递 UV 3" pos:[288,260] width:110 height:18 checked:false
    checkbox chk_vc "顶点色 RGB" pos:[28,286] width:130 height:18 checked:false
    checkbox chk_alpha "顶点 Alpha" pos:[166,286] width:130 height:18 checked:false
    checkbox chk_smoothing "光滑组" pos:[306,286] width:125 height:18 checked:false

    groupBox grp_replace "替换网格并保留蒙皮" pos:[12,208] width:436 height:150 visible:false
    label lbl_replace_1 "使用 FBX 目标网格替换所选 Max 源模型；一对一可直接匹配，其它情况按同名匹配。" pos:[28,236] width:390 height:32 visible:false
    label lbl_replace_2 "双方必须带 Skin。Max 源 Skin 提供场景骨骼与绑定数据；FBX 提供逐顶点权重、Unnormalized 和 DQ 数据。" pos:[28,280] width:390 height:60 visible:false

    button btn_advanced "高级选项..." pos:[24,330] width:120 height:24
    button btn_selfcheck "运行插件自检" pos:[306,330] width:124 height:24
    groupBox grp_advanced "高级选项" pos:[12,364] width:436 height:74 visible:false
    checkbox chk_backup "替换时隐藏备份旧网格" pos:[28,390] width:190 height:18 checked:true visible:false
    checkbox chk_keep_mat "兼容：改用 Max 源材质" pos:[238,390] width:180 height:18 checked:false visible:false
    checkbox chk_keep_imported "保留临时导入节点用于排查" pos:[28,416] width:200 height:18 checked:false visible:false
    checkbox chk_hidden "允许处理隐藏对象" pos:[238,416] width:150 height:18 checked:true visible:false

    label lbl_warn "传递数据前优先检查 FBX，报告无异常后再执行；正式执行前建议保存 Max 文件。" pos:[24,364] width:410 height:44
    button btn_run "开始执行" pos:[155,396] width:150 height:26
    label lbl_meta "作者：Dimmens    版本：1.4.26" pos:[24,430] width:410 height:14

    fn pyString s =
    (
        local t = s as string
        t = substituteString t "\\" "\\\\"
        t = substituteString t "\"" "\\\""
        t = substituteString t "\r\n" "\\n"
        t = substituteString t "\r" "\\n"
        t = substituteString t "\n" "\\n"
        t = substituteString t "\t" "\\t"
        "\"" + t + "\""
    )

    fn initializeLanguage requestedLocale:undefined persist:true =
    (
        local code = "import os, sys, importlib.util, builtins\nfrom pymxs import runtime as rt\n"
        code += "p = os.path.abspath(" + pyString pyLanguageFile + ")\nname = '_fbx_to_3dsmax_i18n_runtime'\nm = sys.modules.get(name)\n"
        code += "if m is None or os.path.normcase(os.path.abspath(getattr(m, '__file__', '') or '')) != os.path.normcase(p) or getattr(m, 'TOOL_VERSION', '') != '1.4.26' or getattr(m, '_F2M_IMPORT_COMPLETE', False) is not True:\n"
        code += "    sys.modules.pop(name, None)\n    spec = importlib.util.spec_from_file_location(name, p)\n"
        code += "    if spec is None or spec.loader is None: raise RuntimeError('Language module loader missing')\n"
        code += "    m = importlib.util.module_from_spec(spec)\n    sys.modules[name] = m\n"
        code += "    try: spec.loader.exec_module(m)\n    except BaseException:\n        if sys.modules.get(name) is m: sys.modules.pop(name, None)\n        raise\n"
        code += "if os.path.normcase(os.path.abspath(m.__file__)) != os.path.normcase(p) or getattr(m, 'TOOL_VERSION', '') != '1.4.26' or getattr(m, '_F2M_IMPORT_COMPLETE', False) is not True: raise RuntimeError('Language module identity/version mismatch')\n"
        code += "for api in ('translate', 'get_language', 'set_language', 'ui_catalog_sources', 'ui_catalog_english'):\n    if not callable(getattr(m, api, None)): raise RuntimeError('Language API missing: ' + api)\n"
        if requestedLocale != undefined do
            code += "m.set_language(" + pyString requestedLocale + ", persist=False)\n"
        code += "rt.globalVars.set(rt.Name('F2M_UI_LanguageCode'), m.get_language())\n"
        code += "rt.globalVars.set(rt.Name('F2M_UI_SourceTexts'), rt.Array(*m.ui_catalog_sources()))\n"
        code += "rt.globalVars.set(rt.Name('F2M_UI_EnglishTexts'), rt.Array(*m.ui_catalog_english()))\n"
        code += "api = getattr(builtins, '_FBXTO3DSMAX_TOOLBAR_API', None)\nif isinstance(api, dict) and callable(api.get('refresh_language')): api['refresh_language']()\n"
        python.Execute code throwOnError:true clearUndoBuffer:false
        if F2M_UI_LanguageCode != "zh-CN" and F2M_UI_LanguageCode != "en" do throw "Unsupported language readback"
        currentLanguage = F2M_UI_LanguageCode
        if requestedLocale != undefined and currentLanguage != requestedLocale do throw "Language preview readback mismatch"
        if requestedLocale != undefined and persist do
        (
            -- Commit only after catalog, toolbar and native language readback succeed.
            local commitCode = "import os, sys\n"
            commitCode += "p = os.path.abspath(" + pyString pyLanguageFile + ")\nname = '_fbx_to_3dsmax_i18n_runtime'\nm = sys.modules.get(name)\n"
            commitCode += "if m is None or os.path.normcase(os.path.abspath(getattr(m, '__file__', '') or '')) != os.path.normcase(p) or getattr(m, 'TOOL_VERSION', '') != '1.4.26' or getattr(m, '_F2M_IMPORT_COMPLETE', False) is not True: raise RuntimeError('Language commit module identity/version mismatch')\n"
            commitCode += "for api in ('get_language', 'set_language'):\n    if not callable(getattr(m, api, None)): raise RuntimeError('Language commit API missing: ' + api)\n"
            commitCode += "chosen = " + pyString currentLanguage + "\nif chosen not in ('zh-CN', 'en') or m.get_language() != chosen: raise RuntimeError('Language commit preview mismatch')\n"
            commitCode += "m.set_language(chosen, persist=True)\n"
            python.Execute commitCode throwOnError:true clearUndoBuffer:false
        )
        currentLanguage
    )

    fn tr sourceText =
    (
        if currentLanguage == "en" and F2M_UI_SourceTexts != undefined and F2M_UI_EnglishTexts != undefined then
        (
            local index = findItem F2M_UI_SourceTexts sourceText
            if index > 0 and index <= F2M_UI_EnglishTexts.count then F2M_UI_EnglishTexts[index] else sourceText
        )
        else sourceText
    )

    fn setWarning sourceText =
    (
        warningTextSource = sourceText
        lbl_warn.text = tr sourceText
    )

    fn selectedUvText =
    (
        local parts = #()
        if chk_uv1.checked do append parts "1"
        if chk_uv2.checked do append parts "2"
        if chk_uv3.checked do append parts "3"

        local out = ""
        for i = 1 to parts.count do
        (
            if i > 1 do out += ","
            out += parts[i]
        )
        out
    )

    fn pyBool b =
    (
        if b then "True" else "False"
    )

    fn writeUiDiagnostic errorText =
    (
        try
        (
            local environmentClass = dotNetClass "System.Environment"
            local directoryClass = dotNetClass "System.IO.Directory"
            local fileClass = dotNetClass "System.IO.File"
            local pathClass = dotNetClass "System.IO.Path"
            local dateTimeClass = dotNetClass "System.DateTime"
            local guidClass = dotNetClass "System.Guid"
            local localRoot = environmentClass.GetEnvironmentVariable "LOCALAPPDATA"
            if localRoot == undefined or localRoot == "" do localRoot = getDir #temp

            local nowValue = dateTimeClass.Now
            local diagnosticFolder = pathClass.Combine localRoot ("FBXTo3dsMax\\Diagnostics\\" + nowValue.ToString("yyyy-MM-dd"))
            directoryClass.CreateDirectory diagnosticFolder
            local token = substituteString ((guidClass.NewGuid()).ToString()) "-" ""
            local diagnosticPath = pathClass.Combine diagnosticFolder ("FBXTo3dsMax_UI_" + nowValue.ToString("yyyyMMdd_HHmmss") + "_" + token + "_内部诊断.txt")
            local diagnosticText = (
                "FBXTo3dsMax 界面内部诊断\r\n" +
                "版本：" + toolVersion + "\r\n" +
                "时间：" + nowValue.ToString("yyyy-MM-dd HH:mm:ss") + "\r\n" +
                "脚本：" + (getSourceFileName() as string) + "\r\n" +
                "异常：\r\n" + (errorText as string) + "\r\n"
            )
            local utf8NoBom = dotNetObject "System.Text.UTF8Encoding" false
            fileClass.WriteAllText diagnosticPath diagnosticText utf8NoBom
            diagnosticPath
        )
        catch
        (
            ""
        )
    )

    fn dotNetColor r g b =
    (
        (dotNetClass "System.Drawing.Color").FromArgb r g b
    )

    fn setModeButtonVisual btn isSelected title subtitle =
    (
        local flatStyle = dotNetClass "System.Windows.Forms.FlatStyle"
        local textAlign = dotNetClass "System.Drawing.ContentAlignment"
        try(btn.UseVisualStyleBackColor = false)catch()
        try(btn.FlatStyle = flatStyle.Flat)catch()
        try(btn.TextAlign = textAlign.MiddleCenter)catch()
        try(btn.Text = (title + "\r\n" + subtitle))catch()
        try(btn.BackColor = if isSelected then (dotNetColor 38 118 214) else (dotNetColor 218 218 218))catch()
        try(btn.ForeColor = if isSelected then (dotNetColor 255 255 255) else (dotNetColor 86 86 86))catch()
        try(btn.FlatAppearance.BorderColor = if isSelected then (dotNetColor 20 84 168) else (dotNetColor 160 160 160))catch()
        try(btn.FlatAppearance.BorderSize = if isSelected then 2 else 1)catch()
    )

    fn layoutDialog =
    (
        local dataBottom = if currentMode == 2 then (grp_replace.pos.y + grp_replace.height) else (grp_topo.pos.y + grp_topo.height)
        local advancedButtonY = dataBottom + 6
        local nextY = advancedButtonY + 34

        btn_advanced.pos = [24,advancedButtonY]
        btn_selfcheck.pos = [306,advancedButtonY]

        if advancedOpen then
        (
            grp_advanced.pos = [12,nextY]
            chk_backup.pos = [28,nextY + 26]
            chk_keep_mat.pos = [238,nextY + 26]
            chk_keep_imported.pos = [28,nextY + 52]
            chk_hidden.pos = [238,nextY + 52]
            nextY += 88
        )

        lbl_warn.pos = [24,nextY]
        btn_run.pos = [155,nextY + 48]
        lbl_meta.pos = [24,nextY + 82]
        try(setDialogSize F2M_Transfer_Rollout [460,nextY + 108])catch()
    )

    fn safeLower s =
    (
        local t = s as string
        try(t = toLower t)catch()
        t
    )

    fn normalizedFbxPath =
    (
        local p = edt_fbx.text as string
        try(p = pathConfig.convertPathToAbsolute p)catch()
        safeLower p
    )

    fn fbxFileFingerprint =
    (
        local p = edt_fbx.text as string
        try(p = pathConfig.convertPathToAbsolute p)catch()
        if p == "" or not doesFileExist p then return (safeLower p + "|missing")
        try
        (
            local info = dotNetObject "System.IO.FileInfo" p
            safeLower p + "|" + (info.Length as string) + "|" + (info.LastWriteTimeUtc.Ticks as string)
        )
        catch
        (
            safeLower p + "|unreadable"
        )
    )

    fn selectedTargetsKey =
    (
        local handles = #()
        for n in selection do
        (
            local h = undefined
            try(h = getHandleByAnim n)catch(h = undefined)
            -- 检查缓存只能以稳定句柄为身份。名称不是唯一键；句柄读取失败时
            -- 必须让本次检查失效，不能把同名的另一个节点误当成已检查对象。
            if h == undefined do return ""
            h = h as string
            append handles h
        )
        try(sort handles)catch()

        local out = ""
        for h in handles do out += (h + ";")
        out
    )

    fn currentCheckKey =
    (
        -- 检查验证的是 FBX 目标文件、模式、Max 源模型集合和隐藏对象范围。
        -- 具体传递通道会在正式执行时再次按通道严格验证，不应因为勾选变化
        -- 让已经完成的昂贵拓扑检查失效。
        local targetKey = selectedTargetsKey()
        if targetKey == "" do return ""
        (currentMode as string) + "|" + fbxFileFingerprint() + "|" + (chk_hidden.checked as string) + "|" + targetKey
    )

    fn markNeedCheck =
    (
        checkDone = false
        checkedKey = ""
        setWarning "传递数据前优先检查 FBX，报告无异常后再执行；正式执行前建议保存 Max 文件。"
    )

    fn markOptionsChanged =
    (
        if checkDone do
        (
            setWarning "已检查当前 FBX/选择；只改变传递数据选项时可直接执行。"
        )
    )

    fn markChecked keyValue =
    (
        if keyValue == "" do
        (
            markNeedCheck()
            setWarning "无法取得所选节点的稳定句柄，本次检查结果不会缓存。"
            return false
        )
        checkDone = true
        checkedKey = keyValue
        lastFbxKey = normalizedFbxPath()
        setWarning "已执行检查。请确认报告没有严重错误，再开始执行。"
        true
    )

    fn checkIsCurrent keyValue =
    (
        keyValue != "" and checkDone and (checkedKey == keyValue)
    )

    fn validNodeSafe n =
    (
        try(isValidNode n)catch(false)
    )

    fn captureSelectionHandlesAndNames =
    (
        local handles = #()
        local names = #()
        for n in selection do
        (
            local handleValue = undefined
            local nameValue = ""
            try(handleValue = getHandleByAnim n)catch(handleValue = undefined)
            try(nameValue = n.name as string)catch(nameValue = "")
            append handles handleValue
            append names nameValue
        )
        #(handles, names)
    )

    fn restoreSelectionByHandlesOrNames handles names =
    (
        local restored = #()
        for i = 1 to handles.count do
        (
            local originalName = if i <= names.count then names[i] else ""
            local targetNode = undefined

            if handles[i] != undefined do
            (
                local nodeByHandle = undefined
                try(nodeByHandle = getAnimByHandle handles[i])catch(nodeByHandle = undefined)
                if validNodeSafe nodeByHandle do
                (
                    local sameName = false
                    try(sameName = ((nodeByHandle.name as string) == originalName))catch()
                    if sameName do targetNode = nodeByHandle
                )
            )

            if targetNode == undefined and originalName != "" do
            (
                -- 模式二成功后原句柄会消失，只允许用“唯一的精确同名节点”
                -- 恢复选择。getNodeByName 在重名场景会任意返回一个节点。
                local exactMatches = #()
                try
                (
                    for candidate in objects where validNodeSafe candidate do
                    (
                        local sameName = false
                        try(sameName = ((candidate.name as string) == originalName))catch()
                        if sameName do append exactMatches candidate
                    )
                )
                catch(exactMatches = #())
                if exactMatches.count == 1 do targetNode = exactMatches[1]
                exactMatches = #()
            )

            if validNodeSafe targetNode and (findItem restored targetNode) == 0 do append restored targetNode
        )

        if restored.count > 0 do try(select restored)catch()
        restored.count
    )

    fn confirmRunForSelection =
    (
        local selectionKey = selectedTargetsKey()
        if selectionKey == "" then
        (
            messageBox (tr "无法取得所选节点的稳定句柄。请重新选择 Max 源模型后再试。") title:(tr "FBX 到 3ds Max")
            false
        )
        else
        if executeConfirmSelectionKey == selectionKey then
        (
            true
        )
        else
        (
            local go = queryBox (tr "开始执行前请确认当前 Max 文件已经保存或另存备份。\n\n同一组选中 Max 源模型只会提示一次；更换选中对象后会再次提示。\n\n是否继续？") title:(tr "FBX 到 3ds Max")
            if go do executeConfirmSelectionKey = selectionKey
            go
        )
    )

    fn markFbxChangedIfNeeded =
    (
        local keyValue = normalizedFbxPath()
        if keyValue != lastFbxKey do
        (
            lastFbxKey = keyValue
            markNeedCheck()
        )
    )

    fn setAdvancedVisible state =
    (
        grp_advanced.visible = state
        chk_backup.visible = state
        chk_keep_mat.visible = state
        chk_keep_imported.visible = state
        chk_hidden.visible = state
        btn_advanced.text = tr (if state then "隐藏高级选项" else "高级选项...")
        layoutDialog()
    )

    fn updateModeUI =
    (
        local isReplace = currentMode == 2

        setModeButtonVisual btn_mode_topo (not isReplace) (tr "模型完全一致") (tr "传递数据")
        setModeButtonVisual btn_mode_replace isReplace (tr "模型不一致") (tr "替换并保留蒙皮")

        grp_topo.visible = not isReplace
        chk_shape.visible = not isReplace
        chk_matid.visible = not isReplace
        chk_uv1.visible = not isReplace
        chk_uv2.visible = not isReplace
        chk_uv3.visible = not isReplace
        chk_normals.visible = not isReplace
        chk_smoothing.visible = not isReplace
        chk_vc.visible = not isReplace
        chk_alpha.visible = not isReplace

        grp_replace.visible = isReplace
        lbl_replace_1.visible = isReplace
        lbl_replace_2.visible = isReplace
        layoutDialog()
    )

    fn applyLanguage =
    (
        -- Only display properties change. Cache keys, options and scene identity stay intact.
        changingLanguage = true
        F2M_Transfer_Rollout.title = tr "FBX 到 3ds Max 数据传递"
        btn_language_zh.checked = currentLanguage == "zh-CN"
        btn_language_en.checked = currentLanguage == "en"
        grp_mode.text = tr "选择模式"
        grp_file.text = tr "FBX 文件"
        edt_fbx.caption = tr "FBX 文件："
        btn_pick.text = tr "选择..."
        lbl_target.text = tr "传递数据前优先检查 FBX"
        btn_check.text = tr "检查 FBX/匹配"
        grp_topo.text = tr "传递数据"
        chk_shape.text = tr "变形"
        chk_matid.text = tr "材质与 ID"
        chk_normals.text = tr "顶点法线"
        chk_uv1.text = tr "传递 UV 1"
        chk_uv2.text = tr "传递 UV 2"
        chk_uv3.text = tr "传递 UV 3"
        chk_vc.text = tr "顶点色 RGB"
        chk_alpha.text = tr "顶点 Alpha"
        chk_smoothing.text = tr "光滑组"
        grp_replace.text = tr "替换网格并保留蒙皮"
        lbl_replace_1.text = tr "使用 FBX 目标网格替换所选 Max 源模型；一对一可直接匹配，其它情况按同名匹配。"
        lbl_replace_2.text = tr "双方必须带 Skin。Max 源 Skin 提供场景骨骼与绑定数据；FBX 提供逐顶点权重、Unnormalized 和 DQ 数据。"
        btn_selfcheck.text = tr "运行插件自检"
        grp_advanced.text = tr "高级选项"
        chk_backup.text = tr "替换时隐藏备份旧网格"
        chk_keep_mat.text = tr "兼容：改用 Max 源材质"
        chk_keep_imported.text = tr "保留临时导入节点用于排查"
        chk_hidden.text = tr "允许处理隐藏对象"
        lbl_warn.text = tr warningTextSource
        btn_run.text = tr "开始执行"
        lbl_meta.text = (tr "作者：") + toolAuthor + "    " + (tr "版本：") + toolVersion
        updateModeUI()
        setAdvancedVisible advancedOpen
        changingLanguage = false
        true
    )

    fn switchLanguage requestedLocale =
    (
        if changingLanguage do return false
        local previousLanguage = currentLanguage
        try
        (
            initializeLanguage requestedLocale:requestedLocale persist:false
            applyLanguage()
            initializeLanguage requestedLocale:currentLanguage persist:true
            true
        )
        catch
        (
            local languageError = getCurrentException()
            try(initializeLanguage requestedLocale:previousLanguage persist:false)catch
            (
                languageError += "\nLanguage session/display rollback failed:\n" + getCurrentException()
            )
            currentLanguage = previousLanguage
            try(applyLanguage())catch
            (
                languageError += "\nLanguage control rollback failed:\n" + getCurrentException()
            )
            changingLanguage = false
            local languageDiagnostic = writeUiDiagnostic languageError
            messageBox ((tr "无法保存或切换语言。请保留内部诊断文件。") + "\n\n" + languageDiagnostic) title:"FBXTo3dsMax"
            false
        )
    )

    fn selectedTargetOk =
    (
        if selection.count < 1 then
        (
            messageBox (tr "请先在 Max 场景里选中至少 1 个 Max 源模型网格。") title:(tr "FBX 到 3ds Max")
            false
        )
        else true
    )

    fn runPython dryRun =
    (
        local fbxPath = edt_fbx.text
        local uvText = selectedUvText()
        local transferUv = (uvText != "")
        local isReplace = currentMode == 2
        local pyFile = if isReplace then pyReplaceFile else pyTopologyFile
        local moduleName = if isReplace then "_fbx_to_3dsmax_skin_runtime" else "_fbx_to_3dsmax_topology_runtime"

        if not (selectedTargetOk()) do return false

        if not doesFileExist pyFile then
        (
            messageBox ((tr "找不到 Python 文件：\n") + pyFile) title:(tr "FBX 到 3ds Max")
            return false
        )

        if fbxPath == "" or not doesFileExist fbxPath then
        (
            messageBox (tr "请先选择一个有效的 FBX 文件。") title:(tr "FBX 到 3ds Max")
            return false
        )

        local code = ""
        code += "import os, sys, importlib.util\n"
        code += "_f2m_module_path = os.path.abspath(" + pyString pyFile + ")\n"
        code += "_f2m_module_name = " + pyString moduleName + "\n"
        code += "_f2m_module = sys.modules.get(_f2m_module_name)\n"
        code += "_f2m_loaded_path = os.path.abspath(getattr(_f2m_module, '__file__', '')) if _f2m_module is not None else ''\n"
        code += "_f2m_reuse = (_f2m_module is not None and os.path.normcase(_f2m_loaded_path) == os.path.normcase(_f2m_module_path) and str(getattr(_f2m_module, 'TOOL_VERSION', '')) == " + pyString toolVersion + " and getattr(_f2m_module, '_F2M_IMPORT_COMPLETE', False) is True and callable(getattr(_f2m_module, 'run_from_max', None)))\n"
        code += "if not _f2m_reuse:\n"
        code += "    sys.modules.pop(_f2m_module_name, None)\n"
        code += "    _f2m_spec = importlib.util.spec_from_file_location(_f2m_module_name, _f2m_module_path)\n"
        code += "    if _f2m_spec is None or _f2m_spec.loader is None: raise RuntimeError('无法创建插件模块加载器')\n"
        code += "    _f2m_module = importlib.util.module_from_spec(_f2m_spec)\n"
        code += "    sys.modules[_f2m_module_name] = _f2m_module\n"
        code += "    try:\n"
        code += "        _f2m_spec.loader.exec_module(_f2m_module)\n"
        code += "    except BaseException:\n"
        code += "        if sys.modules.get(_f2m_module_name) is _f2m_module: sys.modules.pop(_f2m_module_name, None)\n"
        code += "        raise\n"
        code += "    setattr(_f2m_module, '_F2M_IMPORT_COMPLETE', True)\n"
        code += "if os.path.normcase(os.path.abspath(_f2m_module.__file__)) != os.path.normcase(_f2m_module_path): raise RuntimeError('插件模块来源不一致')\n"
        code += "_f2m_module.run_from_max(\n"
        code += "    fbx_path=" + pyString fbxPath + ",\n"
        code += "    dry_run=" + pyBool dryRun + ",\n"

        if isReplace then
        (
            code += "    mode='replace',\n"
            code += "    transfer_shape=False,\n"
            code += "    transfer_uv=False,\n"
            code += "    transfer_normals=False,\n"
            code += "    transfer_vertex_color=False,\n"
            code += "    transfer_alpha=False,\n"
            code += "    transfer_material_ids=False,\n"
            code += "    backup_old_mesh=" + pyBool chk_backup.checked + ",\n"
            code += "    keep_target_material_on_replace=" + pyBool chk_keep_mat.checked + ",\n"
        )
        else
        (
            code += "    mode='topology_only',\n"
            code += "    transfer_shape=" + pyBool chk_shape.checked + ",\n"
            code += "    transfer_uv=" + pyBool transferUv + ",\n"
            code += "    uv_channels=" + pyString uvText + ",\n"
            code += "    transfer_normals=" + pyBool chk_normals.checked + ",\n"
            code += "    transfer_smoothing_groups=" + pyBool chk_smoothing.checked + ",\n"
            code += "    transfer_vertex_color=" + pyBool chk_vc.checked + ",\n"
            code += "    transfer_alpha=" + pyBool chk_alpha.checked + ",\n"
            code += "    transfer_material_ids=" + pyBool chk_matid.checked + ",\n"
        )

        code += "    keep_imported=" + pyBool (chk_keep_imported.checked and not dryRun) + ",\n"
        code += "    include_hidden=" + pyBool chk_hidden.checked + "\n"
        code += ")\n"
        code += "__f2m_run_ok = bool(getattr(_f2m_module, 'LAST_RUN_OK', False))\n"
        code += "from pymxs import runtime as _f2m_bridge_rt\n"
        code += "_f2m_bridge_rt.globalVars.set(_f2m_bridge_rt.Name('F2M_UI_RunStatus'), 1 if __f2m_run_ok else 0)\n"

        local succeeded = false
        F2M_UI_RunStatus = -1
        try
        (
            python.Execute code throwOnError:true clearUndoBuffer:false
            succeeded = (F2M_UI_RunStatus == 1)
        )
        catch
        (
            local uiException = getCurrentException()
            local uiDiagnostic = writeUiDiagnostic uiException
            local uiMessage = tr "插件执行失败。请查看本次传递报告或内部诊断文件；如果没有生成报告，请重新安装插件。"
            if uiDiagnostic != "" do uiMessage += ((tr "\n\n内部诊断文件：\n") + uiDiagnostic)
            messageBox uiMessage title:(tr "FBX 到 3ds Max")
            succeeded = false
        )
        succeeded
    )

    fn runSelfCheck =
    (
        if not doesFileExist pySelfCheckFile then
        (
            messageBox ((tr "找不到自检文件：\n") + pySelfCheckFile) title:(tr "FBXTo3dsMax 自检")
            return false
        )

        local code = ""
        code += "import os, sys, importlib.util\n"
        code += "_f2m_sc_path = os.path.abspath(" + pyString pySelfCheckFile + ")\n"
        code += "_f2m_sc_name = '_fbx_to_3dsmax_selfcheck_runtime'\n"
        code += "sys.modules.pop(_f2m_sc_name, None)\n"
        code += "_f2m_sc_spec = importlib.util.spec_from_file_location(_f2m_sc_name, _f2m_sc_path)\n"
        code += "if _f2m_sc_spec is None or _f2m_sc_spec.loader is None: raise RuntimeError('无法创建自检模块加载器')\n"
        code += "_f2m_sc = importlib.util.module_from_spec(_f2m_sc_spec)\n"
        code += "sys.modules[_f2m_sc_name] = _f2m_sc\n"
        code += "try:\n"
        code += "    _f2m_sc_spec.loader.exec_module(_f2m_sc)\n"
        code += "except BaseException:\n"
        code += "    if sys.modules.get(_f2m_sc_name) is _f2m_sc: sys.modules.pop(_f2m_sc_name, None)\n"
        code += "    raise\n"
        code += "setattr(_f2m_sc, '_F2M_IMPORT_COMPLETE', True)\n"
        code += "if os.path.normcase(os.path.abspath(_f2m_sc.__file__)) != os.path.normcase(_f2m_sc_path): raise RuntimeError('自检模块来源不一致')\n"
        code += "_f2m_sc_result = _f2m_sc.start_from_max()\n"

        try
        (
            python.Execute code throwOnError:true clearUndoBuffer:false
            -- Python 只负责启动 Popen 和显示非模态 Qt 进度窗；这里立即返回，
            -- 不再同步等待最多 300 秒，也不会阻塞 Max 主界面消息循环。
            true
        )
        catch
        (
            messageBox (tr "无法启动插件自检。请重新安装插件；如果问题仍存在，请保留安装日志。") title:(tr "FBXTo3dsMax 自检") beep:true
            false
        )
    )

    on btn_pick pressed do
    (
        local f = getOpenFileName caption:(tr "选择 Maya / Blender / 其它软件导出的 FBX") types:(tr "FBX (*.fbx)|*.fbx|所有文件 (*.*)|*.*|")
        if f != undefined do
        (
            edt_fbx.text = f
            markFbxChangedIfNeeded()
        )
    )

    on edt_fbx entered txt do markFbxChangedIfNeeded()

    on chk_shape changed state do markOptionsChanged()
    on chk_matid changed state do markOptionsChanged()
    on chk_normals changed state do markOptionsChanged()
    on chk_smoothing changed state do markOptionsChanged()
    on chk_uv1 changed state do markOptionsChanged()
    on chk_uv2 changed state do markOptionsChanged()
    on chk_uv3 changed state do markOptionsChanged()
    on chk_vc changed state do markOptionsChanged()
    on chk_alpha changed state do markOptionsChanged()
    on chk_backup changed state do markOptionsChanged()
    on chk_keep_mat changed state do markOptionsChanged()
    on chk_keep_imported changed state do markOptionsChanged()
    on chk_hidden changed state do markNeedCheck()

    on btn_mode_topo Click sender args do
    (
        if currentMode != 1 do
        (
            currentMode = 1
            markNeedCheck()
            updateModeUI()
        )
    )

    on btn_mode_replace Click sender args do
    (
        if currentMode != 2 do
        (
            currentMode = 2
            markNeedCheck()
            updateModeUI()
        )
    )

    on btn_advanced pressed do
    (
        advancedOpen = not advancedOpen
        setAdvancedVisible advancedOpen
    )

    on btn_selfcheck pressed do runSelfCheck()

    -- Clicking the selected language must restore its pressed state as well.
    on btn_language_zh changed state do
        if not changingLanguage do switchLanguage "zh-CN"

    on btn_language_en changed state do
        if not changingLanguage do switchLanguage "en"

    on F2M_Transfer_Rollout open do
    (
        initializeLanguage()
        applyLanguage()
    )

    on btn_check pressed do
    (
        -- 跨 Python 调用只保留纯句柄和名称，避免长期持有节点包装对象。
        local selectionIdentityBeforeCheck = captureSelectionHandlesAndNames()
        local checkSucceeded = runPython true
        restoreSelectionByHandlesOrNames selectionIdentityBeforeCheck[1] selectionIdentityBeforeCheck[2]
        if checkSucceeded do
        (
            markChecked (currentCheckKey())
        )
    )

    on btn_run pressed do
    (
        local runCheckKey = currentCheckKey()
        if not (checkIsCurrent runCheckKey) then
        (
            checkDone = false
            checkedKey = ""
            setWarning "FBX、模式、选中对象或隐藏处理设置变化后需要重新检查。"
            messageBox (tr "请先点击“检查 FBX/匹配”。只改变传递数据选项不需要重新检查；如果换了 FBX、模式、选中对象或隐藏处理设置，需要重新检查。") title:(tr "FBX 到 3ds Max")
        )
        else
        (
            if confirmRunForSelection() do
            (
                -- 模式二成功替换后旧句柄会失效，因此同时保留名称用于回退。
                local selectionIdentityBeforeRun = captureSelectionHandlesAndNames()
                setWarning "正在传递数据，请等待；复杂模型会在完成安全写入和回读后返回。"
                btn_run.enabled = false
                btn_language_zh.enabled = false
                btn_language_en.enabled = false
                try(setWaitCursor())catch()
                try(windows.processPostedMessages())catch()
                local transferSucceeded = runPython false
                try(setArrowCursor())catch()
                btn_run.enabled = true
                btn_language_zh.enabled = true
                btn_language_en.enabled = true
                restoreSelectionByHandlesOrNames selectionIdentityBeforeRun[1] selectionIdentityBeforeRun[2]
                if transferSucceeded then
                (
                    if currentMode == 2 then
                    (
                        -- 模式二成功后已替换节点，选择句柄自然变化，必须重新检查。
                        markNeedCheck()
                        setWarning "替换完成。Max 源模型节点已经变化；再次运行前请重新检查。"
                    )
                    else
                    (
                        setWarning "传递完成。当前 FBX、模式和 Max 源模型未变化时，可调整传递选项后直接再次执行。"
                    )
                )
                else
                    setWarning "传递未完成。请查看报告或内部诊断；若 FBX、模式、Max 源模型和隐藏设置未变化，可修正选项后直接重试。"
            )
        )
    )
)

createDialog F2M_Transfer_Rollout style:#(#style_titlebar, #style_sysmenu, #style_toolwindow)
