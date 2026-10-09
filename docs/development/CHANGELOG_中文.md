# FBXTo3dsMax 更新日志

版本基线为原插件 `1.2.16`；BUG 修复增加 `0.0.1`，新增功能增加 `0.1.0`。发布时同步引擎、UI、版本文件、包元数据和安装器标记。

## v1.4.24（2026-10-09）：双语与目录整理

- 新增常驻 **语言 / Language** 下拉框，中文/English 原位切换，保留模式、FBX、选项和检查状态；偏好原子保存到本地，工具栏与用户摘要使用所选语言，原始技术诊断保留必要信息。
- 整理工程根目录，运行 Python/MAXScript/资源统一放到小写 `contents/`，PowerShell 安装入口移至 `tools/`；中文与英文用户指南分别放在 `docs/zh/`、`docs/en/`，维护文档放在 `docs/development/`。
- 增加完整英文安装与使用参考、原创流程图及经授权隐私审查的历史形状截图；不分发模型，不上传原企业 PDF 或内部链接。纠正同数量即同拓扑、非流形更稳定、安装失败可忽略等旧说明。
- 修复混合技术诊断导致英文自检报告标题、检查行或最终失败提示跳过翻译的问题；按结构字段翻译一次，保留原始业务 JSON、未知诊断及中文行为。传递异常在最终显示边界翻译，避免提前翻译影响整份报告。
- 修复顶部工具栏在实际字体与样式下压缩按钮、将文字显示为省略号的问题：按当前 Qt 样式的尺寸建议设置最小空间，语言切换后原位重算；保留同一个按钮、动作与定时器。尺寸修复须经过纯测试和真实 Max 回归；本版验收结果见[测试说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md)。
- Toolbar label fix (English): use the current polished Qt size hints to prevent the host toolbar from shrinking the icon/text button below its required size; recalculate in place after language changes without replacing the button, action or timers. This size correction requires pure tests and real-Max regression checks; see [testing](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md) for this version's acceptance results.
- 修复主工具栏首次验证通过、移除旧备用栏后再次验证失败时遗漏备用路径的分支：任一次主工具栏验证失败都尝试现有顶部备用栏；备用验证仍失败时清理自有动作并报错。此分支须经过纯测试与真实 Max 回归，本版结果见[测试说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md)。
- Toolbar fallback fix (English): try the existing top fallback if either Main Toolbar validation fails, including the second validation after removing an old fallback. If fallback validation also fails, remove owned actions and report failure. This branch requires pure tests and real-Max regression checks; see [testing](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md) for this version's results.
- 修复英文模式一的“Smoothing Groups”复选框末尾字母裁切：扩大该控件的可用宽度，保持位置、完整译文、勾选状态与传递逻辑；结果须以实际字体/DPI 的完整界面读回验收。
- Smoothing checkbox fix (English): increase the available width for the full “Smoothing Groups” caption without changing its position, checked state or transfer behavior; verify the complete interface on the actual host font and DPI.
- 修复英文自检把单独翻译的原生光滑组来源片段与完整技术报告比较而误报失败的问题：以本次实际生产摘要的完整来源消息验证保存报告的原文或完整译文；缺失、错误来源及无关节点/路径仍拒绝，业务成功与逐面掩码读回门保持。本版结果见[测试说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md)。
- Native smoothing self-check fix (English): verify the saved raw or fully translated production message from the current transfer summary instead of translating an isolated method fragment. Missing or incorrect source evidence and unrelated node/path text remain rejected; transfer success and per-face mask readback gates are unchanged. See [testing](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md) for this version's results.
- 固定安装清单从历史 27 项增至 **32 项**：两个语言模块与三个英文指南。安装副本的中英文指南平铺在 `contents/`，保留 MIT 文本。
- 新功能按 `+0.1.0` 同步为 `1.4.24`，保留两模式业务合同。验收标准包含纯测试、真实 Max、自检与安装生命周期；当前结果见测试说明，旧版结果不代替后续版本证明。

## v1.3.24（2026-10-08）：公开源码与自检素材修复

