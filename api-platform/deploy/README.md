# 广州云端部署

入口 `https://8.138.207.71:17894/`，统一 API 地址 `https://8.138.207.71:17894/v2`。外部端口保持 17894，独立 Nginx 服务终止 TLS，再转发至只监听回环的 17895 后端。复用该主机已有的受信任 IP 证书及 `autoclip-cert-renew.timer`。2026-10-15维护后，续期任务独立清除失效代理环境，每6小时检查、最多错峰10分钟，失败后每小时重试；成功签发即通过deploy hook验证Nginx配置并热加载本服务，原6小时加载定时器继续兜底。不会修改其他服务的 Nginx 配置。

证书维护记录和验收见 [2026-10-15证书维护](../../docs/tasks/2026-10-15-cert-renewal.md)。`repair-cert-renewal.sh` 是本次已执行方案的可审阅源码，需明确维护授权后在目标服务器以root运行；它先验证直连、备份证书和定时器，再修复续期链路，不发布业务代码或修改账本。不要通过关闭TLS校验或改用HTTP绕过证书故障。

代码 `/opt/haike-api-platform/current` 指向独立版本目录；Python 3.12 位于 `/opt/haike-api-platform/python`。依赖以 uv.lock 导出带 SHA256 的 requirements.lock.txt，通过镜像安装时要求全部版本与校验值匹配。运行进程为单独的 haike-api 系统用户，代码只读、数据目录 0700、文件 0600。服务自动启动和失败重启，1 GiB 内存上限。

账户、Key、充值及调用账本位于 `/var/lib/haike-api-platform/platform.sqlite3`；供应商配置和对应主密钥也在该私有目录，不能发布到静态资源或源码仓库。每日 03:20 执行 SQLite 一致性备份，并包含加密配置及上传文件，保存到 `/var/backups/haike-api-platform`。备份目录只允许服务用户读取。已复制的会话清除，用户重新登录；账户 ID、余额及原有平台 Key 保留。

云端必须显式设置 `--public-origin https://8.138.207.71:17894`；Host/HTTPS Origin 不匹配会拒绝。只信任来自回环代理的转发头，Cookie 标记 Secure、HttpOnly 和 SameSite。保留 CSRF、权限隔离、登录错误频率限制，代理对登录及注册另加每 IP 频率限制。缺少管理员时拒绝启动；云端管理员初始化入口关闭。

切换时先确认本机和云端均无未完成任务，停止本机账本，再复制最后快照，启用云端为唯一账本。本机 data/cloud-origin.txt 保存云端入口，现有 Mac/Windows 启动器之后启动 run.py 时只提供跳转，不启动第二套账本。客户端应将 Base URL 更新为云端地址。

运维命令：

```sh
sudo systemctl status haike-api haike-api-proxy
sudo journalctl -u haike-api -n 50 --no-pager
sudo systemctl restart haike-api
sudo systemctl reload haike-api-proxy
sudo systemctl start haike-api-backup
sudo systemctl list-timers 'haike-api-*'
```

更新采用新版本目录及显式切换 current。恢复数据库前停止后端并保留当前数据快照；恢复时必须同时保留与加密供应商配置对应的主密钥。不可把旧账本重新当作另一套可消费余额启动。
