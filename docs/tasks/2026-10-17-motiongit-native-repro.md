# MotionGit 2.5.7 原生制作阻塞复现

2026-10-17，本地调查。用户明确授权后，已将不含账号凭据、Key、个人包、用户媒体或口播原文的1,794字复现报告提交到[作者模板评论区（comment-4）](https://motiongit.com/@adunext/template-04-dark-console-portrait#comment-4)，已核对发布后完整正文可见，待作者回复。五款新版原生生产仍未开放，组件与既有交付保持不变。本报告是故障证据，不是修复或制作完成证明。

## 控制台原生 plan 回归

同一份合法参数与同一套已有本地媒体，经官方入口对照：

|包|check-params|plan|
|---|---|---|
|控制台竖屏 2.5.2|通过|ready-for-review，7.516666666666667秒|
|控制台竖屏 2.5.7，release 429|通过|退出2，`MotionGit console split-root: 'durationSeconds'`|

顶层 `durationSeconds` 已填写，段落 `durationFrames=451`，符合公开 schema 中 `readme-terminal` 的167–1187帧范围。用不含用户原文的诊断文字再次对照，结果相同。不是通过删除字段、缩短音频或绕过检查获得的旧版成功。

已排除：新中文实例仍复现；参数文件移到素材目录外仍复现；另一合法 `keyword-slam` 原生组合仍复现。给单段额外塞入 `durationSeconds` 被官方参数校验明确拒绝，未将此当作兼容补丁。英文实例要求独立依赖缓存，未将缓存不匹配误认作原故障。

按官网 `update.md` 获取并校验当前 rc.22 工具，使用全新实例、全新依赖缓存，正常 setup 成功、check-params通过，plan仍报同一错误。rc.22为1,017,822字节，SHA256 `ac6ef681d0d5eb7d6654230aa51351a6958bbed1a854e3264ada420798fae7ba`。旧工具与已验收实例未替换。官方 update 查询612和610均返回当前最新版2.5.7，没有可直接应用的新模板修复发行。

此前控制台横屏2.5.7（611）的同类合法输入也记录了相同错误。本次全新缓存及2.5.2对照是612，不宣称611完成了同一套新缓存对照。

### 可分享的参数

仅为接口诊断文字，不作为正式用户视频；媒体由复现者提供，同一剪辑版本且有真实声音和SRT，长度7.516666666666667秒。未附带任何用户媒体。

```json
{
  "mode": "native",
  "layout": "portrait",
  "brand": "本地技术检查",
  "durationSeconds": 7.516666666666667,
  "presenterCrop": {"cx": 0.5, "cy": 0.5, "h": 1},
  "media": {
    "talk": "native-mother.mp4",
    "subtitles": "subtitles.srt",
    "music": "",
    "grainTexture": "@style/assets/noise.png"
  },
  "segments": [{
    "recipe": "readme-terminal",
    "durationFrames": 451,
    "anchors": {"window": 0.09},
    "inputs": {
      "chapter": "技术诊断",
      "window": {"title": "本地输入"},
      "body": "本段仅用于参数与规划接口诊断，不作为用户视频。"
    }
  }]
}
```

在各自新实例与匹配缓存中，运行原包正常 setup 后：

```text
node motion.mjs run PACKAGE --instance INSTANCE --cache CACHE check-params PARAMS --inputs INPUTS --language zh
node motion.mjs run PACKAGE --instance INSTANCE --cache CACHE plan PARAMS --inputs INPUTS --out INSTANCE/plan --language zh
```

需要作者修复正常原生 `plan` 的内部字段读取，发布新的可验签包；当前证据不能定位封装内部的函数行号，不将缺字段的位置猜成用户参数或某个确定内部模块。

## 606、608、610 字幕公开合同缺口

三款2.5.7公开 `params.schema.json` 均只将 `media.captions` 声明为文件路径字符串，说明为 `Paired bilingual timed JSON; measured highlight intervals`。guide要求真实中文词区间，现有可读公开文档未给出可验证的词区间字段结构、单位及与中文文本的绑定规则。不能按字符数量生成假词时码或套入组件字幕格式冒充原生字幕。

guide明确引用的 `capacity-matrix.json`、`adapter/parameter-map.json`，在三款上经已验证官方工具 `read` 均返回退出2/`PUBLIC_DOCUMENT_UNAVAILABLE`。控制台guide引用的 `adapter/native-schema.json` 同样不可读。`locales/zh/native.params.schema.json` 在610也不可读；没有从运行时临时目录获取这些文件。

需要作者通过正式 `read` 入口公开实际原生字幕JSON Schema、真实词时码示例与素材/槽位合同，或提供包含这些公开合同及正常入口修复的新发行。现有原声和离线ASR能力可以复用，当前缺口不能归因于用户没充值或必须重生成数字人。

## 保留与下一步

- 私有回执：`.local/motiongit-native-20261017/`；原故障实例与对照实例分别保留。
- 本次仅发布一条合并评论，包含控制台规划回归及606/608/610字幕合同缺口；无附件。发送原文、发布状态与截图分别保存为 `author-comment.txt`、`author-comment-receipt.json`、`author-comment.jpg`；未发送本地私有路径及报告的交付背景。
- 没有改包、关闭验签、读取/复制瞬态核心、修改云端账本或付费生成。
- 原99.2秒用户成片不变；新版组件路线继续可用。
- 取得实际合同和修复包后，先用本复现对照验证，再完成五款原生规划、真实动作中间帧、声音/字幕、正式队列、任务页播放及工程绑定验收，最后开放原生选择；不能仅因更新了版本号就开放。
