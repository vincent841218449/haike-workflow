# MotionGit 竖屏模板与 MediaCrawler 集成：官方资料研究

研究日期：2026-10-21（北京时间）。范围：公开网页、官方仓库与公开规范；未登录、未下载个人模板包、未执行爬虫或生成、未发送外部消息。本文件区分官方已证实事实、现有项目观察与建议实现合同；不是已交付功能清单，也不作法律结论。

## 1. 核心结论

1. MotionGit 当前公开的 9:16 筛选结果是 **7 款完整模板**，不是站点页头的 41 款，也不是“口播视频 13”这一跨比例分类总数。用户图 2 的七张卡片与本次公开筛选结果对应。后续目录应按官方身份同步，不能把截图数量硬编码成永久总量。[官方中文竖屏目录](https://motiongit.com/templates?ratio=9%3A16&lang=zh)
2. 完整接入需要运行每个模板实际提供的制作合同和原生动画；网站预览、改名、换配色、只复用 title/quote/media 三种通用组件，均不足以证明完整接入。MotionGit 规范明确区分模板内容、运行时适配与分发身份，要求保留完整动画依赖并对真实输出进行运动验收。[官方规范：协议层、包结构、运行时](https://motiongit.com/spec)
3. MediaCrawler 提供抖音关键词搜索、指定作品详情、创作者作品、评论以及可选媒体下载。它本身不是“读完口播文案后自动找到语义正确的镜头并剪成片”的编排器；这一结论来自其公开入口和数据接口的职责范围，不是对所有未检查分支作不存在证明。[官方 README](https://github.com/NanmiCoder/MediaCrawler/blob/main/README.md)、[抖音入口源码](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/media_platform/douyin/core.py)、[搜索客户端源码](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/media_platform/douyin/client.py)
4. MediaCrawler 当前许可名为 **NON-COMMERCIAL LEARNING LICENSE 1.1**，许可范围是非商业学习，商用需权利人书面同意。不能因其公开在 GitHub，就把代码随本产品默认商业分发或把抓到的视频视为可商用素材。此处仅转述许可及设计影响；软件授权、平台访问权限、具体视频的使用授权是三个独立问题。[当前 LICENSE](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/LICENSE)

## 2. 可确认的 9:16 模板目录

下表版本是研究时官方详情页面显示的公开元数据，**不代表本地已取得或已验收这些版本**。全部页面标为完整模板，输出标为 1080×1920、60fps；网站的 runtime verification 仍显示 Not verified。名称应使用官方中文全名；旧 04-A 等仅保留为历史迁移别名，不继续作为新选择器主名。[竖屏目录](https://motiongit.com/templates?ratio=9%3A16&lang=zh)

| 官方中文名称 | 官方页面 / 稳定页面身份 | 本次可见版本 | 已声明的能力重点 |
| --- | --- | --- | --- |
| 酷炫科技风 · 口播讲解 | [385712](https://motiongit.com/@adunext/385712) | 网页渠道分别返回 0.2.28-open-beta / 0.2.29-open-beta，存在缓存差异，须固定版本元数据与实际包确认 | 金属字、机械翻牌、空间卡片；独立 kinetic-user-core/1；中文横竖屏、英文竖屏基础表达 B1–B4，不能把英文原生 S 系列也宣称已支持竖屏 |
| 现代图文 · 口播讲解 · 竖屏 | [template-01-integrated-portrait](https://motiongit.com/@adunext/template-01-integrated-portrait) | 2.7.11 | 图文、强调与信息拆解；独立竖屏构图，原生动画与新增组件制作入口分开 |
| 活力海报 · 口播讲解 · 竖屏 | [vibrant-poster-portrait](https://motiongit.com/@adunext/vibrant-poster-portrait) | 2.7.10 | 高对比海报、列表和图形关系；25 个原生组与 motion-kit 0.3.0 并存；70 控件库中只声明七类表达完成本模板风格融合，不能称全部控件均完成艺术验收 |
| 鲜色角色 · 叙事讲解 · 竖屏 | [template-05-native-portrait](https://motiongit.com/@adunext/template-05-native-portrait) | 2.7.11 | 鲜色角色与叙事；原生动画和 motion-kit 0.3.0 分开；素材、字体、声音需按实际包处理 |
| 科技控制台 · 口播讲解 · 竖屏 | [template-04-dark-console-portrait](https://motiongit.com/@adunext/template-04-dark-console-portrait) | 2.7.11 | 紫色玻璃、控制台、数据与关系表达；原生证据组需要真实对应素材，观点基本组不应虚构证据 |
| 纸面透视 · 口播讲解 · 竖屏 | [template-02-expanded-portrait](https://motiongit.com/@adunext/template-02-expanded-portrait) | 2.7.11 | 纸张透视、分层卡片；native 仍需真实口播视频，纯音频走包内声明的 motion-kit 路线，不制造空白视频冒充人物输入 |
| 深色立体 · 多屏展陈 · 竖屏 | [template-03-native-portrait](https://motiongit.com/@adunext/template-03-native-portrait) | 2.7.11 | 深色立体舞台、多屏及空间层次；原生动画和新增组件入口分开，多屏案例需真实本期素材 |

其余六款详情标示运行时为 adu-authored-unit/1，不能假定与科技风使用同一 CLI 或同一参数结构。各版本还可能有不同 locale、schema、字幕证据和容量合同，应逐包解析而非按名称判断兼容。[科技风详情](https://motiongit.com/@adunext/385712)、[科技控制台详情](https://motiongit.com/@adunext/template-04-dark-console-portrait)

### “全部替换”应该如何落地（建议）

- **替换新建入口，不销毁历史工程。** 新选择器只呈现当前官方 9:16 目录，历史任务仍绑定原 template ID、版本、包 SHA、运行时与制作方案，避免旧成片失去重放能力。
- **把目录和可执行状态分开。** 每项有 discovered / downloaded / verified / integrated / acceptance-passed 等内部状态；面向用户只把已验收项称为可制作，待取得包或不支持运行时的项目说明具体原因，不能显示一律“可用”。
- **官方名称是一致性字段。** 保存 `officialName`、`templateId`、`slug`、`author`、`ratio`、`version`、`releaseHash`；站内展示和任务实际执行都来自同一记录，禁止前端名字 A、后台包 B。
- **真实预览。** 每张卡展示对应竖屏官方样片/封面及作者来源。预览不可用时显示明确加载错误及重试，不用无图大白框冒充预览，也不能把 Demo 人物用于用户成片。
- **制作方式匹配内容。** 模板支持 native 和组件路线时，产品应读取包声明，说明当前采用哪条路线并保存选择依据；不把组件组合冒称“与整段官方样片编舞完全相同”。

## 3. 何谓模板功能完整接入

### 官方明确的技术事实

.motion 是包含项目源码、参数、素材声明、依赖与许可的 ZIP 容器。内容 manifest 当前版本是 0.1.0-draft.1；个人分发外层版本是 1.0.0-rc.1，二者不能混用。模板版本、helper 版本、组件库版本也独立演进。[官方规范](https://motiongit.com/spec)

模板详情要求先读取入口和材料合同、核对依赖、预览再导出；个人下载可能包含下载者自己的 API Key，原包应私有保存，不能直接进可分发源码。官方静态检查不保证代码安全、素材版权或实际渲染质量。[科技控制台交接与验证说明](https://motiongit.com/@adunext/template-04-dark-console-portrait)

### 本产品应实现的合同（建议，不是已完成）

| 合同 | 最低需要保存和执行的内容 | 验收依据 |
| --- | --- | --- |
| 包身份与更新 | 固定 ID/版本/完整 SHA；入口、签名、锁文件和完整性校验；升级另存、保留原包和旧工程 | 官方元数据与本地包一致；未知合同不静默执行 |
| 能力清单 | 原生组、组件、变体、支持语言/比例、必需素材角色、容量和缺少输入行为 | 逐能力映射测试；不能以控件数量代替验收 |
| 内容编排 | 原文事实不改；完整字幕；卡片只提炼完整短句；长文分页/分镜；原生组和组件根据意义选择 | 20 秒、长文、数字/否定词、无图/多素材的独立输入 |
| 人物与素材 | presenter / footage / screen / evidence 等角色分开；实际裁切、主次、字幕安全区 | 用户真实人物、每个画面角色和裁切可追溯 |
| 时钟与声音 | 采用真实音频/字幕时钟；原生动作与音效、旁白、音乐分别绑定；不推算精确词时间 | 完整音频零截断、字幕同步、动作音效听验；不恢复已移除的文案语义阻断 |
| 运行时 | 对每个明确 profile 实现 plan、prepare、preview、render 与错误恢复 | 在本机新内容实际渲染，保存环境和依赖证据 |
| 交付 | MP4、可编辑工程、输入和成片 SHA、版本与素材来源 | 完整解码、帧数/时长/音轨、连续观看和下载回验 |
| 费用恢复 | TTS、数字人、搜索、下载、合成各有状态和缓存；未知受理不重提 | 相同输入重试只恢复缺失本地阶段，不重复付费 |

上述建议与官方规范关于内容容量、运行时可复现、完整动画验收、依赖冻结和升级保留的要求一致；不能把任何一项静态检查通过替代真实产物验收。[官方规范](https://motiongit.com/spec)

## 4. MediaCrawler 的实际边界

本次检查上游 main 对应提交为 `8f583999006d5b692272c608440e193ca282e73b`。实现会继续变化，后续集成须固定其版本，不能把本次观察当所有版本保证。

| 上游现有能力 | 官方证据 | 对本项目意味着什么 |
| --- | --- | --- |
| 按关键词、分页、排序、发布时间搜索抖音 | [DouYinClient.search_info_by_keyword](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/media_platform/douyin/client.py#L182) | 要先由本项目把脚本文案转换成具体视觉检索词；整稿直接当关键词不等于语义匹配 |
| 指定作品 ID/URL 取详情，解析短链接；创作者主页作品 | [DouYinCrawler 入口](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/media_platform/douyin/core.py) | 可支持用户指定链接和自有账号素材的确定性导入 |
| 评论和二级评论，登录态缓存、浏览器/CDP | [官方 README 功能表和启动说明](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/README.md) | 评论不是视频画面证据；登录标记也不是当前真实可搜索的证明 |
| 可选下载视频、封面、图集图片 | [抖音媒体提取器](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/media_platform/douyin/media.py)、[下载开关入口](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/media_platform/douyin/core.py#L405) | 要确认本地文件成功后才可用于成片；详情已取到不代表视频已下载 |
| 默认关闭媒体下载；下载异常不终止数据采集；已存在文件跳过 | [官方 README 媒体下载段](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/README.md)、[config/base_config.py](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/config/base_config.py) | 本产品须单独判断 `downloaded/verified`，不能把爬虫 completed 当素材 ready |

检查到的搜索路径按关键词返回作品信息，媒体路径把详情转换成下载任务。这些代码没有执行“逐句语义理解 → 视觉内容审核 → 镜头内时间段定位 → 与口播时钟剪辑 → 原生模板绑定”这一完整链条；应由本产品的检索和编排层补齐。不要把 Pro 页面宣传的其他 AI 项目能力当作本仓库当前接口。[抖音核心源码](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/media_platform/douyin/core.py)、[媒体提取器](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/media_platform/douyin/media.py)

### 本地项目事实与上游事实不能混淆

本次主任务的本地只读检查反馈：仓库已有 `Sources.douyin → DouyinSource.search → 下载 → review_material` 链，但当前数字人 `templateExecution=auto` 的 `studio_template_auto.storyboard` 只遍历用户已给 materials，未接入 Sources 检索。这是**主制作路线缺少接线**，不是“项目完全没有 MediaCrawler”。`douyin_authorized` 和 `douyin_login_confirmed` 配置标记为真，也不能替代本次浏览器会话、授权范围和下载实测。此段是本地检查结论，与上述上游研究分别记录。

## 5. 文案找素材应有的产品逻辑（建议）

建议主流程：`用户文案 → 真实配音时钟 → 视觉需求计划 → 候选检索 → 内容与来源筛选 → 下载验证 → 镜头段定位 → 模板素材角色绑定 → 本地预览/合成`。素材任务应独立缓存，模板变更通常复用同一批合格素材和原声。

1. **素材策略先明确。** 提供“仅自有/上传”“自有+获授权素材库”“抖音授权素材检索”等策略。允许视频不需要外部 B-roll 时直接使用所选模板的文字与人物表达；不强迫每句找一段视频。
2. **逐句生成视觉需求。** 保存原句、口播区间、核心实体/动作/地点、不可误配的事实、检索词、所需画幅/时长与素材角色。例如“工程款拖欠”可检索工地等待/结算场景，但不能把陌生企业画面包装成该真实欠款案例的证据。
3. **先候选后下载。** 搜索结果保留平台 ID、作者、来源链接、标题和抓取时间；去重、相似度及质量排序。使用画面采样/OCR/本地语音信息复核实际画面，标题相关不等于画面相关。
4. **权利和内容适配分别判断。** 记录谁提供授权、允许用途、归属账号、许可证据与有效期；公开可播放不自动等于允许下载、改编和商业使用。未明确授权的候选可展示来源供用户选择，但不自动并入对外交付成片。
5. **审核镜头内区间。** 保留候选原文件 SHA、可用 in/out、字幕/水印遮挡、人物安全区、画面比例；没有合适镜头就反馈“该句无合格素材”，不能随机插入或反复付费生成来掩盖失败。
6. **绑定实际模板角色。** 主体口播人物保持独立，B-roll 不替代用户人物。官方原生证据组必须使用本期真实证据；情境补充素材要与证据角色区分。模板所需数量不足时选同模板的相容表达或要求补素材，不编造实体/步骤/金额填槽。
7. **中断可恢复。** 搜索失败、登录过期、下载失败、零命中、授权未确认、审核未通过与原生编排失败各有明确状态和下一步。正在排队和已失败不显示同一个“等待供应商”。

## 6. 使用边界对商业集成的影响

MediaCrawler LICENSE 的明确原文为：“未经版权所有者书面同意，不得将本软件用于任何商业用途或对第三方造成不当影响。”README 也将用途限定为学习参考。这不适合直接当本商业视频产品的默认可分发爬虫依赖；建议先完成可替换 `MaterialSearchProvider` 接口，保留已有本地开发入口，商业启用前取得书面授权或选用获授权的实现/数据服务。把进程放本机或单独 sidecar 不会自行改变上游许可条件。[LICENSE](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/LICENSE)、[README](https://github.com/NanmiCoder/MediaCrawler/blob/8f583999006d5b692272c608440e193ca282e73b/README.md)

MotionGit 各详情页声明模板代码 MIT，可修改和商业使用，但版权和许可声明需保留；品牌、肖像、字体、示例图像和声音遵循各自许可。规范开放、包验签成功、网页显示“免费”，均不能代替逐素材授权。新选择器可保留作者与官方来源，个人含密钥包继续仅存忽略的私有位置。[科技控制台许可](https://motiongit.com/@adunext/template-04-dark-console-portrait)、[创作者协议](https://motiongit.com/legal/creator)、[使用条款](https://motiongit.com/legal/terms)

## 7. 不能直接承诺的事项与验收顺序

不能承诺：站点所有模板已取得；每个完整模板任意原生组均支持任意文案；七款均已在本机运行；下载成功代表版权可用；一次搜索必有相关素材；平台登录永不过期；任意 16:9 素材都可无损变成 9:16；视觉封面相似即可视为原生功能完整融合。

建议验收顺序：

1. 目录与官方命名/身份同步，移除新建入口旧别名，历史工程仍能回放。
2. 七款逐包获取与验证，各自记录准确版本、运行时、原生组/组件能力清单和缺失项。
3. 每款用独立新输入完成短片与长稿的无生成费本地回归：真实时钟、人物/素材替换、原生动作与声音、完整字幕、可编辑工程。
4. 将已有素材检索接入数字人 auto 主线；先用离线候选与授权素材验证检索/审核/下载/缓存合同，再在许可与平台授权明确的前提下做小规模真实搜索验收。
5. UI 同步展示真实阶段、可操作异常、费用与已复用产物；最终任务页核对“所选模板 = 实际执行模板版本”，视频播放推进且下载与可编辑工程 SHA 对应。

## 8. 研究证据说明

Firecrawl 已认证并完成小请求检查，本次用于公开详情和中文目录抓取；官方 GitHub 源码通过公开 raw/API 只读取得。公开页面在不同语言/抓取缓存中出现科技风版本差异，已保留为不确定项，不按其中一个值宣称最终安装版本。抓取文本保存在忽略的 `.firecrawl/20261021-*`，不含账号私包或密钥。本文件仅新增研究说明，不修改代码、配置、现有交接或任务账本。
