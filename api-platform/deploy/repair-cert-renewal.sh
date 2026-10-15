#!/bin/bash
# Existing Guangzhou certificate maintenance only; no business release or ledger changes.
set -Eeuo pipefail
umask 077
test "$(id -u)" = 0
CERT_HOME=/opt/autoclip/shared/letsencrypt
CERT_FILE="$CERT_HOME/live/8.138.207.71/fullchain.pem"
test -f "$CERT_FILE"
test -x /opt/autoclip/certbot-venv/bin/certbot
test -f /opt/haike-api-platform/current/deploy/nginx.conf
/opt/autoclip/certbot-venv/bin/python - <<'PY'
import inspect
from certbot._internal import cli
# Certbot deliberately hides this supported automation flag from --help all.
assert '--no-random-sleep-on-renew' in inspect.getsource(cli)
PY

# Fail before changing configuration when direct ACME access is unavailable.
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  curl -fsS --max-time 25 https://acme-v02.api.letsencrypt.org/directory -o /dev/null

BACKUP=/var/backups/haike-cert-maintenance-$(date -u +%Y%m%dT%H%M%SZ)
install -d -m 700 "$BACKUP"
cp -a "$CERT_HOME" "$BACKUP/letsencrypt"
for entry in autoclip-cert-renew.service autoclip-cert-renew.timer autoclip-cert-renew.service.d autoclip-cert-renew.timer.d; do
  if [ -e "/etc/systemd/system/$entry" ]; then
    cp -a "/etc/systemd/system/$entry" "$BACKUP/"
  fi
done
readlink -f /opt/haike-api-platform/current > "$BACKUP/business-release-before.txt"
openssl x509 -in "$CERT_FILE" -noout -dates
# Stop the old randomized wait before reloading the service definition.
systemctl stop autoclip-cert-renew.service

python3 - <<'PY'
from pathlib import Path
import os

files = {
 '/etc/systemd/system/autoclip-cert-renew.service.d/50-haike-reliable-renewal.conf': '''[Unit]
StartLimitIntervalSec=0
[Service]
UnsetEnvironment=HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
ExecStart=
ExecStart=/opt/autoclip/certbot-venv/bin/certbot renew --quiet --no-random-sleep-on-renew --config-dir /opt/autoclip/shared/letsencrypt --work-dir /opt/autoclip/shared/acme-work --logs-dir /opt/autoclip/shared/logs/acme --deploy-hook "docker exec autoclip-guangzhou-gateway-1 nginx -s reload"
Restart=on-failure
RestartSec=1h
TimeoutStartSec=10min
''',
 '/etc/systemd/system/autoclip-cert-renew.timer.d/50-haike-reliable-renewal.conf': '''[Timer]
OnCalendar=
OnCalendar=*-*-* 00,06,12,18:00:00
RandomizedDelaySec=10m
Persistent=true
''',
 '/opt/autoclip/shared/letsencrypt/renewal-hooks/deploy/50-haike-api-proxy-reload': '''#!/bin/sh
set -eu
/usr/sbin/nginx -t -c /opt/haike-api-platform/current/deploy/nginx.conf
/usr/bin/systemctl reload haike-api-proxy.service
/usr/bin/openssl x509 -in /opt/autoclip/shared/letsencrypt/live/8.138.207.71/fullchain.pem -checkend 172800 -noout
''',
}
for name, content in files.items():
    path = Path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(content)
    temporary.chmod(0o755 if 'renewal-hooks' in name else 0o644)
    os.replace(temporary, path)
PY

systemctl daemon-reload
systemctl reset-failed autoclip-cert-renew.service
systemctl enable --now autoclip-cert-renew.timer
systemctl restart autoclip-cert-renew.timer
# Existing certificate is due; renew normally, keeping its account, IP and profile.
systemctl start autoclip-cert-renew.service
systemctl start haike-api-tls-reload.service

openssl x509 -in "$CERT_FILE" -checkend 172800 -noout
openssl x509 -in "$CERT_FILE" -noout -dates
test "$(readlink -f /opt/haike-api-platform/current)" = "$(cat "$BACKUP/business-release-before.txt")"
systemctl show autoclip-cert-renew.service -p Result -p ExecMainStatus
systemctl is-enabled autoclip-cert-renew.timer haike-api-tls-reload.timer
systemctl is-active autoclip-cert-renew.timer haike-api-tls-reload.timer haike-api-proxy.service haike-api.service
systemctl list-timers '*cert*' '*tls*' --all --no-pager
printf 'CERT_MAINTENANCE_BACKUP=%s\nCERT_MAINTENANCE_OK\n' "$BACKUP"
