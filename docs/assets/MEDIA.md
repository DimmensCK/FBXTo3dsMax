# 教程媒体 / Tutorial media

## 原创矢量图 / Original SVGs

下列图由本项目直接用 SVG 编写，随项目按 MIT 提供：

- `brand/fbx-to-max.svg`：项目横幅。
- `diagrams/two-modes.svg`：两模式的数据方向与保留对象。
- `diagrams/channel-map.svg`：原创简单网格、UV 与数据层级。
- `diagrams/smoothing-and-normals.svg`：面平滑关系与面角方向的区别。
- `diagrams/skin-data-authority.svg`：模式二网格、权重、骨骼与绑定的数据来源。

它们是**原创概念示意**，不是 3ds Max 截图、实际模型输出或版本验收证据。

These SVGs were authored as original project illustrations and are provided under MIT. They explain workflows, an original simple mesh/UV layout, smoothing/normal concepts and Skin data authority. They are **conceptual schematics**, not software captures, actual transfer outputs or version-acceptance evidence.

## 1.4.26 较早来源的真实界面 / Actual UI from the earlier source

`ui/rollout-1.4.26-cn.png` 与 `ui/rollout-1.4.26-en.png` 分别展示 Max 2023.3.10 中的中文/英文默认模式一。它们来自较早本地来源 `f94fdb51a3f570bcba7dcf930a6b833c2958e84a`，原 PNG 完整复制，未裁剪、重绘或重新编码。FBX 字段为空，无模型、场景视口、本机个人路径或内部链接，按 MIT 提供。

这两张图证明当时的界面布局，**不作为之后更改的点位核心或整个新包验收**。旧双语/英文/PowerShell 结果绑定各自历史来源；当前修订状态见[测试说明](../TESTING.md)。本地验收修订号不是公开下载 commit，其本地历史不随公开版本上传。

These unchanged originals show the Chinese/English default Mode 1 UI in Max 2023.3.10 from the earlier local source. They contain an empty FBX field, no model/scene viewport, personal local path or internal link, and are provided under MIT. They document the earlier layout, **not qualification of the later changed point core or complete package**. See [Testing](../TESTING.md) for separate historical/current scopes and the Release for public download identities.

## 1.4.26 原创雨棚渲染 / Original canopy renders

| 文件 / File | 内容 / Subject |
|---|---|
| `demos/canopy-before-1.4.26.png` | 模式一传递前 / Before Mode 1 transfer |
| `demos/canopy-after-1.4.26.png` | 实际形状与UV1传递后 / After actual shape and UV1 transfer |

原图来自本次新源码 a9071872a1cfe3034af3c6b20c4e13ca7283fee3 的同一次原生安装副本演示，真实预检及形状/UV1传递后保留接收节点、材质和选择。两图均960×640，使用同一相机/原创棋盘材质/灯光。传递前 PNG 为693,217 B、SHA-256 `CB75DB4FC2E3AF4938E1B2B8F56DC759CEB01112663F2AC08D1060F7D18BBE28`；传递后为796,691 B、SHA-256 `2E7E384D086C0F3230A2A0CBD4750AC05A97BF65726EB0A6C24579FC4FA3A26E`。两张原图已分别实际查看，原始低起伏雨棚到明显波浪及棋盘 UV 的变化清楚，无账号、本机路径或私有模型。原生安装副本演示已通过独立复核；随文档提供的四张 PNG 均逐字节保留原图。

Both original 960×640 PNGs belong to one native installed-copy demonstration on the new local source above, using the same camera, original checker material and lighting. Their exact lengths and SHA-256 hashes are recorded above. Each original was actually viewed: the change from a gently curved canopy to pronounced waves, together with checker UV changes, is visible, without accounts, personal paths or private models. The native installed demonstration passed independent review; all four published PNGs preserve the original bytes.

两张新渲染来自本次合格源码的同一次原生演示，传递前、传递后两图分别与各自原始 PNG 逐字节一致，并分别核对来源、SHA-256 与尺寸。它们不是 UI 截图或物理鼠标操作记录，也不分发生成器之外的私有模型。

Both new renders come from the same accepted native demonstration on the changed source. Their original PNG bytes, origin, SHA-256 and dimensions were checked separately. They are not UI or physical-mouse records and distribute no private model.

## 1.4.25 历史真实界面 / Historical actual UI

