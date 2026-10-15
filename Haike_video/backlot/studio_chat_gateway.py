"""Durable, platform-funded GPT calls through the customer's one Haike Key."""
import base64
import hashlib
import json
from uuid import uuid4

from backlot.studio import atomic_private, timestamp
from backlot.work_catalog import WorkError


def identity(studio):
    config = studio.configuration()
    return hashlib.sha256(json.dumps([config.get("base_url"), config.get("api_key")]).encode()).hexdigest()


def call(relay, path, stage, payload, lock):
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    with lock:
        receipt = json.loads(path.read_text()) if path.exists() else None
        if receipt:
            if receipt["fingerprint"] != fingerprint:
                raise WorkError("原AI任务内容已冻结，不能在恢复时替换参数")
            if receipt["status"] == "succeeded":
                return receipt["result"]
            if not receipt.get("gateway"):
                raise WorkError("AI原请求结果待核对，未重复提交。请由管理员核对中转记录", "unavailable")
            if receipt["identity"] != identity(relay.studio):
                raise WorkError("原AI意图绑定的账户或网关已变化，请恢复原海客Key后查询")
        else:
            if len(relay.request_paths()) >= relay.request_limit():
                raise WorkError("本次AI调用已达次数上限，已完成素材保留")
            receipt = {"stage": stage, "model": "gpt-6-luna", "fingerprint": fingerprint,
                       "status": "prepared", "image": False, "gateway": True,
                       "identity": identity(relay.studio), "images": {},
                       "intent": "call_" + uuid4().hex, "created_at": timestamp(),
                       "customer_charge_micros": "0", "procurement_amount": None}
            atomic_private(path, receipt)
        sdk = relay.studio.client()
        if "quote" not in receipt:
            messages = []
            for message in payload["messages"]:
                content = message["content"]
                if isinstance(content, list):
                    parts = []
                    for part in content:
                        if part.get("type") == "text":
                            parts.append(part)
                            continue
                        url = part.get("image_url", {}).get("url", "")
                        if not url.startswith("data:image/jpeg;base64,"):
                            raise WorkError("视觉分析仅上传项目生成的JPEG代表帧")
                        image_hash = hashlib.sha256(url.encode()).hexdigest()
                        if image_hash not in receipt["images"]:
                            local = relay.folder / (image_hash + ".jpg")
                            local.write_bytes(base64.b64decode(url.split(",", 1)[1], validate=True))
                            local.chmod(0o600)
                            receipt["images"][image_hash] = sdk.upload(local, "image")["id"]
                            atomic_private(path, receipt)
                        parts.append({"type": "image_file", "file_id": receipt["images"][image_hash]})
                    content = parts
                messages.append({"role": message["role"], "content": content})
            receipt["quote"] = sdk.quote("haike/text", {"messages": messages,
                "max_output_tokens": payload.get("max_completion_tokens", 4096)}, "AI分镜 · " + stage[:80])
            atomic_private(path, receipt)
        if int(receipt["quote"]["max_charge_micros"]) != 0:
            raise WorkError("AI试用已改为收费，请先确认新的预算；尚未提交生成")
        sdk.confirm(receipt["quote"], "0", receipt["intent"])
        receipt["status"] = "submitting"
        atomic_private(path, receipt)  # Stable intent saved before network submission.
    try:
        job = sdk.wait(receipt["intent"])
    except Exception:
        raise WorkError("AI调用结果待查询，原海客意图已保留，可恢复原任务；未创建新意图", "unavailable") from None
    receipt.update(gateway_job_id=job["id"], gateway_status=job["status"])
    if job["status"] != "succeeded":
        receipt["status"] = job["status"]
        atomic_private(path, receipt)
        raise WorkError("AI原任务尚未成功，已保留调用意图，请查询账单后恢复", "unavailable")
    if job["charged_micros"] != "0" or not job.get("result", {}).get("choices"):
        atomic_private(path, receipt)
        raise WorkError("AI试用回执不符合约定，请联系管理员核对原任务")
    usage = job.get("usage", {})
    result = {"id": job["id"], "choices": job["result"]["choices"],
              "usage": {"prompt_tokens": usage.get("input_tokens"), "completion_tokens": usage.get("output_tokens")}}
    receipt.update(status="succeeded", result=result, completed_at=timestamp())
    atomic_private(path, receipt)
    return result
