# Haike Workflow 单仓库入口

工作台、采集、发布、跨模块手册及API账户中心包含于本仓库，保留固定目录布局。根 README.md 和 scripts/setup.ps1 是本版本首次安装入口。历史部署文档中的多仓 clone/checkout、旧提交锚点和便携包说明不适用于本源码仓库。首次迁移来源见 SOURCE-PROVENANCE.json。

- 安装、升级、打包：先读 README.md、docs/DISTRIBUTION.md；完成后运行 scripts/check.py。版本由根 Git 提交统一管理。
- Mac 本机启动、迁移或恢复：先读 README-MAC.md；当前工作目录同时承载 Git 源码与本地运行环境。
- 生产端开发、视频生产或理解：先读 Haike_video/AGENTS.md，再按其路由。
- 采集端开发：先读 copy_skill/copy_skill-main/AGENTS.md。
- 发布端开发：先读 creatorhub/AGENTS.md。
- API收费中转站：先读api-platform/README.md；部署另读api-platform/deploy/README.md，测试使用隔离数据库和假供应商。
- 日常跨模块操作：先读 Haike-Videohub/agent-runbooks/README.md，再读匹配手册并核对实时状态。
- 用户明确说「模板图文视频」：读生产端入口后直接读同名手册，不替换成其他制片路线。

凭据仅存放于忽略的本地配置；安装默认跳过本地 Qwen TTS。付费调用和真实发布按各模块审批闸门执行。上传只包含源码、模板和可分发资源。

代码发现优先使用codebase-memory-mcp：search_graph定位符号，trace_path追调用链，get_code_snippet读取源码；复杂查询用query_graph，架构用get_architecture。仅在图谱信息不足或查找字符串、配置及非代码文件时回退到rg。

开发改动在所属模块执行相关检查。共享手册的维护遵循原有提案机制；本次整合未授权把历史经验标为新机实测。单仓库验收通过不代表真实账号、云服务和另一台物理机已验收。

整个项目优先在本地部署和测试。云端上线、广州网关同步及生产服务切换，必须在本地验证通过后再获得用户当次明确授权；本地验收通过不自动授权上线。

## Git迭代管理

当前自有私有仓库为vincent841218449/haike-workflow，origin指向它，原hrbj18仓库仅为upstream。main为交付基线、dev为集成分支；后续修改从dev建立feat/fix分支，检查所属模块、记录明确提交，通过PR审阅和已授权推送管理迭代。流程见docs/GIT_WORKFLOW.md。

当前4188工作台与8000发布面板从本checkout启动；原源码和安装目录保留用于回退。修改本checkout源码，前端用scripts/build-studio.py构建，再重启本目录管理的服务。编译目录、运行环境和私有数据被忽略；Mac路径写入content_intelligence.local.json。Git提交与云端部署分开；云端账本和主密钥独立备份，代码回退不自动恢复资金数据库。

