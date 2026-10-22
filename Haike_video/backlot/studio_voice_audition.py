"""A fixed, service-funded audition: one click, one durable supplier intent.

Only explicitly local personal voices can create a result here. No customer
balance is debited, and the supplier quote/usage is never rewritten as free.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
import hashlib
import json
import threading

from backlot import studio_personal_voice as personal
from backlot.studio import timestamp
from backlot.studio_avatar import key_identity
from backlot.studio_system_voice import ROUTE, TARGET_MODEL, _now
from backlot.work_catalog import WorkError

POLICY = "service-preview-v1"
MAX_PREVIEW_MICROS = 10_000
DAILY_MAX_MICROS = 500_000
DAILY_MAX_VOICES = 50
_workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="voice-audition")
_guard, _pending = threading.Lock(), {}
_prepare_guard = threading.Lock()


def _reserve(studio, voice_id, quote):
    client = studio.client()
    frozen = client._read(quote["id"])
    amount = int(quote["max_charge_micros"])
    if (quote.get("execution_route") != ROUTE or quote.get("model") != personal.MODEL
            or frozen["target_model"] != TARGET_MODEL
            or frozen["inputs"] != {"voice_id": voice_id, "text": personal.SAMPLE_TEXT}
            or not 0 <= amount <= MAX_PREVIEW_MICROS):
        raise WorkError("试听服务暂时无法准备这个音色，请联系管理员；未发起新的生成")
    day = _now().astimezone(timezone(timedelta(hours=8))).date().isoformat()
    owner = key_identity(studio)
    with studio.db() as db:
        rows = [json.loads(row[0]) for row in db.execute("SELECT data FROM studio_voice_operations").fetchall()]
        matches = [v for v in rows if v["identity"] == owner and v.get("quote", {}).get("id") == quote["id"]]
        item = next((v for v in matches if v.get("intent")), matches[0] if matches else None)
        if item and item.get("funding") == POLICY:
            return item
        funded = {v["quote"]["id"]: int(v["quote"]["max_charge_micros"]) for v in rows
                  if v.get("funding") == POLICY and v.get("funding_day") == day and v.get("intent")}
        if len(funded) >= DAILY_MAX_VOICES or sum(funded.values()) + amount > DAILY_MAX_MICROS:
            raise WorkError("今天的免费试听准备额度已用完，已缓存的试听仍可播放，请稍后再试")
        # Reuse an old unconfirmed checkout or a crash-saved SDK intent.
        item = item or {"id": "voiceop-" + quote["id"].split("-")[1], "identity": owner,
                        "kind": "sample", "name": personal._read(studio, voice_id)["name"],
                        "voice_id": voice_id, "quote": quote, "created_at": timestamp()}
        intent = frozen.get("intent_id") or "call_" + hashlib.sha256(quote["id"].encode()).hexdigest()[:32]
        intent = client.confirm(quote, amount, intent_id=intent)
        state = client._read(intent)
        item.update(intent=intent, funding=POLICY, funding_day=day, customer_charge_micros="0",
                    job={"id": state["id"], "status": state["status"]})
        db.execute("INSERT OR REPLACE INTO studio_voice_operations VALUES(?,?,?)",
                   (item["id"], owner, json.dumps(item, ensure_ascii=False)))
    return item


def _run(studio, operation_id):
    from backlot import studio_voices
    item = studio_voices._get(studio, operation_id)
    try:
        job = studio.client().resume(item["intent"])
        job.pop("result", None)  # Playback streams the private cache, not JSON base64.
        item["job"] = job
        studio_voices._store(studio, item)
    except Exception:
        pass  # Original durable SDK state remains the recovery authority.


def _start(studio, item):
    studio = personal.bind(studio)
    key = (str(personal.root(studio)), item["intent"])
    with _guard:
        if key not in _pending or _pending[key].done():
            _pending[key] = _workers.submit(_run, studio, item["id"])


def refresh(studio, item):
    """Read progress without blocking a library request on a supplier call."""
    from backlot import studio_voices
    state = studio.client()._read(item["intent"])
    job = {k: state[k] for k in ("id", "status", "message", "usage", "estimated_cost_micros") if k in state}
    if state["status"] in {"queued", "accepted", "submitting"}:
        _start(studio, item)
    return studio_voices.public({**item, "job": job})


def prepare(studio, voice_id):
    studio = personal.bind(studio)
    # Single-process quick preparation is serial; SQLite/SDK locks protect the
    # durable quote/intent boundary as well. The network work runs separately.
    with _prepare_guard:
        if not personal.is_local(voice_id):
            from backlot import studio_voices
            voice = next((v for v in studio_voices.catalogue(studio)["items"] if v["id"] == voice_id), None)
            if not voice or voice.get("sample_status") != "succeeded":
                raise WorkError("这个音色的试听暂未准备好，请稍后重试；不会自动发起收费试听")
            return {"status": "succeeded", "customer_charge_micros": "0", "sample_url": voice["sample_url"]}
        data = personal._read(studio, voice_id)
        state = personal.preview_state(studio, data)
        if state["status"] == "succeeded":
            return {"status": "succeeded", "customer_charge_micros": "0",
                    "sample_url": "/api/studio/voices/" + voice_id + "/sample"}
        if not data.get("sample_quote") or state["status"] == "missing":
            quote = personal.preview_quote(studio, voice_id)["quote"]
        else:
            quote = studio.client()._read(data["sample_quote"])["quote"]
        item = _reserve(studio, voice_id, quote)
        current = refresh(studio, item)
        return {"status": current["job"]["status"], "customer_charge_micros": "0"}