`ui/rollout-1.4.25-cn.png` 与 `ui/rollout-1.4.25-en.png` 来自1.4.25在 3ds Max 2023.3.10 中的真实运行，分别展示中文和英文的默认模式一界面。FBX 路径为空，没有模型、场景视口、本机个人路径或内部链接。两张原始 PNG 完整复制，未裁剪、重绘或重新编码，随项目按 MIT 提供。它们展示界面布局；操作回归范围见[测试说明](../TESTING.md)。

These original PNG captures show the Chinese and English default Mode 1 UI of version 1.4.25 running in 3ds Max 2023.3.10. The FBX field is empty; no model, scene viewport, personal local path or internal link is included. Both PNGs are copied unchanged, without cropping, redrawing or re-encoding, and provided under MIT. They illustrate the layout; see [Testing](../TESTING.md) for the workflow regression scope.

## 授权历史截图 / Authorized historical screenshots

| 文件 / File | 展示内容 / Subject |
|---|---|
| `tutorial/deformation-before.webp` | 形状传递前 / Shape before transfer |
| `tutorial/deformation-after.webp` | 形状传递后 / Shape after transfer |
| `tutorial/materials-and-face-ids.webp` | 材质与逐面 ID 查看 / Material and face-ID inspection |
| `tutorial/vertex-color-rgb.webp` | RGB 顶点色查看 / RGB vertex-color inspection |
| `tutorial/vertex-alpha.webp` | 独立 Alpha 查看 / Independent alpha inspection |

这些画面由 Dimmens 明确授权用于公开教程，按原图完整复制，未裁剪、重绘或重新编码。已逐图检查，没有可识别的公司/个人文字、完整本机路径或内部链接。普通匿名对象名与画面片段不构成人物身份说明。

截图展示历史功能，不是当前版本的 UI 截图、完整步骤或验收结果。画面左右不定义哪边必定是 FBX 或 Max。仓库不附带任何底层模型或场景文件，授权也不授予底层私有模型的使用权。

Dimmens explicitly authorized these historical images for public tutorials. They were copied whole, without cropping, redrawing or re-encoding, and reviewed for identifiable company/personal text, full local paths and internal links. Generic anonymous object names do not identify a person.

The images illustrate historical functionality, not current-version UI, complete procedures or acceptance results. Left/right placement does not define FBX/Max authority. No underlying model or scene files are included, and no rights to the underlying private models are granted.

## 历史视频 / Historical clip

`demos/mode1-deformation-v1.3.23.mp4` 是经授权的旧版结果检查片段：裁去非演示区域，去除原片音轨与附加元数据，画面加入中英历史版本标题。标准容器信息（例如 **Lavf61.7.100**）仍保留，不表示全部元数据为零。它展示变形/绑定结果查看，不是完整操作录像或新版验证证明。

The authorized historical clip is cropped to the demonstration viewport, with the original audio track and additional source metadata removed, and a bilingual historical-version caption added. Standard container information, including **Lavf61.7.100**, remains; this is not a claim of zero metadata. It shows deformation/binding result inspection, not a complete tutorial recording or current-version validation.

## 不分发的资料 / Excluded material

原 PDF、内部资源索引/链接、未导出的视频和 FBX / MAX / BLEND 模型文件不在公开工程中。教程根据当前实现重新组织，不将历史说明的错误前提当作产品承诺。

The original PDF, internal resource indexes/links, unexported video and FBX / MAX / BLEND model files are excluded. The tutorials are rewritten against the current implementation rather than treating historical assumptions as product guarantees.

## 社交预览 / Social preview

`brand/social-preview.svg` 是延续项目品牌视觉的原创 1280×640 SVG；`brand/social-preview.png` 是使用 Max 自带 Python 3.9.7 与 PySide2 / QtSvg 5.15.1 直接栅格化的同尺寸 PNG（使用现有 Windows 平台插件，仅 QImage 内存绘制，未显示窗口）。未启动 Max、未编辑历史截图或模型。它用于仓库社交预览，说明选择性通道、Skin 工作流、免费 MIT 源码与中英语言；不是软件界面、实际模型输出或验收证明。

The original 1280×640 social-preview SVG extends the project branding. Its PNG is a direct rasterization using Max-bundled Python 3.9.7 and PySide2 / QtSvg 5.15.1, with the existing Windows platform plugin and QImage memory painting only; no window was shown. No Max host was started and no historical screenshot or model was edited. It describes selective channels, Skin workflows, free MIT source and Chinese/English; it is not a software capture, actual transfer output or acceptance result.
