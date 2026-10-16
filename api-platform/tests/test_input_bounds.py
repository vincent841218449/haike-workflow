import pytest
from test_platform import RULE, key

from platform_app import gateway
from platform_app.store import canonical


@pytest.mark.parametrize("length", [60001, 100001, 1000001])
def test_chat_input_preserves_text_without_a_byte_ceiling(length):
    messages = [{"role": "user", "content": "文" * length}]
    inputs = {"messages": messages, "max_output_tokens": 6500}

    cleaned, usage = gateway.clean_input(None, "test-user", "haike/text", inputs)

    assert cleaned == inputs
    assert usage == {
        "input_tokens": len(canonical(messages).encode()) * 2 + 1024,
        "output_tokens": 6500,
    }


def test_nested_input_and_quantity_are_validated(env):
    _, admin, customer, _, _, _, _ = env
    headers, _ = key(customer)
    response = customer.post(
        "/v2/quotes",
        headers=headers,
        json={
            "model": "demo/cosyvoice-characters",
            "input": {"text": "海", "demo_outcome": []},
        },
    )
    assert response.status_code == 422
    response = customer.post(
        "/v2/quotes",
        headers=headers,
        json={
            "model": "demo/cosyvoice-characters",
            "input": {"text": "海" + " " * 20000, "demo_outcome": "succeeded"},
        },
    )
    assert response.status_code == 422
    response = admin.post(
        "/admin/v1/price-versions/preview",
        json={
            "model": "demo/avatar-role",
            "quantity": 1200,
            "rule": RULE,
        },
    )
    assert response.status_code == 422
