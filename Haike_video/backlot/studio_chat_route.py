"""Freeze each AI request route; never move an accepted/unknown submission."""

import hashlib
import json

from backlot.studio import atomic_private, timestamp
from backlot.work_catalog import WorkError


def direct_identity(config, model):
    return hashlib.sha256(
        json.dumps([config.get("base_url"), config.get("api_key"), model]).encode()
    ).hexdigest()


def use_gateway(relay, path, payload, config, lock):
    with lock:
        saved = json.loads(path.read_text()) if path.exists() else None
        if not saved:
            return config.get("chat_route", "gateway") != "direct"
        if not saved.get("gateway"):
            return (
                False  # An old direct request stays bound even after a default switch.
            )
        if config.get("chat_route", "gateway") != "direct":
            return True
        journal = (
            relay.studio.private
            / "haike-api/intents"
            / (saved.get("intent", "") + ".json")
        )
        # A prepared record without a quote/journal has never reached SDK confirm
        # or wait. Only this preflight can use the newly configured local route.
        if (
            saved.get("status") != "prepared"
            or saved.get("quote")
            or saved.get("gateway_job_id")
            or journal.exists()
        ):
            return True
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()
        if saved["fingerprint"] != fingerprint:
            raise WorkError("原AI任务内容已冻结，不能在恢复时替换参数")
        if not config.get("base_url") or not config.get("api_key"):
            raise WorkError("本机AI连接尚未配置，未迁移或提交原请求", "unavailable")
        previous = {
            k: saved.get(k)
            for k in ("gateway", "status", "identity", "intent", "created_at")
        }
        saved.setdefault("route_history", []).append(
            {
                **previous,
                "changed_at": timestamp(),
                "reason": "local_route_enabled_before_quote_or_submission",
            }
        )
        saved.update(
            gateway=False,
            route="direct",
            identity=direct_identity(config, payload.get("model")),
        )
        atomic_private(path, saved)
        return False
