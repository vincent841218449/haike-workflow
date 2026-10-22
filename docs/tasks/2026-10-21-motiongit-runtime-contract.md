# MotionGit 当前个人包与原生制作合同：实施补充研究

日期：2026-10-21（北京时间）。本文件仅研究官方公开资料和公开 helper 源文本；未读取本地个人包/密钥、未登录、未执行 helper、未签发/下载个人包、未调用任何生成接口。用户已说明 MediaCrawler 及素材具有许可，本次技术实施以该授权范围为前提；不再将上轮尚未确认的许可作为要求用户重复确认的理由。

## 1. 当前官方支持的入口

官方当前更新指引是 [update.md](https://motiongit.com/update.md)。已明确要求使用验过官方 HTTPS 元数据的 helper，通过原始个人 `.motion` 完成升级；旧包和项目保留，新包另存，不把个人包展开到项目中。

本次公开元数据读取结果：

| 字段 | 研究时的实际值 |
| --- | --- |
| 元数据 URL | `https://motiongit.com/assets/motion-runtimes/latest.json` |
| profile | `motiongit.assistant-runtime/1` |
| helperVersion | `1.0.0-rc.35` |
| minimumNode | `22` |
| bytes | `1045076` |
| sha256 | `f995d62a0d41e47c9dcb5589ec51e0c773fdb6a7ce4cda2114a6d1c015554444` |
| 对应公开源码 URL | `https://motiongit.com/assets/motion-runtimes/1.0.0-rc.35.mjs` |

元数据会变化，实施时仍应重新读取并校验，不能永久信任本表。公开 `.mjs` 本次仅按文本取得并校验大小/SHA，没有执行。官方方法要求固定 HTTPS、拒绝重定向、Node 22+，并将工具保存在私有工具目录。[官方更新入口及校验示例](https://motiongit.com/update.md)

公开 helper 的命令帮助确认以下语法；前缀始终为 `node <verified-helper.mjs>`，不需要全局 `motion` 安装：

```text
start   <personal.motion>
read    <personal.motion> [public/path.json|md|txt]
new     <personal.motion> <instance-dir>
update  <personal.motion>
upgrade <personal.motion> [--output <new.motion>]
update  <personal.motion> --download <new.motion>
run     <personal.motion> <operation> [args]
```

`update` 是匿名版本查询；`upgrade` 执行确认范围内的更新和续传，并完成新版首读；`read/new` 可附带一次有界的免费更新检查，不自动下载。网络失败应呈现“状态未知”，不能报告“已是最新”。[个人分发规范](https://motiongit.com/spec/personal)、[公开 rc.35 helper](https://motiongit.com/assets/motion-runtimes/1.0.0-rc.35.mjs)

### start 与 read 的可实现返回合同

当前公开 helper 的 `start` 返回 `profile: motiongit.assistant-start/1`、`verified`、`productionEntry`、`templateGuide`、`assistantGuide`、`runtime`。其中：

- `productionEntry.guide`：当前实际读取的制作引导路径。
- `productionEntry.parameterSchema`：当前顶层参数 schema 的公开路径，缺失则为 null。
- `productionEntry.publicParameterSchemas`：实际公开文件中以 `.schema.json` 结尾的路径清单，已排序。
- `productionEntry.extension`：仅在引导确有相应声明时返回，包含 `workflow`、`parameterSchema` 和建议 `read` 命令。
- `runtime.coreExecuted` 为 false：首读成功不等于已运行模板或完成渲染依赖检查。

`read PACKAGE path` 校验包身份后，读取该包发布层存在的安全 JSON/Markdown/TXT；返回 `path`、`deliveryIdentity`、`currentTemplate`、`documentLayer: release-public-document`、`archiveDocumentSha256`、`content` 等。路径不存在或不允许读取时报 `PUBLIC_DOCUMENT_UNAVAILABLE`。不能凭 guide 引用的名字就假定文件可读，也不能转而监视临时核心目录找字段。[公开 rc.35 helper 中的 start/read 实现](https://motiongit.com/assets/motion-runtimes/1.0.0-rc.35.mjs)、[官方 AI 首读指南](https://motiongit.com/ai)

**实施顺序建议：** 经验证的原包 → `start` → 保存实际 delivered 身份 → `read` 顶层参数 schema、语言版 native schema、字幕合同 → 根据该合同创建新实例 → `run` 该模板实际支持的操作。组件目录仅描述单个控件属性，不能代替顶层 `workflow/timeline` 结构。[官方更新指引](https://motiongit.com/update.md)

## 2. 正常下载与更新机制：不可混用的两种情况

### A. 从未取得该模板的首次获取

官方公开指引是：在模板详情正常登录，使用下载按钮；可选的 ZIP compatibility 与同次准备的 `.motion` 内容、签名和账户绑定相同，不产生另一个 Key。不能把老模板的 `upgrade` 当作任意其他模板的首次获取 API。本次未找到官方公开、可直接使用一个现有包跨模板签发任意新模板的 CLI 合同。[官方正常下载帮助](https://motiongit.com/help/download)

如果 Chrome 继续拦截某一浏览器动作，应准确记录拦截与阶段，不通过猜隐藏端点、复制会话、关闭拦截或拆除包身份来绕过。已有模板的官方独立升级机制可以按其文档使用；这与绕过首次浏览器下载不同。

### B. 已有该模板、已有有效且获授权的个人包

官方推荐 `upgrade OLD.motion`，沿原包有效凭据增量复用文件、持续保存操作记录和分段、有限恢复并重新验签；不需要网站 Cookie，不打印或外拷 Key。中断后重复同一命令，而不是删除锁/分段重新签发。长过程持续有进度时允许等待，保留日志和最终完整 JSON。[官方自动更新合同](https://motiongit.com/update.md)

成功判定：最终 `motiongit.upgrade-result/1` 的 `status` 是 `updated` 或 `refreshed`、`verified: true`、`activePackage` 实际存在。`refreshed` 是同模板版本/内层发布包的个人封套 helper 刷新；`current` 不会重新下载或签名，也不能冒称旧入口已修复。摘要用 `personalArchiveSha256/personalBytes` 校验个人文件，不能拿内层 release SHA/大小替代。[官方升级结果合同](https://motiongit.com/update.md)

## 3. 官方文档给出的精确 HTTP 合同

优先使用已验证 helper，避免产品自己复制身份/重试/续传逻辑。以下仅记录官方已公开端点及字段，**本次未向这些认证端点发送请求**。

| 用途 | 官方接口与关键字段 |
| --- | --- |
| 匿名发布更新查询 | `GET https://motiongit.com/api/v1/template-updates`；query 来自已验证 receipt：`registry, templateId, authorAccountId, releaseId, currentVersion, releaseArchiveSha256, helperVersion` |
| 原包授权更新状态 | `GET https://motiongit.com/api/v1/template-updates/status`；原包 Bearer 与来源上下文 |
| 确认一次更新签发 | `POST https://motiongit.com/api/v1/template-updates/download`；原包 Bearer、`X-MotionGit-Package-Context`、耐久 UUID `Idempotency-Key`；body 为 `{profile:"motiongit.bearer-template-update/1",target:{releaseId,templateVersion,releaseArchiveSha256,releaseSize}}` |
| 取已签发个人包 | 官方结果返回的固定 `GET https://motiongit.com/api/v1/template-updates/downloads/<downloadId>.motion`；不是根据网页 slug 自行猜测的路径 |

`X-MotionGit-Package-Context` 是 JCS JSON `{v:1,downloadId,receiptSha256}` 的 UTF-8 base64url；`receiptSha256` 必须取实际 receipt 文件字节。状态包含严格 legacy `template_update`、`template_download` 与 helper 能力；关闭下载时 `downloadUrl=null`，`downloadAvailable=false` 或 `template_download.status=closed`，不得自行绕过。来源是[个人分发规范更新段](https://motiongit.com/spec/personal)；`/api/v1` 全前缀也由[公开 rc.35 helper](https://motiongit.com/assets/motion-runtimes/1.0.0-rc.35.mjs)确认。

签发元数据 profile 是 `motiongit.bearer-personal-download/1`，包含 `downloadId`、目标版本与身份、`personalArchiveSha256`、`personalBytes`、`downloadUrl` 等；helper 验证身份、原收件人、签名和文件后才另存。已有原包更新保留其原凭据；原凭据停用、撤销或过期不能自动换用其他 Key。[官方个人分发规范](https://motiongit.com/spec/personal)

## 4. 2.7.11 原生参数与字幕合同的可读线索

本次 Firecrawl 实时抓取的官方 Files 页已显示 2.7.11，但 Web 搜索工具对同 URL 曾返回三日前缓存 2.5.7。应以实际签名个人包和固定发布版本为准，不能依赖搜索缓存断言缺文件或最新状态。

| 模板官方 Files 页面 | 研究时公开列出的文件（大小与短 SHA 仅为列表元数据） |
| --- | --- |
| [科技控制台 · 竖屏](https://motiongit.com/@adunext/template-04-dark-console-portrait/files) | `native.params.schema.json` 149 KB / e518d065；`adapter/native-schema.json` 136 KB / a6a34042；`CAPTIONS-EXPORT.md` 5.7 KB / 6177f9b4；`locales/zh/` 与 `locales/en/` 对应参数和说明均列出；共 88 个文件 |
| [现代图文 · 竖屏](https://motiongit.com/@adunext/template-01-integrated-portrait/files) | `native.params.schema.json` 6.0 KB / 564aafc8；`CAPTIONS-EXPORT.md` 7.4 KB / d91fb238；语言版 native/params/kit schema 均列出；共 86 个文件 |

Files 页展示文件名、大小与 hash，但本次读取的公开 HTML没有为每个文件提供可直接获取内容的 HTTP 链接。因此上述元数据只证明“当前公开列表列出了文档”，尚不证明已读到完整字幕字段、单位、文本绑定或 native plan 已通过。**不要由文件名猜 `media.captions` JSON 格式。**

实施侧可使用当前 helper 的 `productionEntry.publicParameterSchemas` 得到真实可读路径，再 `read` 精确的顶层、locale native schema、`CAPTIONS-EXPORT.md`、`NARRATION-MAP.md` 及其实际引用的合同。如果 guide 广告了某个文件而新包 read 仍缺失，保留具体路径与版本错误，不读临时核心也不伪造词时间。[官方 AI 指南](https://motiongit.com/ai)、[当前 rc.35 read/start 机制](https://motiongit.com/assets/motion-runtimes/1.0.0-rc.35.mjs)

## 5. 不能声称 2.7.11 已明确修复旧原生计划错误

[科技控制台官方发布说明](https://motiongit.com/@adunext/template-04-dark-console-portrait)对 2.7.11 明确写到人物窗口/完整字幕间距、浏览器及色彩工具识别、预览错误提示；2.7.10写到渲染/预览与裁切图遮挡字幕误判。它们没有明确点名已修复 2.5.7 native plan 的 `durationSeconds` KeyError。

同页官方社区仍能读到 2026-10-17 的脱敏复现：顶层 durationSeconds 已给，check-params 通过，plan 报 `MotionGit console split-root: 'durationSeconds'` / locale operation failed；并请求公开原生字幕合同。这是用户提交的问题报告，**不是作者已确认修复的证据**，本次未看到作者对应公开答复。

建议本地按原最小复现、真实 7.5166666667 秒有声视频和匹配 SRT，在新签名包独立实例执行 `check-params → plan → prepare/preview → render`。新合同若有差异则按公开 schema适配，保持原视频/音频及真实时钟不变。只有新包实际 plan 和真实渲染通过才将该能力标为 integrated/acceptance-passed；20 秒测试通过也不能替代 581 字长稿与完整字幕回归。

## 6. 给本轮实施的决策建议

1. 对已有五款实际包用 rc.35 官方 upgrade，逐个串行执行，固定保存结果；新模板首获走官方正常下载，不能把“全部7款目录可见”当“全部7包已获取”。
2. 升级后的每款记录 actual template/release/helper/locale 身份和独立 schema 列表；运行时的“native 与组件入口”必须分别实现并测试。
3. 源码集成不复制个人包凭据。参数/素材/工程与 verified helper、私有包分离，交付 ZIP 不含个人原包和 Key。
4. 用户已授权本轮素材许可的前提下，继续主代理实施 Sources 接线；该授权不代表需要本次 MotionGit 升级过程中再使用任何外部付费生成，配音/数字人缓存保持复用。
5. 当前公开文档足以支持正常旧包升级和读取真实 schema；不足以支持猜测任意新模板首次下载 API或宣称旧 native plan 错误已修复。未满足时应报告具体缺失合同，而不是静默换成通用 title/quote 路线。

研究缓存位于忽略的 `.firecrawl/20261021-motiongit-*`、`20261021-*-files.*` 与 `20261021-public-helper.mjs`；只含公开网页/公开 helper。本文件不修改产品代码、配置、任务账本或既有交接。
