/*
FBXTo3dsMax v1.3.24 隔离式交互安装验收。

    仅允许由带随机令牌的专用 3ds Max 子进程执行。脚本连续执行两次正式
    拖放安装器，逐轮确认机器状态、最终中文结果载荷、27 项安装哈希和
    可见顶部按钮，写出带同一令牌的新鲜结果后退出该专用子进程。
*/

(
global F2M_Installer_RunStatus
global F2M_Installer_LastLogPath
global F2M_Installer_FinalDialogTitle
global F2M_Installer_FinalDialogText
global F2M_TopologyHelper
global F2M_SkinHelper
global F2M_Helper

local expectedVersion = "1.3.24"
local expectedManifestCount = 27
local environmentClass = dotNetClass "System.Environment"
local fileClass = dotNetClass "System.IO.File"
local pathClass = dotNetClass "System.IO.Path"
local directoryClass = dotNetClass "System.IO.Directory"
local processClass = dotNetClass "System.Diagnostics.Process"
local bitConverter = dotNetClass "System.BitConverter"
local shaClass = dotNetClass "System.Security.Cryptography.SHA256"
local utf8NoBom = dotNetObject "System.Text.UTF8Encoding" false
local runToken = environmentClass.GetEnvironmentVariable "F2M_INSTALL_HARNESS_TOKEN"
local commandArgs = undefined
local sourceHarnessName = getSourceFileName()
local expectedHarnessPath = ""
local testsRoot = ""
local workspaceRoot = ""
local installerPath = ""
local resultPath = ""
local processId = (processClass.GetCurrentProcess()).Id as string
local pathResolveError = ""

try
(
    expectedHarnessPath = pathClass.GetFullPath (sourceHarnessName as string)
    testsRoot = pathClass.GetDirectoryName expectedHarnessPath
    workspaceRoot = pathClass.GetDirectoryName testsRoot
    installerPath = pathClass.Combine workspaceRoot "Install_FBXTo3dsMax.ms"
    resultPath = pathClass.Combine testsRoot "_max_install_v1319_harness.txt"
)
catch
(
    pathResolveError = getCurrentException()
)
if pathResolveError != "" do
    throw ("无法从验收脚本自身路径解析工作区：" + pathResolveError)

fn validRunToken value =
(
    if value == undefined do return false
    local tokenText = value as string
    if tokenText.count != 40 do return false
    if (substring tokenText 1 8) != "v1.3.24-" do return false
    local hexCharacters = "0123456789abcdef"
    for index = 9 to 40 do
    (
        if findString hexCharacters (toLower (substring tokenText index 1)) == undefined do
            return false
    )
    true
)

fn sameFullPath firstPath secondPath =
(
    local firstFull = ""
    local secondFull = ""
    try(firstFull = pathClass.GetFullPath (firstPath as string))catch(return false)
    try(secondFull = pathClass.GetFullPath (secondPath as string))catch(return false)
    (toLower firstFull) == (toLower secondFull)
)

fn dedicatedHarnessCommand args expectedPath =
(
    if args == undefined or args.count < 3 do return false
    local matchingTriples = 0
    for index = 1 to (args.count - 2) do
    (
        local firstArg = args[index] as string
        local secondArg = args[index + 1] as string
        local thirdArg = args[index + 2] as string
        if (
            (toLower firstArg) == "-u" and
            (toLower secondArg) == "maxscript" and
            sameFullPath thirdArg expectedPath
        ) do matchingTriples += 1
    )
    matchingTriples == 1
)

fn commandArgsDiagnostic args =
(
    if args == undefined do return "<undefined>"
    local result = ""
    try
    (
        for index = 1 to args.count do
            result += ("[" + (index as string) + "]=" + (args[index] as string) + " | ")
    )
    catch(result += ("<读取失败：" + (getCurrentException()) + ">"))
    result
)

-- 这些条件必须同时满足；误把本文件拖进用户工作会话时只会拒绝，
-- 绝不会执行安装、关闭 Max 或丢弃未保存场景。有效令牌下的守卫失败会先写
-- GUARD_FAIL，供只管理本次 PID 的启动器诊断。
if not (validRunToken runToken) do
    throw "拒绝运行安装验收：缺少专用子进程令牌。"

local guardError = ""
try
(
    expectedHarnessPath = pathClass.GetFullPath expectedHarnessPath
    commandArgs = environmentClass.GetCommandLineArgs()
    if sourceHarnessName == undefined or sourceHarnessName == "" or (not (sameFullPath sourceHarnessName expectedHarnessPath)) do
        throw "当前源脚本路径不是指定验收脚本。"
    if not (dedicatedHarnessCommand commandArgs expectedHarnessPath) do
        throw "当前命令行不是精确的 -U MAXScript 验收入口。"
)
catch
(
    guardError = getCurrentException()
)
if guardError != "" do
(
    fileClass.WriteAllText resultPath (
        "GUARD_FAIL\r\n" +
        "令牌=" + runToken + "\r\n" +
        "进程=" + processId + "\r\n" +
        "错误=" + guardError + "\r\n" +
        "源脚本=" + (sourceHarnessName as string) + "\r\n" +
        "原始命令行=" + (environmentClass.CommandLine as string) + "\r\n" +
        "参数=" + (commandArgsDiagnostic commandArgs) + "\r\n"
    ) utf8NoBom
    throw ("拒绝运行安装验收：" + guardError)
)

environmentClass.SetEnvironmentVariable "F2M_INSTALL_HARNESS_TOKEN" ""
fileClass.WriteAllText resultPath (
    "STARTED\r\n令牌=" + runToken + "\r\n进程=" + processId + "\r\n"
) utf8NoBom

local failureText = ""

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

fn requireSuccessfulInstall passIndex =
(
    if F2M_Installer_RunStatus != 1 do
        throw (
            "第 " + (passIndex as string) + " 轮安装器没有返回成功状态；" +
            "状态=" + (F2M_Installer_RunStatus as string) +
            (if F2M_Installer_LastLogPath != "" then
                ("，日志=" + F2M_Installer_LastLogPath)
            else "")
        )
    if F2M_Installer_FinalDialogTitle != "FBXTo3dsMax" do
        throw (
            "第 " + (passIndex as string) +
            " 轮最终中文结果标题不正确：" +
            (F2M_Installer_FinalDialogTitle as string)
        )
    local dialogText = F2M_Installer_FinalDialogText as string
    local requiredChineseText = #(
            "FBXTo3dsMax v1.3.24 安装成功。",
        "顶部",
        "按钮",
        "安装目录：",
        "安装日志："
    )
    for requiredText in requiredChineseText where findString dialogText requiredText == undefined do
        throw (
            "第 " + (passIndex as string) +
            " 轮最终中文结果正文缺少：" + requiredText
        )
    if findString (toLower dialogText) "installed successfully" != undefined do
        throw "安装结果正文仍包含旧版英文成功提示。"
    if F2M_Installer_LastLogPath == "" or (not (fileClass.Exists F2M_Installer_LastLogPath)) do
        throw ("第 " + (passIndex as string) + " 轮安装日志没有读回。")
    true
)

