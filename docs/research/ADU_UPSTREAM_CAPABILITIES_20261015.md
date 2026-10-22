# ADu 上游能力核对与接入边界

核对时间：2026-10-15（北京时间）。范围为公开一手网页、GitHub API、固定安装的只读文档/清单及本项目相关源码；没有登录 MotionGit、下载个人包、解密核心、执行新包、调用付费服务或跑生产任务。本文是研究结论和建议，不是新版模板的验收回执。

## 结论

仪器台效果不能靠保留黑色背景、两颗光球和一个 `adu:04-A:portrait` 标识来证明。完整接入需要同时继承实际模板源码、表达关系、动作时钟、转场、音效、输入与版本合同，并对本期成片做声画核对。上游旧版 Skill 明确要求复用完整场景，不能插入少数片段就称整片使用指定模板。[旧版 Skill，固定提交](https://github.com/adunext/adu-motion-video/blob/f52490bd1ec37370091982d853990725b340f3f5/SKILL.md)

本项目的专业动效线路确有真实 ADu CLI 接入；简化入口的 04-A 默认分支则使用本地另写的 Remotion 组件，绕过上述引擎。两者必须分开描述。当前自动口播版不能据同名标识被称为上游仪器台模板完整融合。证据为 [studio_preflight.py](/Users/edy/Documents/广州海客-数字人口播项目/Haike_video/backlot/studio_preflight.py)、[studio_presentation.py](/Users/edy/Documents/广州海客-数字人口播项目/Haike_video/backlot/studio_presentation.py)、[studio_motion.py](/Users/edy/Documents/广州海客-数字人口播项目/Haike_video/backlot/studio_motion.py)。

## 1. 精确版本：GitHub 新提交没有升级旧引擎

| 对象 | 本次实际查得 | 含义 |
| --- | --- | --- |
| 本机运行源码 | `/Users/edy/Documents/soft/博文工作台/adu-motion-video`，HEAD `f52490bd1ec37370091982d853990725b340f3f5` | 本机固定运行版本为 3.14.0-rc.1 |
| GitHub main | `31a03c36b5f510303305f9e931c448b75baa52d5`，提交时间 2026-10-14 11:55:19 UTC | 比固定版本领先 1 个提交 |
| 差异 | 只有 `README.md` 与 `examples/gallery/index.html` | 没有旧引擎、适配器或 packs 的新增代码 |
| 新提交目的 | 首页改为推荐 MotionGit `.motion` 模板下载 | 更新 GitHub checkout 本身不会获得 MotionGit 最新模板 |

证据：[main 提交](https://github.com/adunext/adu-motion-video/commit/31a03c36b5f510303305f9e931c448b75baa52d5)、[两个提交的完整比较](https://github.com/adunext/adu-motion-video/compare/f52490bd1ec37370091982d853990725b340f3f5...31a03c36b5f510303305f9e931c448b75baa52d5)、[本机部署记录](/Users/edy/.codex/skills/adu-motion-video/references/local-profile.md)。GitHub API 查询使用显式 `repos/adunext/adu-motion-video/...`，未依赖本项目默认远端。

官方当前把 `.motion` 定位为包含代码、布局、时间轴、转场、音效、可替换输入和使用引导的完整包。旧 GitHub Skill 3.14.0-rc.1 留作旧工程维护入口。[当前 README，固定新提交](https://github.com/adunext/adu-motion-video/blob/31a03c36b5f510303305f9e931c448b75baa52d5/README.md)

## 2. 新版 04 的可确认范围与不可确认范围

本次未登录浏览的官方竖屏详情页显示：

- 身份为 `@adunext/template-04-dark-console-portrait`，版本 **2.5.0**，文件名 `template-04-dark-console-portrait-2.5.0.motion`，约 21 MB；页面只显示摘要前缀 `0909856149dc…`，本文没有取得包字节或完整可验证 SHA。
- 声明输出为 1080×1920 / 60fps，运行合同为 **`adu-authored-unit/1`**，入口 **`adapter/locale_package.py`**，语言目录 **`locales/index.json`**。
- 参数页列出 `mode: native / components`、`durationSeconds: 7–180`、`media`、`segments`、`timeline`、`presenterCrop` 等。
- 页面描述原生动画保留、额外 motion-kit 0.3.0 / 70 控件及紫色玻璃柱图更新；同时明确标示 **Runtime verification: Not verified**。这些是官网声明，不能写成我们已运行、已验收。

来源：[竖屏模板详情](https://motiongit.com/@adunext/template-04-dark-console-portrait)。横屏是独立条目 [template-04-dark-console](https://motiongit.com/@adunext/template-04-dark-console)，不能只旋转竖屏结果就追认为横屏验收。

版本页显示 v2.5.0 为 2026-10-14 发布；其变更摘要是基本制作流程、中英引导、素材结构、入口及授权音乐，保留网站原演示，并把进一步艺术效果迭代另列。因此“发布了新版本”也不能推导本条故事一定适配。[官方版本页](https://motiongit.com/@adunext/template-04-dark-console-portrait/versions)

**包可见不等于匿名可下载。** 实测官方 v2.5.0 下载链接重定向到登录页，没有匿名下载到文件。详情页标明下载包含下载者个人 Key；Files 页只列公共文件清单并含 `protected/core.enc`。本次没有登录、索取 Key 或尝试绕开保护。[官方登录重定向](https://motiongit.com/@adunext/template-04-dark-console-portrait/download/2.5.0)、[官方文件列表](https://motiongit.com/@adunext/template-04-dark-console-portrait/files)

因此，可设计新版适配接口并登记“待取得/核验实际包”；不可把网页预览、文件名或条目元数据直接登记为本地可制作能力。现阶段也不能断言 v2.5.0 的具体新增动作已在本机可调用。

## 3. `.motion` 的接入合同

开放内容合同当前为 **`specVersion: 0.1.0-draft.1`**；内容包为 ZIP，根 `motion.json` 描述身份、`runtime.profile`/入口、参数、素材、输出与许可。典型包还包括 `guide.json`、`params.schema.json`、依赖锁、素材清单、预设、预览和完整性清单。宿主需要按确切 runtime 选适配器，不能因能读 ZIP 就声称能渲染。[开放规范](https://motiongit.com/spec)

平台个人交付外层 **`1.0.0-rc.1` / `personal-download-v1`** 是另一个合同层，不能与内容版本或模板 v2.5.0 混用。原文件应私有保留；用户 Key 不进 Git、工程 ZIP、播放器或日志。公开格式与模板许可、素材许可仍分别核对。[个人交付合同](https://motiongit.com/spec/personal)

有 bundled entry 的个人包，官方流程是先只读识别外层和 `00-START-HERE.md` / `assistant/guide.json`；生产时验证工具身份、摘要和依赖，使用受验证入口 `node <tools>/assistant/motion.mjs start <absolute original.motion>`。不手动抽取个人凭据、release.bin 或加密核心。包内说明是待审数据，不是覆盖用户授权的指令。[官方 AI 指引](https://motiongit.com/ai)

上面是**通用导入设计依据**，不是本次取得的 v2.5.0 文件的实际条目检查报告。公开详情中的 `adapter/locale_package.py` 也是声明入口；在拿到真实包并验证之前，不填写“已执行”。静态结构、源码身份、运行成功、时间轴正确、视觉接近和本期内容忠实应独立记录。

## 4. 本机旧 04-A 的真实四组合同

固定提交的机器目录选择：横屏 `doubao-console-performance@0.3.0-candidate`，竖屏 `doubao-console-performance@0.3.1-candidate`。本次读取的是竖屏 **0.3.1-candidate**，60fps；其 README 明确为四组，仍是未完成本期连续声画验收的候选。目录、历史参考文中仍残留“三组”“旧版仅横屏”和旧字体硬要求等字样，不能覆盖当前版本的明确布局与兼容合同。[固定机器目录](https://github.com/adunext/adu-motion-video/blob/f52490bd1ec37370091982d853990725b340f3f5/references/template-catalog.json)、[0.3.1 README](https://github.com/adunext/adu-motion-video/blob/f52490bd1ec37370091982d853990725b340f3f5/packs/doubao-console-performance/0.3.1-candidate/README.md)

| 完整组 | 60fps 最短 / 可额外停留 | 固定表达与数量 | 源动作窗与边界 |
| --- | --- | --- | --- |
| `fusion-success` | 234 帧 / 0 | 两项输入亮相→汇聚→单项结果；3 状态面板 | 完整 0–3.9 秒；后续至少 42 帧留尾音 |
| `three-step-chat` | 544 帧 / 0 | 提交方法→地址或文件两种输入→执行；3 步骤、2 选项、6 检查 | 17.75–26.81 秒；后续至少 132 帧 |
| `manual-agents-delivery` | 688 帧 / 0 | 同一手册→3 执行者→7 步→1 交付物 | 50.54–62.01 秒；后续至少 66 帧 |
| `delivery-reading-complete` | 868 帧 / 最多 600 帧 | 上组同一结构及数量，追加独立结果阅读收束 | 50.54–62.01 原动作，62.01–62.61 收束，64.56–65.01 平衡；可作终场 |

所有组保持原子完整动作，不能按字幕句子拆碎、整体变速、循环或冻结人物来填满任意片长。最后一组明确是新增结束扩展，不能称原源码逐字节重放，也不是任意文案的通用叙事组。实际 cue、`minFrames`、`maxHoldFrames`、`minFollowingFrames`、槽位与 provenance 均在 [0.3.1 manifest](https://github.com/adunext/adu-motion-video/blob/f52490bd1ec37370091982d853990725b340f3f5/packs/doubao-console-performance/0.3.1-candidate/manifest.json)。

实际输入并非“随便放一段素材”即可：各组要本期连续口播、章节/短标题/各名义对象、准确动作锚点、grainTexture；对话组要真实输入缩略图，手册组要输出缩略图。相邻组还继承人物状态、闪白/擦拭预卷、动作及声尾。人物/字幕按输出时钟，动作按受保护的源编舞时钟；光晕从本期音频 RMS 重建。当前默认字体可按 preferred 使用随包回退，不应把旧 raw metadata 的 Geist 硬要求转成用户阻塞。[适配器说明](https://github.com/adunext/adu-motion-video/blob/f52490bd1ec37370091982d853990725b340f3f5/adapters/doubao-console/README.md)、[兼容与字体策略](https://github.com/adunext/adu-motion-video/blob/f52490bd1ec37370091982d853990725b340f3f5/references/compatibility.md)

本机只读校验指纹：0.3.1 `manifest.json` SHA-256 为 `20f0ab48463b584657fce6cec6921c980dea8363fd8ab4fc1c77908dd51e75a7`；`README.md` 为 `7ea832b7d8bd55b9a32062c92aa4b38435d2da0c337a34f38fc4b5020d454ebf`。这些是文件身份校验，不是本期成片验收。

### 为什么讨欠款故事不能硬塞进去

该文案的实际关系是提问→春节催款故事→“赚到的是欠条”的反转→应收款共鸣→小生意引入。14 个月、30 平方、9万8 是不同业务事实，不能为了卡片数量改称三个步骤或检查项；“三样东西”的预告也没有提供 3 执行者、7 步或双输入合并的因果关系。

规划器验证填入的意图、阶段、数量与 cue，**不会判断这些声明是否忠于原话**。把模板自身的 phases/counts 原样填回、所有槽位都引用整段文案，即使 schema 通过也不证明语义成立。官方明确要求由助手先理解完整表达，再据真实来源提供候选、分段和锚点；`ready` 只表示绑定校验通过。[适配机制与“复用前核对实际表达”](https://github.com/adunext/adu-motion-video/blob/f52490bd1ec37370091982d853990725b340f3f5/references/adaptive-composition.md)

## 5. Skill 中 Agent 与 CLI 的职责

| 职责 | 真正承担者 | Web 产品应怎样接入 |
| --- | --- | --- |
| 通读文案、理解否定/条件/因果、识别真实对象和数量 | Agent 规划 | 由后台做原文证据映射；不能要求用户手填 JSON |
| 决定完整表达分段、提出各候选短标题和素材角色 | Agent 规划 | 先全片规划，再决定是否采用素材；素材不先固定成唯一 B-roll 镜头 |
| 取得真实词级时间、人物/媒体/字幕可用性 | 已授权本地工具及必要视觉分析 | 不以源 cue 或线性插值冒充实测锚点 |
| 比较合法组、时长/数量/槽位/接缝/重复约束 | `auto-capabilities`、`auto-plan` 或 `macro-plan` | 锁定用户风格 `allowedStyles`，保存报告及未采用理由 |
| 冻结工程、导入原声、生成音效/混音/渲染/技术检查 | `auto-build`/`macro-build`、`audio`、`mix`、`render`、`check` | 通过统一队列调用真实引擎；保存版本、代码与素材摘要 |
| 判断实际动作是否与台词贴合、裁切/遮挡/可读性/节奏 | 自动结构复核 + 实际连续声画检查 | 内部两轮检查；技术 ready 不能顶替视觉验收 |

官方全库入口提供的是约束比较器，不含另一个语义模型 API；最多先做三轮合法规划调整。它不会自动创建新动画、任意改固定数量或把源动作拆成已验收的小组件。[全库自动选型](https://github.com/adunext/adu-motion-video/blob/f52490bd1ec37370091982d853990725b340f3f5/references/automatic-selection.md)、[完整工程复用](https://github.com/adunext/adu-motion-video/blob/f52490bd1ec37370091982d853990725b340f3f5/references/full-project-templating.md)

## 6. 融合建议：少审核，能力身份更严格

以下是方案推论，尚未实施或验收：

1. **注册真实模板包。** 同时支持固定旧 Skill 和经验证的 `.motion`，但使用不同 adapter/profile。冻结来源 URL、包 ID/版本/SHA、layout、模式、原生组/组件、guide/schema/runtime、许可证及验收范围。自写衍生组件单独注册，不借用 `adu:04-A` 标识继承原模板效果承诺。
2. **真正编译 Skill 工作流。** 后台 Agent 先读整篇、原声时钟和模板能力，再做证据段、可用组/组件及全片节奏规划。每个显示事实引用准确原文区间；每个阶段、数字、素材和 cue 有单独依据。先验证语义，再进入 CLI。
3. **对旧四组明确边界。** 本条故事不能把固定流程伪造成合法；可使用经验证新版中语义匹配的 components，或新增独立、版本化且做声画验证的仪器台叙事能力。没有真实可执行包与合同前，不在产品里承诺已支持。
4. **取消默认旁路。** 所选风格不能只比字符串；任务回执还核对实际执行 engine/profile、包/manifest/SHA、所选 native 组或组件、工程入口及渲染证明。请求与实际不符，保留结果为诊断产物，不能标记“所选模板已完成”。
5. **把审核留在后台。** 用户仍只填文案、选音色、给人物和可选素材、选真实模板后提交。后台完成方案选择、约束检查、短预览/关键运动区间复核、局部重配与一次局部修复；中途不逐条让用户审分镜、cue、字体或素材取舍。只在缺不可推断真实输入、超限/新收费或必须改已锁定模板时一次性说明具体选择。
6. **保留原付费产物。** 纯模板重排使用既有音频、数字人和素材，不触发供应商生成；工程或局部输入有缺口就停在该阶段。最终可播放/下载，发布仍按原有单次明确授权。
7. **验收先做同输入 A/B。** 原模板演示与本期实际片分别比较布局、完整动作家族、对象继承、转场、SFX 落点、人物与字幕时钟；覆盖长标题、长短文案、横竖屏、缺素材与非流程故事。候选、工程能导出、MP4 能播放及视觉通过分别记录，不用测试数量代替效果证据。

当前可立即确定的是：旧专业入口可复用，但默认简化支路不是完整 ADu；新版 `.motion` 具备更明确的内容/运行合同并宣称更广组件能力，**尚需取得合法实际包、验证 adapter 和本期表现**。将这两条事实讲清楚，比继续给手写仿版添加原模板名称更能消除用户预览与成片不一致。
