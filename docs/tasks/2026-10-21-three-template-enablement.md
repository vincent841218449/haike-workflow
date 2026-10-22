# 三款竖屏模板正式制作接线及零生成费验收

2026-10-21。本轮接续用户“还有这3个模板，为什么不能使用”，修复实际制作链路后才更新本机可用状态。仅本地；没有新增配音、数字人、远端AI请求、发布、部署或云端账本变更。根.taskmaster/tasks/tasks.json为既有用户改动，未纳入提交。

## 原因与实现

- 鲜色角色2.7.11：候选包未登记实际可制作模式。新版导演接口、所选原包组件、真实声画、正式队列和工程导出已串联；不会换成旧版三组件编译器。
- 活力海报2.7.10：发布的70个组件并非全部完成海报配色验收。正常官方read返回的poster-kit-guide明确只有7种推荐表达已适配。自动导演现在只接收kinetic/wave、qa/flip、flow/chain、polaroid/drop、mindmap/radial、checklist/clipboard、cta/button；已确认完成的行动才能采用划勾清单。缓存模型响应同样检查范围。高级手动编辑仍可用70组件，其他变体须看实际预览。修正文字运动区边界，保留原包红底与白/黄文字，不再自动选浅底白字的通用highlight。
- 酷炫科技风0.2.29-open-beta：与motion-kit/poster-kit不同，缺少正常user-media入口的生产适配。新增独立原生编排、正常check/plan/prepare/preview/render、精确来源绑定、原队列、完整有声产物选择及工程导出。当前自动路线为官方B1–B4基础表达；原片复杂27组未开放。完整字幕保留，关闭字幕会在收费前提示版本能力限制。没有改运行器白名单、读取保护核心或把静态人物检查片当成成片。
- 科技风时间轴采用本机已有faster-whisper/CTranslate2声学DTW，把**用户原文**定位到原音轨。没有识别转写文字与文案一致性校验，没有按ASR改写用户字幕。时间证据绑定原声SHA，缓存破坏/来源改变时保留旧结果，不重配音；离线环境与失败日志可恢复。正式输出仍用原音频，不改变语速。
- ZIP导出改为逐项核对后复用已完成工程，保持重复恢复的MP4/ZIP摘要不变；改变输入拒绝覆盖旧工程。科技风ZIP只含可编辑参数、计划及本期素材，不含个人包、凭据和生成的保护运行时；需用户自己已验证的原包恢复编辑。

## 实际验证范围

复用同一19.6秒人物、配音及完整测试文稿。原声SHA `b709e48a1b3e881fe1f04c53d3e420a602101cdbfb4e673caac7c8aef2614bd3`，人物视频SHA `499222a32a11c5c9af51e4e75629535126f87a173e792b5a78ba8794057e08e7`。

`Haike_video/scripts/three_template_acceptance.py`经过真实production preflight与导演响应校验，但导演/语义复核返回是**显式离线测试夹具**，远端模型调用0；不冒充真实模型自动编排验收。声学定位、签名模板运行器、实际预览、统一队列、成片及工程是真实运行。鲜色角色使用keyword/slam、quote/card、kinetic/wave三种原包表达；海报使用原包已适配kinetic/wave；科技风本期用B1/B4两镜头。其他表达的视觉遍历、真实远端导演和581字长稿在这三款上尚未全部验收。

| 模板 | 隔离队列任务 | MP4 SHA256 | 工程SHA256 |
| --- | --- | --- | --- |
| 鲜色角色 | PQ-80e26c89d231d0b931f3 | 4a25864a11af2184e17611492ff200d993f719b92498cfaed97a4a9f94c145b0 | 93967ff2218a70337ce34d6ab4f5f41061aafddd5fd2b7a38b8908a2b0837448 |
| 活力海报 | PQ-62174d807cd685d2e372 | c8c410ea053bf7d0fdc39df85a99a18c319ab38d11f7831af0112460f60cf189 | f6c3a491577b0bf128c855e2b39fa85bca7eaaa23be97cc7095e4ac046b8b53c |
| 酷炫科技风 | PQ-4968462e4c1a9a48dc50 | bb31f607c2ad9e93a23119a62dbe7738929eee5e44693bdf239d4d151294cae7 | 17ad3a0e0b8deb0d7a7b3c09a8a36582eeaca6b7baaa53f43671f1f95d17af40 |

三片均H264/AAC、1080×1920、60fps、19.6秒/1176帧，完整解码与交付响度通过；ZIP中delivery.json绑定对应成片SHA。代表性实际视频帧已查看，未做连续人工听验，listened=false如实保留。对三片逐个禁止render后再调用正式finish，均恢复完成且MP4/ZIP逐字节不变。

证据：`output/three-templates-20261021/{pass5,pass7,kinetic2}/*-result.json`，`component-contact.jpg`、`kinetic-contact.jpg`。隔离任务未导入用户正式任务列表，前置人物布局片不作交付。

## 本机开放范围与剩余工作

本机忽略的registry仅为614/624登记components、626登记native；production_ready仍false，不能据此开放所有原生组。四款既有可制作版本保持，合计7个官方竖屏身份均可选。所选精确包、制作模式与产物来源仍校验；官方封面/案例独立保留。

真实网络素材槽仍有字幕/人物重叠未通过，网络素材开关继续关闭；本轮不把素材搜索下载成功当作模板真实合成成功。全原生组、长稿、局部编辑重排仍按后续独立验收推进。

相关后端178项通过，前端52项通过。构建、根源码检查（3244文件/1180 Python）、交接预算与暂存凭据扫描通过。本机已重启加载；catalog中三款supported/automatic_ready均true。空白测试草稿逐项点击三款均保存成功，科技风实际保存auto/385712精确模板，页面显示官方原生表达及完整字幕，不再链接到错误的组件编辑器。没有点击收费制作。

原581字r15的MP4、ZIP、narration、tts-source、avatar-source、local-asr六项SHA再次与基线一致；正式队列仍24条（17完成、5失败、1待处理、1取消）。本机三份缓存测试片/工程另存`output/three-templates-20261021/delivery/`，不伪装成用户原任务的新版本。
