# 2026-10-14 Mac工作目录迁移

当前Codex工作目录同时保存可编辑源码、Git历史和本机运行环境。14754工作台及8000发布面板由根`portable/macos.py`管理，日常入口见[README-MAC.md](../README-MAC.md)。

## 来源与Git

源码来自原`haike-workflow` checkout，保留完整`.git`、main/dev及功能分支、标签、origin和upstream。origin沿用私有仓库`vincent841218449/haike-workflow`。

迁移分支`chore/avatar-workspace-migration`基于`feat/ai-storyboard-materials`的`8e969671`。`a864e39`单独保存迁移前已有的8个文件改动；后续迁移提交包含启动入口、忽略规则、Mac体检和文档。原checkout保持原样。

运行环境与用户数据来自原`haike-workflow-windows-x64-offline-20261012`安装目录，保留四模块布局。迁移前确认原生产队列没有queued/running任务、发布库没有任务；停服务后再次同步本地数据，最后由新目录接管原端口。旧安装目录保留，可显式启动回退。

## 本地数据与依赖

- 6个草稿、10个上传素材、2个已完成生产任务和2个待审作品随本地数据库迁入；素材路径与完成任务的展示路径已指向新目录。
- 私有配置、Key、账号数据、素材、数据库、虚拟环境、Windows依赖、node_modules及运行时均被Git忽略。旧安装副本独有的历史脚本、验收记录与文档留在忽略的`.local/workspace-migration/installation-extras/`。
- ADu动效引擎以固定提交`f52490bd1ec37370091982d853990725b340f3f5`迁入`runtime/adu-motion-video/`，保留其独立版本元数据和本地依赖。无关的旧视频工程仍在原目录。
- 现有Whisper-small模型复制到`runtime/asr/faster-whisper-small/`，核对原SHA256；字幕配置指向本机新Python路径。没有下载新模型。
- Mac启动器将本机路径写入忽略的`content_intelligence.local.json`，公共默认配置保持版本管理；跨模块检查识别Mac Chrome、原生venv和本地覆写配置。
- 历史冻结请求、项目计划与回执保留原始记录；迁移记录和数据库备份留在`.local/workspace-migration/`。Git只备份源码，私有文件需另外备份。

## 验证

迁移回归56项通过：工作台/字幕/下载/分镜49项，根仓库7项（包含Mac启动器3项）。源码检查和前端构建通过；原生运行环境体检通过；跨模块38项0 FAIL，布局和SHA256反例均被捕获。两个保留WARN为MediaCrawler缺Git元数据、候选池默认关闭。

Playwright验证数字人口播、基础与动效模板弹窗、作品列表；健康接口、服务身份、本地字幕就绪状态及10个素材文件均通过。最终服务身份的root为当前工作目录。验证没有执行付费生成或真实发布。

源码保存提交`a864e39`和迁移提交`7640422`已推送至origin的迁移分支。暂存文件及本次两个提交的Gitleaks扫描通过；运行数据、模型和凭据仍留在本机忽略目录。
