from types import SimpleNamespace

import pytest
from google.adk.sessions.state import State

from ecommerce_agent.agent import root_agent, save_user_info
from catalog_agent.agent import save_cart
from checkout_agent.agent import save_shipping_address
from order_summary_agent.agent import summary_instruction


def context(data=None):
    return SimpleNamespace(state=State(data or {}, {}))


def profile():
    ctx = context()
    assert save_user_info(ctx, "Demo Shopper", "demo@example.com", "+919876543210")["status"] == "saved"
    return ctx


def test_all_agents_use_openai():
    agent = root_agent
    names = []
    while agent:
        assert agent.model.model == "openai/gpt-4o-mini"
        assert agent.before_model_callback is not None
        names.append(agent.name)
        agent = agent.sub_agents[0] if agent.sub_agents else None
    assert names == ["ecommerce_agent", "catalog_agent", "checkout_agent", "order_summary_agent"]


def test_complete_state_and_total():
    ctx = profile()
    assert save_cart(ctx, "Smartphones", "Pixel 9", "2", 70000)["status"] == "saved"
    assert ctx.state["total"] == 140000
    assert save_shipping_address(ctx, "123 Demo Road, Mumbai, 400001")["status"] == "saved"
    prompt = summary_instruction(ctx)
    assert '"total": 140000' in prompt
    assert '"quantity": "2"' in prompt
    assert "no payment or actual order has been placed" in prompt


@pytest.mark.parametrize("quantity", ["0", "-1", "1.5", "no", "100"])
def test_invalid_quantity_does_not_mutate(quantity):
    ctx = profile()
    assert save_cart(ctx, "Smartphones", "Pixel 9", quantity, 70000)["status"] == "error"
    assert ctx.state.get("item") is None


@pytest.mark.parametrize("category,item,price", [("Smartphones", "Unknown", 70000), ("Laptops", "Pixel 9", 70000), ("Smartphones", "Pixel 9", 1)])
def test_invalid_catalog_data(category, item, price):
    ctx = profile()
    assert save_cart(ctx, category, item, "1", price)["status"] == "error"
    assert ctx.state.get("total") is None


@pytest.mark.parametrize("email,mobile", [("bad", "1234567890"), ("demo@example.com", "abc1234567890"), ("demo@example.com", "123")])
def test_profile_validation(email, mobile):
    ctx = context()
    assert save_user_info(ctx, "Demo", email, mobile)["status"] == "error"
    assert ctx.state.get("name") is None


def test_checkout_requires_profile_and_cart():
    assert save_cart(context(), "Smartphones", "Pixel 9", "1", 70000)["status"] == "error"
    assert save_shipping_address(profile(), "123 Demo Road, Mumbai")["status"] == "error"


def test_summary_handles_missing_state():
    assert "missing fields" in summary_instruction(context())
