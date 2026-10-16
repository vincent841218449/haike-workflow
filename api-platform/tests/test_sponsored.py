from concurrent.futures import ThreadPoolExecutor

import pytest
from test_commerce import enable, real_quote
from test_platform import key, submit

from platform_app import adapters, domain, gateway, providers, sponsored
from platform_app.store import Problem

RULE = {"costs": {"input_tokens": "0", "output_tokens": "0"}, "multiplier": "1.5",
        "fee_micros": "0", "source": "平台承担试用调用费用", "cost_basis": "采购价待核对",
        "confirmed": True, "billing_policy": "sponsored"}


def setup(env):
    store, _, customer, _, admin, _, _ = env
    vault = enable(store, "openai")
    providers.publish(store, admin["id"], "haike/text", RULE, vault)
    headers, _ = key(customer)
    return vault, headers


def test_sponsored_receipt_has_tokens_zero_charge_and_unknown_procurement(env):
    store, _, customer, _, _, user, _ = env
    _, headers = setup(env)
    q = real_quote(customer, headers, "haike/text", {"messages": [{"role": "user", "content": "测试"}]})
    assert q["max_charge_micros"] == "0" and q["price"]["billing_policy"] == "sponsored"
    j = submit(customer, headers, q).json()
    class Recorded:
        def execute(self, *args):
            return {"usage": {"input_tokens": 232, "output_tokens": 81}, "result": {"choices": [{}]}}
    gateway.execute_one(store, Recorded())
    bill = gateway.get_job(store, user, j["id"], admin=True)
    assert bill["charged_micros"] == "0" and bill["cost_status"] == "unknown"
    assert bill["estimated_cost_micros"] is None and bill["estimated_profit_micros"] is None
    assert bill["billing"]["lines"][0]["quantity"] == 232
    assert bill["billing"]["lines"][0]["unit_cost_micros"] is None
    assert domain.verify_ledger(store)["ok"]


@pytest.mark.parametrize("structured", [False, True])
def test_large_template_request_reaches_provider_intact_once(env, monkeypatch, structured):
    store, _, customer, _, _, user, _ = env
    vault, headers = setup(env)
    text = "完整模板动作说明、原文与语义依据。" * 4000
    content = [{"type": "text", "text": text}] if structured else text
    messages = [{"role": "system", "content": "按所选模板编排，不截断原文。"},
                {"role": "user", "content": content}]
    calls = []

    def fake_http(url, request_headers, body):
        calls.append(body)
        assert body["messages"] == messages
        return {"usage": {"prompt_tokens": 23000, "completion_tokens": 12},
                "choices": [{"message": {"content": "完整编排结果"}, "finish_reason": "stop"}]}

    monkeypatch.setattr(adapters, "http", fake_http)
    response = customer.post("/v2/quotes", headers=headers, json={
        "model": "haike/text", "input": {"messages": messages, "max_output_tokens": 6500}})
    assert len(response.request.content) > 100000
    assert response.status_code == 200, response.text
    quote = response.json()
    job = submit(customer, headers, quote).json()
    assert submit(customer, headers, quote).json()["id"] == job["id"]
    assert gateway.execute_one(store, adapters.Adapter(vault, store.path.parent / "files"))
    assert len(calls) == 1
    result = gateway.get_job(store, user, job["id"])
    assert result["status"] == "succeeded"
    assert result["charged_micros"] == "0"
    assert result["result"]["choices"][0]["message"]["content"] == "完整编排结果"
    assert domain.verify_ledger(store)["ok"]


def test_trial_quota_is_atomic_across_keys_and_idempotent_replays(env, monkeypatch):
    store, _, customer, _, _, user, _ = env
    vault, headers = setup(env)
    monkeypatch.setattr(sponsored, "USER_DAILY", 2)
    monkeypatch.setattr(sponsored, "GLOBAL_DAILY", 3)
    second_headers, second_result = key(customer)
    second_key = second_result["key"]
    with store.read() as db:
        first_key = dict(db.execute("SELECT * FROM api_keys WHERE id!=? AND user_id=?", (second_key["id"], user["id"])).fetchone())
    users = [{**user, "key_id": first_key["id"]}, {**user, "key_id": second_key["id"]}]
    quotes = [real_quote(customer, headers if i % 2 == 0 else second_headers, "haike/text",
                        {"messages": [{"role": "user", "content": "测试"}]}) for i in range(5)]
    def accept(i):
        try: return gateway.accept(store, vault, users[i % 2], quotes[i]["id"], 0, f"trial-intent-{i:02d}", f"trial-idem-{i:02d}")
        except Problem as e: return e
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(accept, range(5)))
    assert sum(isinstance(r, dict) for r in results) == 2
    assert all(r.status == 429 for r in results if isinstance(r, Problem))
    accepted = next(i for i, r in enumerate(results) if isinstance(r, dict))
    assert accept(accepted)["id"] == results[accepted]["id"]
    with store.read() as db:
        assert db.execute("SELECT count(*) FROM gateway_trial_calls").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM gateway_jobs").fetchone()[0] == 2
    # Failed/cancelled jobs still consume trial attempts, never refill a vendor-spending quota.
    gateway.cancel(store, user, results[accepted]["id"])
    assert isinstance(accept(next(i for i, r in enumerate(results) if isinstance(r, Problem))), Problem)
    assert domain.verify_ledger(store)["ok"]


def test_platform_quota_includes_other_users(env, monkeypatch):
    _store, _, customer, outsider, _, _, _ = env
    _, headers = setup(env)
    monkeypatch.setattr(sponsored, "GLOBAL_DAILY", 1)
    q = real_quote(customer, headers, "haike/text", {"messages": [{"role": "user", "content": "测试"}]})
    submit(customer, headers, q)
    other_headers, _ = key(outsider)
    other_q = real_quote(outsider, other_headers, "haike/text", {"messages": [{"role": "user", "content": "测试"}]})
    assert submit(outsider, other_headers, other_q).status_code == 429


def test_sponsored_rule_cannot_fake_procurement_or_apply_to_other_capabilities():
    with pytest.raises(Problem): providers.normalize("haike/text", {k: v for k, v in RULE.items() if k != "billing_policy"})
    with pytest.raises(Problem): providers.normalize("haike/text", {**{k: v for k, v in RULE.items() if k != "billing_policy"}, "costs": {"input_tokens": "00", "output_tokens": "00"}})
    with pytest.raises(Problem): providers.normalize("haike/text", {**RULE, "costs": {"input_tokens": "1", "output_tokens": "0"}})
    with pytest.raises(Problem): providers.normalize("haike/illustration", RULE)
    with pytest.raises(Problem): providers.calculate("haike/text", RULE, {"input_tokens": -1, "output_tokens": 2})


def test_vision_supports_twelve_owned_representative_frames_with_byte_cap(env):
    store, _, _, _, _, user, other = env
    file = gateway.upload(store, user["id"], "image", b"\x89PNG\r\n\x1a\n")
    inputs = {"messages": [{"role": "user", "content": [{"type": "image_file", "file_id": file["id"]}] * 12}]}
    with store.read() as db:
        gateway.clean_input(db, user["id"], "haike/text", inputs)
        with pytest.raises(Problem): gateway.clean_input(db, other["id"], "haike/text", inputs)
    with store.write() as db: db.execute("UPDATE gateway_files SET size=? WHERE id=?", (600000, file["id"]))
    with store.read() as db, pytest.raises(Problem):
        gateway.clean_input(db, user["id"], "haike/text", inputs)
