# Mac本地工作目录

2026-10-14已完成迁移。当前Codex工作目录同时承载可编辑源码、Git历史和本地运行环境。工作台与发布面板从本目录启动，原源码和原安装目录保留用于回退。

## 打开与关闭

- 数字人口播：[http://127.0.0.1:14754/avatar](http://127.0.0.1:14754/avatar)
- 发布面板：[http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- 双击根目录`一键启动工作台-Mac.command`启动；已有的本目录服务会复用。
- 双击`停止工作台-Mac.command`停止本目录管理的服务。
- 双击`检查工作台-Mac.command`进行Mac运行环境体检。

端口被占用时会选择附近可用端口；实际地址记录于忽略的`.portable/services.json`。原目录入口可能重新启动旧副本，日常使用本目录入口。

```sh
./Haike_video/.venv/bin/python portable/macos.py start --publisher --no-browser
./Haike_video/.venv/bin/python portable/macos.py diagnose
./Haike_video/.venv/bin/python portable/macos.py stop
```

## 源码与Git

沿用私有仓库[vincent841218449/haike-workflow](https://github.com/vincent841218449/haike-workflow)，保留完整提交历史、原分支和标签。当前迁移分支为`chore/avatar-workspace-migration`；迁移前已有的源码改动以独立提交保存。main/dev保持原有流程，见[Git管理](docs/GIT_WORKFLOW.md)。

前端修改后在本目录构建，再停止并启动服务：

```sh
./Haike_video/.venv/bin/python scripts/build-studio.py
./Haike_video/.venv/bin/python scripts/check.py
```

Git保存源码、测试、模板和文档。密钥、数据库、素材、成片、依赖和模型保存在被忽略的本机目录，需另外备份。普通Git克隆不含这些文件；新机器须配置运行环境并另行导入私有资料。

## 验证与迁移记录

前端构建、源码检查、56项回归、Mac运行环境体检、跨模块38项和两个反例检查通过。Playwright确认口播页面、模板弹窗和作品列表正常；服务身份指向本目录，本地字幕模型就绪。迁移提交已推送至origin，提交凭据扫描通过。

数据来源、依赖位置、历史记录保留方式和实际验证范围见[迁移记录](docs/MAC_WORKSPACE_MIGRATION.md)。本次没有执行付费生成或真实发布。
