# 本地模板成片回归

入口是 `scripts/template_render_matrix.py`，检查证据由
`scripts/review_render_matrix.py` 收集。它们使用隔离的 Studio 数据库和正式
`ProductionQueueWorker`，调用现有 `studio_avatar` / `studio_motion` 生产器；不连接供应商、采集或发布服务。

## 输入与执行

私有输入 JSON 显式提供 `source_video`、`source_audio`、原 `draft` 和横屏
`evidence_video`。原声音旁的 `local-asr.json` 提供已有真实时间轴。
`fixture_labels` 保存本轮短显示文字；`clip_starts` 只能填写核对过的语音停顿；
`basic_scene_overrides` 可复用原项目素材编号，或显式指定 `presentation: "text"`。
输入 JSON、人物、配音、素材、私有 `.motion` 包与成片均留在忽略目录。

```bash
# 在仓库根目录运行，先设置 HAIKE_ADU_ROOT 为已安装的固定版本。
Haike_video/.venv/bin/python Haike_video/scripts/template_render_matrix.py \
  prepare .local/template-qa --source /绝对路径/本期测试输入.json --skip-basics
Haike_video/.venv/bin/python Haike_video/scripts/template_render_matrix.py \
  run .local/template-qa
Haike_video/.venv/bin/python Haike_video/scripts/review_render_matrix.py \
  .local/template-qa --output output/template-qa
```

基础模板的完整口播与素材另用 `prepare-basics`，随后同样执行 `run`。
中断后先读原队列；已完成的案例不重复提交。每轮修改另存测试根目录，保留原失败记录。

## 验收范围

- 当前菜单对应 3 个基础模板、21 个旧 ADu 风格/画幅绑定及 1 个 MotionGit 完整包绑定。分组数、版本与画幅以当前运行时目录为准。
- 原生固定组使用完整动作及真实口播片段，结尾落在语音停顿。测试声明的语义和数量属于视觉回归夹具，不证明任意故事都符合该固定编舞。
- 基础模板和自由口播组件路线可复用完整口播；MotionGit 的原生固定组与官方组件路线分别记录，不能混为相同的样片编舞。
- 必须核对实际 MP4、尺寸、帧率、总帧数、声画时长、完整解码、编码后响度/真峰值、动作前后帧、字幕和取景。`ready`、模板名称及来源指纹只能证明前置合同，不能替代实际成片。
- 抽帧检查、连续画面检查、实际播放器验证与听音分别记录。脚本保持 `visual_review: pending` 和 `listened: false`，不会自动冒充人工观感验收。
- `reviewed` 只能在检查对应图片后填写。完整包的内外两层预览需要相同的实际图片与未变更工程，不能直接删闸门或给旧图盖新章。

本轮修复涉及离线分镜复用、情境视频填满素材窗口、基础口播文字卡、原文字幕校正、
旧纸面聚合字幕字段兼容、仪器台竖屏字幕避让、双层原生预览核验，以及保留视频流的交付响度处理。
逐模板结果、真实产物及本机证据以 `output/template-render-matrix-20261016/` 报告为准；
此文档本身不宣称所有案例已通过，也不授权付费调用或上线。
