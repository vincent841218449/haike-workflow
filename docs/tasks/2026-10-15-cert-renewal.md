# 2026-10-15 中转站证书维护

用户明确授权续期并修复自动续期。本轮仅维护现有广州服务器的证书和相关定时任务，未发布项目新功能，业务版本仍为 `20261014-unified-gpt-v2`，未修改账本、用户Key或供应商配置。

## 故障证据

公网17894证书在2026-10-15 11:16:11（北京时间）过期；标准TLS校验返回 `SSLCertVerificationError` / verify_code 10。账户和音色请求在鉴权之前就被阻断，换Key不能解决。

`autoclip-cert-renew.timer` 原为每12小时检查，虽已启用，但续期服务多次失败：环境中的HTTPS代理指向已停用的 `172.17.0.1:18888`，连接被拒绝。原deploy hook只加载AutoClip网关，海客API依靠独立的6小时加载定时器。Certbot 5.4还会在非交互续期时额外随机等待，本次观察到458秒。

## 已执行修复

- 使用原Certbot、ACME账户、IP、webroot及shortlived profile，保留TLS验证。
- 新增续期服务drop-in，只清除该服务的六种代理变量；每6小时检查、错峰最多10分钟，失败后1小时重试、单次超时10分钟。
- 用已安装源码及[官方CLI定义](https://github.com/certbot/certbot/blob/main/src/certbot/_internal/cli/__init__.py)核对隐藏参数 `--no-random-sleep-on-renew`，避免与systemd错峰重复等待。该参数不会出现在 `--help all`，不能用帮助文本判断是否支持。
- 新增 `renewal-hooks/deploy/50-haike-api-proxy-reload`：Nginx配置校验通过后热加载海客API代理，并验证新证书至少48小时内有效。保留原AutoClip加载hook和海客6小时兜底定时器。
- 配置及证书仅在云端私有目录备份。最终运行备份路径：`/var/backups/haike-cert-maintenance-20261015T034045Z`。私钥和账户文件未下载到源码仓库。

可审阅维护脚本：`api-platform/deploy/repair-cert-renewal.sh`。通过阿里云命令助手执行；最终命令名称 `haike-cert-renew-final-20261015`。未安装新软件、开放新端口或重启业务后端。

## 验收

- 新证书到期：2026-10-22 02:42:18（北京时间）。证书本身仍有固定有效期，通过自动续期保持可用。
- 公网标准TLS握手通过，未跳过证书验证。
- 续期服务 `Result=success`、`ExecMainStatus=0`；续期及兜底定时器均enabled/active，代理和API服务active。维护脚本校验了业务release符号链接未变。
- 本地4188 `GET /api/studio/account` 返回200，读取6项能力；`GET /api/studio/voices` 返回200，7个官方系统音色恢复显示。
- 脚本 `bash -n` 通过。证书维护不等同于上线7音色真实制作接口；该功能仍按原本地优先约定单独验收。
