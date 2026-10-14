from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext
from model_config import create_model, before_model, on_model_error
from order_summary_agent.agent import order_summary_agent


def save_shipping_address(tool_context: ToolContext, address: str):
    """Save a nonempty address only after a valid cart and profile exist."""
    required = ("name", "email", "mobile", "item", "quantity", "price", "total")
    if not all(tool_context.state.get(key) for key in required):
        return {"status": "error", "message": "User details and a cart are required before checkout."}
    address = address.strip()
    if len(address) < 10 or len(address) > 1000:
        return {"status": "error", "message": "Provide a complete shipping address (10 to 1000 characters)."}
    tool_context.state["shipping_address"] = address
    return {"status": "saved", "shipping_address": address}


checkout_agent = LlmAgent(
    name="checkout_agent",
    description="Collects and saves shipping details for the current demo cart.",
    model=create_model(), before_model_callback=before_model, on_model_error_callback=on_model_error,
    instruction="""
    You are the checkout specialist. You prepare a demo order summary.
    A transfer_to_agent result of null is normal success; never call it an issue or error.
    If there is no saved cart, transfer back to catalog_agent.
    Collect a complete shipping address and call save_shipping_address.
    Only confirm it was saved if the tool returns status=saved.
    Ask whether the user wants to view the order summary, then transfer to order_summary_agent.
    If they already asked for the summary and supplied the address, save it and transfer immediately.
    Do not process payment or claim an order has been placed.
    Keep responses short and friendly.
    """,
    tools=[save_shipping_address], sub_agents=[order_summary_agent],
)
