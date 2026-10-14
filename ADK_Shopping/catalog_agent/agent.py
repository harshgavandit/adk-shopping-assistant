from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext
from catalog import PRODUCTS, catalog_text
from checkout_agent.agent import checkout_agent
from model_config import create_model, before_model, on_model_error


def save_cart(tool_context: ToolContext, category: str, item: str, quantity: str, price: int):
    """Save one demo catalog item. Price is checked against the fixed catalog."""
    selected = next((name for name in PRODUCTS if name.casefold() == item.strip().casefold()), None)
    if selected is None:
        return {"status": "error", "message": "Choose an item from the demo catalog."}
    expected_category, unit_price = PRODUCTS[selected]
    if category.strip().casefold() != expected_category.casefold() or price != unit_price:
        return {"status": "error", "message": f"Use {expected_category} and unit price INR {unit_price} for {selected}."}
    try:
        count = int(quantity)
    except (ValueError, TypeError):
        return {"status": "error", "message": "Quantity must be a whole number from 1 to 99."}
    if not 1 <= count <= 99:
        return {"status": "error", "message": "Quantity must be a whole number from 1 to 99."}
    if not all(tool_context.state.get(key) for key in ("name", "email", "mobile")):
        return {"status": "error", "message": "Collect and save user details with ecommerce_agent first."}
    tool_context.state.update({
        "category": expected_category, "item": selected,
        "quantity": str(count), "price": unit_price, "total": unit_price * count,
    })
    return {"status": "saved", "item": selected, "quantity": count, "unit_price": unit_price, "total": unit_price * count}


catalog_agent = LlmAgent(
    name="catalog_agent",
    description="Shows demo products, saves the cart, and routes checkout requests.",
    model=create_model(), before_model_callback=before_model, on_model_error_callback=on_model_error,
    instruction="""
    You are the catalog specialist for a DEMO shopping assistant.
    Explain that these are illustrative demo products and prices, not live stock.
    Only use this fixed catalog:
    """ + catalog_text() + """
    Workflow:
    - If the user has not selected a category, offer Smartphones, Laptops, Headphones.
    - Answer product questions, using at most three options at a time.
    - Before saving, get an explicit item and quantity from the user.
    - Call save_cart with category, item, quantity as a string, and UNIT price.
    - This demo supports one product line; a new selection replaces that line.
    - Only confirm the cart when save_cart returns status=saved. On error, correct the inputs.
    - Ask whether the user wants checkout. On yes, transfer to checkout_agent.
    - If the cart is already saved and the user asks checkout, transfer immediately.
    - If user details are missing, transfer back to ecommerce_agent to collect them.
    - For tracking, explain that order tracking is not available in this demo.
    - Never claim an order is placed or a payment is processed.
    Keep responses short, friendly and specific.
    """,
    tools=[save_cart], sub_agents=[checkout_agent], output_key="catalog_output",
)