- 改为 MIT 许可证，作者署名保留 Dimmens；使用可读 Python/MAXScript 源文件安装。
- 删除公开分发对私有/前雇主 FBX 样本的依赖，新增程序生成测试流程：`f2m_test_fixtures.py` 提供原创拓扑/原生光滑组数据，`f2m_selfcheck.py` 在 Max 中构建、导出简单两骨骼 Skin 场景。仓库不包含 FBX、MAX 或 BLEND 模型文件。
- 整理源码、资源和维护测试；将旧加密发行、工具链、私有资产、退役实验与历史流水移入所有者单独备份。
- 重写安装说明、两模式使用参考、贡献和 GitHub 发布指南；移除公开文档中的个人路径、私有资产名称及历史运行身份。
- 增加公开仓库静态检查和独立 Max Batch 自检入口，验证输出使用用户本地数据目录。
- 自检依赖修复按 BUG 规则增加 `0.0.1`；同步为 `1.3.24`，安装清单从 28 项改为 27 项（移除三个私有样本，增加生成器与安装副本的 LICENSE）。保留既有两模式业务行为。
- 同步安装器原生“必要目标”检查，要求生成器和 LICENSE，移除已退役 FBX 要求；新增实际 MAXScript 目标数组与 27 项固定清单的回归检查，仓库静态检查也验证这道门。此前仅校验清单和原生解析会漏掉这个确定性的安装失败。
- 测试方法与证据边界见[测试说明](https://github.com/DimmensCK/FBXTo3dsMax/blob/main/docs/TESTING.md)；原创小样本不继承旧私有大资产的压力覆盖，旧加密安装验收不作为源码安装证明。

## v1.3.23（2026-08-01）

- 修复模式二大坐标资产的 float32 Skin 往返被固定阈值误判失败：世界点与包围盒共用尺度感知容差，保留 `0.001 cm` 下限和 2 ppm 坐标预算；非法输入、明显超差仍停止并回滚。
- 正式业务失败明确显示“传递未完成”、对象摘要与报告路径。
- 两种模式在修改 FBX Importer 或调用原生 import 前，先解除 Modify 当前对象、切到 Create 并验证脱离；模式一最后一个法线对象也执行该护栏。
- 保留 v1.3.22 的变换、法线权威、候选可见性与全部事务护栏。

## v1.3.22（2026-07-31）

- 模式一节点级点位写入/读回固定在 world 坐标域，消除当前工具栏 World/Local/View 状态影响，并保留独立基础对象读回及失败快照恢复。
- 导入 FBX 完整求值栈（包括 Skin），通过独立临时 Edit Normals 读取最终面角方向；最终方向逐角验证。
- 模式二保留新候选自适应 Mesh Bind，继承旧 Max 模型图层及节点显示状态，验证 Pivot、世界点、包围盒与可见性，避免候选隐藏或位置改变。

## v1.3.21（2026-07-31）

- 修复模式一非原点模型重复平移，恢复成熟的节点级点位写入域；基础对象快照仅用于精确回滚。
- 修复模式二把 FBX 绑定矩阵写到另一套 Max 场景骨架导致的变形：Max 源 Skin local data 提供绑定系统，FBX 提供逐顶点状态。
- Skin 必须精确复制到原 FBX Skin 栈位；local data 或读回不完整时停止，不退化为普通 modifier 副本。

## v1.3.20（2026-07-31）

- 跨调用节点身份改用 handle，删除前释放 wrapper，名称回退要求唯一，覆盖提交、恢复和错误引用生命周期。
- 自检必须同时满足业务通过与 Batch 自然退出 0；强制清理、超时、取消和非零退出均失败。
- 区分 SG-only、SG 全 0 的完整法线传递，以及 SG 感知的 `0.1°` 面角语义残差；加入最小保护闭包、实际接收模型基线和两次最终方向读回。
- 零残差仍保留唯一的全蓝色栈底法线基线，防止基础网格旧方向重新暴露。
- SG+normals 使用独立严格解析/求解工作进程和一次 Max 导入，拓扑摘要在同次正式读取中验证。
- 模式二默认保留 FBX 目标材质/通道/法线，逐顶点权重只采用 ReplaceVertexWeights。此版早期完整 FBX Bind 合同已由 v1.3.21 的 Max local-data 合同取代。

## v1.3.19（2026-07-30）

- 检查缓存仅绑定模式、FBX 路径/大小/时间、隐藏范围和选择；改变传递通道不重复昂贵检查，正式执行仍全面验证。
- 模块按绝对路径、版本、完成态及接口复用；拓扑/Skin Helper 分开缓存。
- 加入 Max 退出状态机与可取消工具栏 timer，避免关闭/CUI 保存时重建控件。
- 光滑求解优先连续软区；SG-only 优先采用严格验证通过的 Autodesk 候选。
- 收紧 importer 设置恢复、临时节点清理、安装清单集合和卸载字节恢复。

## v1.3.18（2026-07-30）

- UI 删除不支持的 python.Eval，改用 -1/0/1 结果桥区分异常、业务失败与成功。
- Python 入口保护已有 Undo Buffer；UI 桥接异常保存 UTF-8 技术诊断并提供中文提示。

## v1.3.17（2026-07-30）

- 对同向循环面角起点变化及面重排建立明确映射，实际应用于 UV、RGB/Alpha、材质 ID、SG 和法线。
- 修复 AutoLoader 路由和 Bootstrap 执行边界，实现顶部按钮冷启动恢复。
- 增加源码、安装副本、FBX、法线空间和光滑组写回回归。

## v1.3.16（2026-07-29）

- 保留历史两模式并整理成独立 FBXTo3dsMax 工程。
- 加入光滑组传递/严格求解、法线共存、过程模型和独立 Batch 自检。
- 建立完整暂存、SHA-256、备份、整体切换、失败回滚与可恢复卸载流程。

历史真机环境为 Windows 11 x64、Max 2023.3.10 / Python 3.9.7。其它 Max 主版本需各自验证；任何回归通过都不等于未知缺陷为零。
