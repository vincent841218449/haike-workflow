"""Local, account-scoped CosyVoice enrollment; no cloud gateway deployment.

The development-only upload lease expires at the provider in 48 hours. A
unique prefix and a persisted submit boundary allow recovery without creating
another voice. TTS uses the exact enrolled model via studio_system_voice.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import requests

from backlot.studio import atomic_private
from backlot.studio_system_voice import configuration, _now, TARGET_MODEL
from backlot.work_catalog import WorkError
from lib.bailian_speech import operation_lock

ROUTE = "local-personal-voice-clone"
MODEL = "haike/cosyvoice"
SAMPLE_TEXT = "你好，我是你的专属声音。愿每一次表达，都自然、清晰、有温度。"
_workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="voice-clone")
_pending, _pending_lock = {}, threading.Lock()


def bind(studio):
    """A running request must keep its platform account if settings change."""
    bound = copy.copy(studio)
    account = studio.configuration()
    bound.configuration = lambda: account
    return bound


def root(studio):
    from backlot.studio_avatar import key_identity
    return studio.private / "personal-voices" / key_identity(studio)


def configuration_status(studio):
    config = configuration(studio)
    return {"ready": config["ready"], "billing_source": "local-provider",
            "target_model": TARGET_MODEL, "storage": "provider-temporary-48h"}


def is_local(voice_id):
    return isinstance(voice_id, str) and re.fullmatch(r"voice_local_[a-f0-9]{32}", voice_id) is not None


def _path(studio, identity):
    if not isinstance(identity, str) or not re.fullmatch(r"(?:voice_local_|samplelocal-|localclone-)[a-f0-9]{32}", identity):
        raise WorkError("个人音色或录音编号无效")
    return root(studio) / (identity + ".json")


def _read(studio, identity):
    path = _path(studio, identity)
    if path.is_symlink():
        raise WorkError("个人音色记录路径不可用")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise WorkError("个人音色记录不存在或不属于当前账户，请恢复原账户后继续") from None


def _write(studio, identity, data):
    atomic_private(_path(studio, identity), data)


def _lock(studio, identity):
    return operation_lock(_path(studio, identity).with_suffix(".lock"))


def upload(studio, normalized, name, duration, preparation=None):
    """Save a private reference locally; consent is required before transmission."""
    raw = normalized.read_bytes()
    identity = "samplelocal-" + hashlib.sha256(raw).hexdigest()[:32]
    with _lock(studio, identity):
        path = _path(studio, identity).with_suffix(".wav")
        if not path.exists():
            path.write_bytes(raw); path.chmod(0o600)
        _write(studio, identity, {**(preparation or {}), "id": identity, "sha256": hashlib.sha256(raw).hexdigest(),
            "name": name, "duration": duration})
    return {**(preparation or {}), "id": identity, "name": name, "duration": duration,
            "reference_url": "/api/studio/voices/references/" + identity}


def reference(studio, sample_id):
    if not isinstance(sample_id, str) or not re.fullmatch(r"samplelocal-[a-f0-9]{32}", sample_id):
        raise WorkError("参考录音编号无效")
    data = _read(studio, sample_id)
    path = _path(studio, sample_id).with_suffix(".wav")
    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != data["sha256"]:
        raise WorkError("参考录音已清理或发生变化，请重新上传")
    return path


def quote(studio, inputs):
    name, language, tags = inputs.get("name"), inputs.get("language", "zh"), inputs.get("tags", [])
    if (inputs.get("consent") is not True or not isinstance(name, str) or not 1 <= len(name.strip()) <= 48
            or any(ord(c) < 32 for c in name) or language not in {"zh", "en", "yue"}
            or not isinstance(tags, list) or len(tags) > 4
            or any(not isinstance(t, str) or not 1 <= len(t.strip()) <= 12 for t in tags)):
        raise WorkError("请填写1至48字音色名称，并确认使用本人或有授权的清晰录音")
    config = configuration(studio)
    if not config["ready"]:
        raise WorkError("本地音色服务尚未接通，请联系管理员")
    if not isinstance(inputs.get("sample_id"), str) or not re.fullmatch(r"samplelocal-[a-f0-9]{32}", inputs["sample_id"]):
        raise WorkError("请先上传自己的参考录音")
    sample = _read(studio, inputs["sample_id"])
    fingerprint = hashlib.sha256(json.dumps([sample["sha256"], config["identity"], TARGET_MODEL]).encode()).hexdigest()[:32]
    identity = "localclone-" + fingerprint
    with _lock(studio, identity):
        if _path(studio, identity).exists():
            prior = _read(studio, identity)
            if prior.get("intent"):
                if prior.get("status") == "failed" and not prior.get("provider_voice_id"):
                    # Only a fresh user action retries a definite rejection.
                    # Polling and uncertain submissions can never take this path.
                    prior["retry_requested"] = True
                    _write(studio, identity, prior)
                elif prior.get("status") == "succeeded":
                    _path(studio, sample["id"]).with_suffix(".wav").unlink(missing_ok=True)
                return prior["quote"]  # The same recording always resumes its original creation.
        value = {"id": identity, "model": "haike/voice-clone", "execution_route": ROUTE,
                 "max_charge_micros": "0", "billing_source": "local-provider", "voice_name": name.strip(),
                 "expires_at": (_now() + timedelta(minutes=10)).isoformat()}
        _write(studio, identity, {"quote": value, "sample_id": sample["id"], "sample_sha256": sample["sha256"],
            "name": name.strip(), "language": language, "tags": [t.strip() for t in tags],
            "consent": True, "target_model": TARGET_MODEL, "credential_identity": config["identity"],
            "prefix": "h" + base64.b32encode(bytes.fromhex(fingerprint)).decode().lower()[:8]})
        return value


def confirm(studio, value):
    with _lock(studio, value["id"]):
        data = _read(studio, value["id"])
        if data["quote"] != value or value["max_charge_micros"] != "0":
            raise WorkError("克隆报价已变化，请重新检查；未提交调用")
        if not data.get("intent"):
            if _now().isoformat() >= value["expires_at"]:
                raise WorkError("录音确认已过期，请返回后重新开始克隆")
            data.update(intent=value["id"], status="queued", created_at=_now().isoformat())
            _write(studio, value["id"], data)
        elif data.pop("retry_requested", False) and data.get("status") == "failed" and not data.get("provider_voice_id"):
            data.setdefault("rejections", []).append({"at": _now().isoformat(), "message": data.get("message", "")})
            data.update(status="queued", message="")
            _write(studio, value["id"], data)
    return value["id"]


def start(studio, identity):
    bound = bind(studio)
    key = (str(root(bound)), identity)
    with _pending_lock:
        if key not in _pending or _pending[key].done():
            _pending[key] = _workers.submit(resume, bound, identity)
    return _public(_read(bound, identity))


def _enrollment(config, inputs, reference=False):
    headers = {"Authorization": "Bearer " + config["api_key"], "Content-Type": "application/json"}
    if reference:
        headers["X-DashScope-OssResourceResolve"] = "enable"
    with requests.Session() as session:
        session.trust_env = False
        response = session.post(config["endpoint"].rsplit("/", 1)[0] + "/customization", headers=headers,
            json={"model": "voice-enrollment", "input": inputs}, timeout=(15, 120), allow_redirects=False)
    return response


def _upload_reference(studio, data, config):
    path = _path(studio, data["sample_id"]).with_suffix(".wav")
    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != data["sample_sha256"]:
        raise WorkError("原录音已变化或丢失，请重新上传原录音；不会提交克隆")
    # Never send the API key to storage, persist a policy, or use an arbitrary host.
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(config["endpoint"].split("/services/")[0] + "/uploads",
            headers={"Authorization": "Bearer " + config["api_key"]},
            params={"action": "getPolicy", "model": "voice-enrollment"}, timeout=(15, 45), allow_redirects=False)
        if response.status_code != 200:
            raise WorkError("录音上传授权未完成，请稍后查询原任务")
        policy = response.json()["data"]
        host, directory = policy.get("upload_host", ""), policy.get("upload_dir", "")
        if (not re.fullmatch(r"https://[a-z0-9-]+\.oss-[a-z0-9-]+\.aliyuncs\.com/?", host)
                or not re.fullmatch(r"[a-zA-Z0-9_/-]{1,500}", directory) or ".." in directory
                or policy.get("x_oss_object_acl") != "private"):
            raise WorkError("录音服务未返回有效的私有上传地址")
        key = directory.rstrip("/") + "/" + data["prefix"] + ".wav"
        fields = {"OSSAccessKeyId": policy["oss_access_key_id"], "Signature": policy["signature"],
                  "policy": policy["policy"], "key": key, "success_action_status": "200",
                  "x-oss-object-acl": "private", "x-oss-forbid-overwrite": "true"}
        with path.open("rb") as audio:
            result = session.post(host, data=fields, files={"file": ("reference.wav", audio, "audio/wav")},
                timeout=(15, 90), allow_redirects=False)
        if result.status_code not in {200, 201, 204}:
            raise WorkError("录音传输未完成，请稍后查询原任务")
    return "oss://" + key


def _valid_provider(data, identity):
    return (isinstance(identity, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", identity)
            and identity.startswith(data["target_model"] + "-" + data["prefix"] + "-"))


def _rejection_message(response):
    return {401: "克隆服务凭据无效，请联系管理员修复后再开始克隆",
            403: "克隆服务权限或额度不足，请联系管理员处理后再开始克隆",
            429: "克隆服务繁忙，本次未受理，请稍后重新点击开始克隆"}.get(
                response.status_code, "克隆服务拒绝了录音，请检查5秒以上清晰人声、录音质量及服务权限")


def resume(studio, identity):
    studio = bind(studio)
    with _lock(studio, identity):
        data = _read(studio, identity)
        config = configuration(studio)
        if data["credential_identity"] != config["identity"] or not config["api_key"]:
            raise WorkError("克隆服务凭据已改变，请恢复原凭据后查询原音色")
        if data["status"] == "submitting":
            data.update(status="submission_unknown", message="正在核对原克隆结果，不会重新创建")
            _write(studio, identity, data)
        if data["status"] == "queued":
            try:
                reference = _upload_reference(studio, data, config)
            except Exception:
                data["message"] = "录音上传未完成，已保留录音，正在等待恢复传输"
                _write(studio, identity, data)
                return _public(data)
            data.update(status="submitting")
            _write(studio, identity, data)  # Must precede the non-idempotent request.
            try:
                response = _enrollment(config, {"action": "create_voice", "target_model": data["target_model"],
                    "prefix": data["prefix"], "url": reference,
                    "language_hints": ["en" if data["language"] == "en" else "zh"]}, reference=True)
                if response.status_code in {400, 401, 403, 404, 413, 422, 429}:
                    data.update(status="failed", message=_rejection_message(response))
                else:
                    receipt = response.json()
                    voice = receipt.get("output", {}).get("voice_id")
                    if response.status_code != 200 or not _valid_provider(data, voice):
                        raise ValueError("uncertain receipt")
                    data.update(provider_voice_id=voice, request_id=str(receipt.get("request_id", "")), status="running")
            except Exception:
                data.update(status="submission_unknown", message="正在核对原克隆结果，不会重新创建")
            _write(studio, identity, data)
        if data["status"] == "submission_unknown":
            try:
                result = _enrollment(config, {"action": "list_voice", "prefix": data["prefix"], "page_index": 0, "page_size": 10})
                found = result.json().get("output", {}).get("voice_list", [])
                if result.status_code == 200 and len(found) == 1 and _valid_provider(data, found[0].get("voice_id")):
                    data.update(provider_voice_id=found[0]["voice_id"], status="running")
                    _write(studio, identity, data)
            except Exception:
                pass
        if data["status"] == "running":
            try:
                response = _enrollment(config, {"action": "query_voice", "voice_id": data["provider_voice_id"]})
                output = response.json().get("output", {})
                if response.status_code != 200 or output.get("target_model", data["target_model"]) != data["target_model"]:
                    raise ValueError("query incomplete")
                status = str(output.get("status", "")).upper()
                if status == "OK":
                    voice_id = "voice_local_" + identity.split("-")[1]
                    if not _path(studio, voice_id).exists():
                        _write(studio, voice_id, {k: data[k] for k in ("name", "language", "tags", "target_model", "provider_voice_id", "credential_identity", "created_at")})
                    data.update(status="succeeded", voice_id=voice_id)
                    data.pop("message", None)
                    _path(studio, data["sample_id"]).with_suffix(".wav").unlink(missing_ok=True)
                elif status in {"FAILED", "UNDEPLOYED"}:
                    data.update(status="failed", message="音色未通过服务检查，请更换清晰单人录音")
                else:
                    data["message"] = "正在分析声音，完成后自动加入个人音色库"
            except Exception:
                data["message"] = "原音色已受理，正在恢复状态查询，不会重新克隆"
            _write(studio, identity, data)
        return _public(data)


def _public(data):
    return {"id": data["quote"]["id"], "status": data["status"], "model": "haike/voice-clone",
            "message": data.get("message", ""), "max_charge_micros": "0",
            "retryable": data["status"] == "submission_unknown", "billing_source": "local-provider",
            **({"result": {"voice_id": data["voice_id"]}} if data.get("voice_id") else {})}


def resolve(studio, voice_id):
    if not is_local(voice_id):
        raise WorkError("请选择个人库中的音色")
    data = _read(studio, voice_id)
    if data["credential_identity"] != configuration(studio)["identity"] or data["target_model"] != TARGET_MODEL:
        raise WorkError("此音色所属本机服务配置已变化，请恢复原配置")
    return data


def catalogue(studio):
    result = []
    config = configuration(studio)
    for path in sorted(root(studio).glob("voice_local_*.json"), reverse=True):
        voice_id = path.stem
        data = _read(studio, voice_id)
        ready = config["ready"] and config["identity"] == data["credential_identity"] and data["target_model"] == TARGET_MODEL
        state = preview_state(studio, data)
        result.append({"id": voice_id, "name": data["name"], "scope": "personal", "model": MODEL,
            "language": data["language"], "tags": data["tags"], "status": "ready" if ready else "unavailable",
            "production_ready": ready, "production_hint": "本地专属音色，配音费用计入视频上限。",
            "sample_status": state["status"], "sample_url": "/api/studio/voices/" + voice_id + "/sample" if state["status"] == "succeeded" else None,
            "created_at": data["created_at"]})
    return result


def preview_state(studio, data):
    if not data.get("sample_quote"):
        return {"status": "missing"}
    client = studio.client()
    record = client._read(data["sample_quote"])
    return client._read(record["intent_id"]) if record.get("intent_id") else {"status": "missing"}


def preview_quote(studio, voice_id):
    with _lock(studio, voice_id):
        data = _read(studio, voice_id)
        state = preview_state(studio, data)
        if state["status"] == "succeeded":
            return {"cached": True}
        resolve(studio, voice_id)
        if data.get("sample_quote"):
            record = studio.client()._read(data["sample_quote"])
            if record.get("intent_id"):
                return {"cached": False, "status": state["status"]}
            if _now().isoformat() < record["quote"]["expires_at"]:
                return {"quote": record["quote"]}
        quote = studio.client().quote(MODEL, {"text": SAMPLE_TEXT, "voice_id": voice_id}, "voice-preview")
        data["sample_quote"] = quote["id"]
        _write(studio, voice_id, data)
        return {"quote": quote}


def sample(studio, voice_id):
    data = _read(studio, voice_id)
    state = preview_state(studio, data)
    if state["status"] != "succeeded":
        raise WorkError("此音色尚无合成试听，请先生成试听")
    client = studio.client()
    record = client._read(data["sample_quote"])
    return client.cached_audio(record["intent_id"])


def rename(studio, voice_id, name):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 48 or any(ord(c) < 32 for c in name):
        raise WorkError("音色名称需要1至48字")
    with _lock(studio, voice_id):
        data = resolve(studio, voice_id)
        data["name"] = name.strip()
        _write(studio, voice_id, data)
    return {"id": voice_id, "name": data["name"]}