fn verifyInstalledPackage passIndex =
(
    local packageRoot = pathConfig.appendPath (getDir #privateExchangeStoreInstallPath) "FBXTo3dsMax"
    local contentsRoot = pathConfig.appendPath packageRoot "Contents"
    local versionPath = pathConfig.appendPath contentsRoot "FBXTo3dsMax.version"
    local manifestPath = pathConfig.appendPath contentsRoot "FBXTo3dsMax.install-manifest.sha256"
    local uiPath = pathConfig.appendPath contentsRoot "FBXTo3dsMax_UI.ms"

    if not directoryClass.Exists packageRoot do
        throw ("第 " + (passIndex as string) + " 轮安装后缺少正式插件目录。")
    if not fileClass.Exists versionPath do throw ("安装后缺少版本文件：" + versionPath)
    local installedVersion = fileClass.ReadAllText versionPath
    installedVersion = substituteString installedVersion "\r" ""
    installedVersion = substituteString installedVersion "\n" ""
    if installedVersion != expectedVersion do
        throw ("安装后版本不是 " + expectedVersion + "。")
    if not fileClass.Exists manifestPath do throw "安装后缺少 SHA-256 清单。"
    if not fileClass.Exists uiPath do throw "安装后缺少正式界面脚本。"

    local manifestLines = fileClass.ReadAllLines manifestPath
    local verifiedCount = 0
    local seenPaths = #()
    local packagePrefix = pathClass.GetFullPath (packageRoot + "\\")
    local packagePrefixLower = toLower packagePrefix
    for rawLine in manifestLines do
    (
        local line = rawLine as string
        if line.count > 0 do
        (
            local parts = filterString line "|"
            if parts.count != 2 do throw ("安装哈希清单行格式无效：" + line)
            local relativePath = parts[1] as string
            local expectedHash = toUpper (parts[2] as string)
            if (
                relativePath == "" or
                findString relativePath ".." != undefined or
                (substring relativePath 1 1) == "\\" or
                (substring relativePath 1 1) == "/" or
                (relativePath.count >= 2 and (substring relativePath 2 1) == ":")
            ) do throw ("安装哈希清单包含不安全路径：" + relativePath)
            if (findItem seenPaths relativePath) != 0 do
                throw ("安装哈希清单包含重复路径：" + relativePath)
            if expectedHash.count != 64 do
                throw ("安装哈希清单包含无效哈希：" + relativePath)
            append seenPaths relativePath

            local installedPath = pathClass.GetFullPath (
                pathClass.Combine packageRoot relativePath
            )
            if findString (toLower installedPath) packagePrefixLower != 1 do
                throw ("安装哈希路径越过正式插件目录：" + relativePath)
            if sha256File installedPath != expectedHash do
                throw ("安装文件哈希不一致：" + relativePath)
            verifiedCount += 1
        )
    )
    if verifiedCount != expectedManifestCount do
        throw (
            "安装哈希清单应为 " + (expectedManifestCount as string) +
            " 项，实际为 " + (verifiedCount as string) + " 项。"
        )

    local uiTextLower = toLower (fileClass.ReadAllText uiPath)
    if findString uiTextLower "python.eval" != undefined do
        throw "安装后的界面仍包含不受支持的 python.Eval。"
    if ::FBXTo3dsMax_Bootstrap == undefined do throw "安装后启动引导未注册。"
    if not (::FBXTo3dsMax_Bootstrap.verifyToolbar()) do
        throw "安装后顶部按钮没有通过唯一性、可见性与点击命中验证。"
    true
)

try
(
    for passIndex = 1 to 2 do
    (
        if passIndex == 2 do
        (
            F2M_TopologyHelper = "F2M_STALE_TOPOLOGY_SENTINEL"
            F2M_SkinHelper = "F2M_STALE_SKIN_SENTINEL"
            F2M_Helper = "F2M_STALE_ALIAS_SENTINEL"
        )
        F2M_Installer_RunStatus = -1
        F2M_Installer_LastLogPath = ""
        F2M_Installer_FinalDialogTitle = ""
        F2M_Installer_FinalDialogText = ""
        fileIn installerPath quiet:true
        requireSuccessfulInstall passIndex
        verifyInstalledPackage passIndex
        if passIndex == 2 and
           (F2M_TopologyHelper != undefined or
            F2M_SkinHelper != undefined or
            F2M_Helper != undefined) do
            throw "同版本覆盖后仍残留旧 MAXScript Helper 缓存。"
    )
)
catch
(
    failureText = getCurrentException()
)

local finalText = if failureText == "" then
(
    "PASS\r\n" +
    "令牌=" + runToken + "\r\n" +
    "进程=" + processId + "\r\n" +
    "覆盖安装次数=2\r\n" +
    "安装清单=27/27\r\n" +
    "中文结果载荷=通过\r\n" +
    "Helper缓存清理=通过\r\n" +
    "顶部按钮=通过\r\n"
)
else
(
    "FAIL\r\n" +
    "令牌=" + runToken + "\r\n" +
    "进程=" + processId + "\r\n" +
    "错误=" + failureText + "\r\n"
)
fileClass.WriteAllText resultPath finalText utf8NoBom

-- 只有通过开头双重身份校验的专用子进程才能到达这里。
quitMax #noPrompt
)
