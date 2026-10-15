"""Opt-in local system-voice production; remote account and ledger stay remote.

Only the seven curated presets use this route. Quotes freeze voice, model,
credential identity and estimated supplier cost. A durable intent is saved
before HTTP submission; an interrupted submission can never submit again.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import requests

from backlot.studio import atomic_private
from backlot.work_catalog import WorkError

MODEL = "haike/cosyvoice-system"
TARGET_MODEL = "cosyvoice-v3-flash"
ROUTE = "local-system-voice"
COST_PER_10000_MICROS = 1_000_000


def configuration(studio):
    from backlot.ai_text import _read_env_file, _effective_value
    path = studio.private / "haike-api/system-voices.local.json"
    try:
        enabled = json.loads(path.read_text(encoding="utf-8")).get("enabled") is True
    except FileNotFoundError:
        enabled = False
    except (ValueError, OSError):
        raise WorkError("本地音色配置无法读取，请恢复原配置后重试") from None
    _, values = _read_env_file(studio.projects_root.parent / ".env.secrets.local")
    key = _effective_value("DASHSCOPE_API_KEY", values)
    workspace = _effective_value("DASHSCOPE_WORKSPACE_ID", values)
    if workspace and not re.fullmatch(r"[A-Za-z0-9-]{1,80}", workspace):
        raise WorkError("本地配音业务空间配置无效，请联系管理员")
    host = f"{workspace}.cn-beijing.maas.aliyuncs.com" if workspace else "dashscope.aliyuncs.com"
    endpoint = f"https://{host}/api/v1/services/audio/tts/SpeechSynthesizer"
    return {"enabled": enabled, "ready": enabled and bool(key), "api_key": key,
            "endpoint": endpoint, "identity": hashlib.sha256(json.dumps([endpoint, key]).encode()).hexdigest()}


def status(studio):
    config = configuration(studio)
    return {"enabled": config["enabled"], "ready": config["ready"], "model": MODEL,
            "target_model": TARGET_MODEL, "billing_source": "local-provider"}


def _now():
    return datetime.now(timezone.utc)


class SystemVoiceClient:
    """Decorate the existing SDK only at its quote/intent boundary."""
    def __init__(self, studio, remote):
        from backlot.studio_avatar import key_identity
        self.studio, self.remote = studio, remote
        self.root = studio.private / "system-voices" / key_identity(studio)

    def __getattr__(self, name):
        return getattr(self.remote, name)

    def request(self, path, body=None, **kwargs):
        if path.startswith("/quotes/localvoice-") and path.endswith("/renew"):
            if body != {"confirmed": True}:
                raise WorkError("请确认原配音报价续期")
            identity = path.split("/")[2]
            with self._lock(identity):
                data = self._read(identity)
                if data.get("intent_id"):
                    return data["quote"]  # Accepted work keeps its original frozen quote.
                if _now() - datetime.fromisoformat(data["created_at"]) > timedelta(hours=24):
                    raise WorkError("原配音报价已超过24小时，请重新确认费用")
                data["quote"]["expires_at"] = (_now() + timedelta(minutes=10)).isoformat()
                self._write(identity, data)
                return data["quote"]
        value = self.remote.request(path, body, **kwargs)
        if path == "/capabilities" and status(self.studio)["ready"]:
            # Explicit local opt-in takes precedence for this model only.
            items = [v for v in value.get("items", []) if (v.get("model") or v.get("id")) != MODEL]
            value = {**value, "items": items + [{"id": MODEL, "model": MODEL,
                "name": "系统音色配音", "capability": "tts", "status": "available",
                "billing_source": "local-provider"}]}
        return value

    def _path(self, identity):
        if not re.fullmatch(r"(?:localvoice-[a-f0-9]{32}|call_[a-f0-9]{32})", str(identity)):
            raise WorkError("配音任务编号无效")
        return self.root / (identity + ".json")

    def _read(self, identity):
        try:
            return json.loads(self._path(identity).read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            raise WorkError("原配音记录不存在或已损坏，请恢复原账户和记录；不会重新提交") from None

    def _write(self, identity, data):
        atomic_private(self._path(identity), data)

    def _lock(self, identity):
        from lib.bailian_speech import operation_lock
        return operation_lock(self._path(identity).with_suffix(".lock"))

    def quote(self, model, inputs, project_ref=""):
        if model != MODEL or not status(self.studio)["enabled"]:
            return self.remote.quote(model, inputs, project_ref)
        from backlot.studio_voices import _system_catalogue
        from platform_app.providers import bailian_tts_characters
        config = configuration(self.studio)
        if not config["ready"]:
            raise WorkError("本地配音尚未配置服务凭据，已选音色保留")
        voice = next((v for v in _system_catalogue().presets() if v["id"] == inputs.get("voice_id")), None)
        text = inputs.get("text")
        if not voice or not isinstance(text, str) or not text.strip() or len(text) > 5000 or set(inputs) != {"text", "voice_id"}:
            raise WorkError("请选择有效系统音色并填写1至5,000字文案")
        identity = "localvoice-" + uuid4().hex
        characters = bailian_tts_characters(text)
        maximum = (characters * COST_PER_10000_MICROS + 9999) // 10000
        quote = {"id": identity, "model": MODEL, "execution_route": ROUTE,
                 "billing_source": "local-provider", "max_charge_micros": str(maximum),
                 "quoted_usage": {"characters": characters},
                 "price": {"currency": "CNY", "cost_per_10000_micros": str(COST_PER_10000_MICROS),
                           "basis": "供应商标价估算，实际账单待核对"},
                 "expires_at": (_now() + timedelta(minutes=10)).isoformat()}
        self._write(identity, {"quote": quote, "inputs": inputs, "voice": voice["voice"],
            "target_model": TARGET_MODEL, "credential_identity": config["identity"],
            "created_at": _now().isoformat(), "project_ref": project_ref})
        return quote

    def confirm(self, quote, maximum, intent_id=None):
        if not str(quote.get("id", "")).startswith("localvoice-"):
            return self.remote.confirm(quote, maximum, intent_id)
        intent_id = intent_id or "call_" + uuid4().hex
        with self._lock(intent_id), self._lock(quote["id"]):
            data = self._read(quote["id"])
            if quote != data["quote"] or int(maximum) < int(quote["max_charge_micros"]):
                raise WorkError("配音报价已变化或超过费用上限，未提交调用")
            if data.get("intent_id") and data["intent_id"] != intent_id:
                raise WorkError("此配音报价已有原任务，请恢复原任务")
            path = self._path(intent_id)
            if path.exists():
                if self._read(intent_id)["quote_id"] != quote["id"]:
                    raise WorkError("同一配音意图不能更换报价")
                return intent_id
            if (self.remote.state_dir / (intent_id + ".json")).exists():
                raise WorkError("调用意图已用于原网关任务，请恢复原任务")
            if datetime.fromisoformat(quote["expires_at"]) <= _now():
                raise WorkError("本地配音报价已过期，请先续期原报价")
            # Reserve the quote before creating its intent, including crash recovery.
            data["intent_id"] = intent_id
            self._write(quote["id"], data)
            self._write(intent_id, {"id": "localtts-" + intent_id[5:], "quote_id": quote["id"],
                                    "status": "queued", "created_at": _now().isoformat()})
        return intent_id

    def resume(self, intent_id):
        if not self._path(intent_id).exists():
            return self.remote.resume(intent_id)
        with self._lock(intent_id):
            job = self._read(intent_id)
            data = self._read(job["quote_id"])
            if job["status"] == "submitting":
                job.update(status="submission_unknown", message="原配音提交结果不明，请核对供应商记录；不会重复提交")
                self._write(intent_id, job)
            if job["status"] == "queued":
                config = configuration(self.studio)
                if not config["api_key"] or data["credential_identity"] != config["identity"]:
                    raise WorkError("本地配音凭据已改变，请恢复原凭据后继续同一任务")
                job["status"] = "submitting"
                self._write(intent_id, job)
                try:
                    with requests.Session() as session:
                        session.trust_env = False
                        response = session.post(config["endpoint"], headers={"Authorization": "Bearer " + config["api_key"]},
                            json={"model": data["target_model"], "input": {"text": data["inputs"]["text"],
                                  "voice": data["voice"], "format": "wav", "sample_rate": 24000}},
                            timeout=(15, 180), allow_redirects=False)
                    if response.status_code in {400, 401, 403, 404, 422, 429}:
                        job.update(status="failed", message="配音服务拒绝请求，请核对本机模型权限、额度或音色配置")
                    elif response.status_code != 200:
                        raise ValueError("uncertain response")
                    else:
                        receipt = response.json()
                        audio = (receipt.get("output") or {}).get("audio", {}).get("url")
                        characters = (receipt.get("usage") or {}).get("characters")
                        if not isinstance(audio, str) or not audio:
                            raise ValueError("missing audio")
                        job.update(audio_url=audio, upstream_id=str(receipt.get("request_id") or ""))
                        if type(characters) is not int or characters < 0:
                            raise ValueError("missing usage")
                        job.update(status="accepted", usage={"characters": characters},
                            estimated_cost_micros=str((characters * COST_PER_10000_MICROS + 9999) // 10000))
                except Exception:
                    job.update(status="submission_unknown", message="原配音提交或用量结果不明，请核对原调用；不会重复提交")
                self._write(intent_id, job)
            if job["status"] == "accepted":
                from backlot.studio_avatar import download_result
                target = self.root / (job["id"] + ".wav")
                try:
                    if not target.exists():
                        download_result(job["audio_url"], target)
                    with wave.open(str(target), "rb") as audio:
                        if audio.getnframes() <= 0 or target.stat().st_size > 25 * 1024 * 1024:
                            raise ValueError("invalid audio")
                    job.update(status="succeeded", audio_path=str(target))
                    job.pop("message", None)
                    self._write(intent_id, job)
                except Exception:
                    target.unlink(missing_ok=True)
                    job["message"] = "配音已生成，下载或音频校验未完成；恢复原任务会复用结果"
                    self._write(intent_id, job)
            value = {k: job[k] for k in ("id", "status", "usage", "estimated_cost_micros", "message") if k in job}
            value.update(model=MODEL, billing_source="local-provider", settlement_status="supplier_bill_pending")
            if job["status"] == "succeeded":
                value["result"] = {"audio_base64": base64.b64encode(Path(job["audio_path"]).read_bytes()).decode()}
            return value

    def wait(self, intent_id, timeout=300):
        if self._path(intent_id).exists():
            return self.resume(intent_id)
        return self.remote.wait(intent_id, timeout=timeout)
