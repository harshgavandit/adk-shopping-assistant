import re
from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext
from catalog_agent.agent import catalog_agent
from model_config import create_model, before_model, on_model_error


def save_user_info(tool_context: ToolContext, name: str, email: str, mobile: str):
    """Validate and save the user's profile for this demo shopping session."""
    name, email, mobile = name.strip(), email.strip(), mobile.strip()
    if not name or len(name) > 100:
        return {"status": "error", "message": "Provide a name of 1 to 100 characters."}
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254:
        return {"status": "error", "message": "Provide a valid email address."}
    if not re.fullmatch(r"\+?[\d\s().-]+", mobile) or not 7 <= len(re.sub(r"\D", "", mobile)) <= 15:
        return {"status": "error", "message": "Provide a valid mobile number with 7 to 15 digits."}
    tool_context.state.update({"name": name, "email": email, "mobile": mobile})
    return {"status": "saved"}


root_agent = LlmAgent(
    name="ecommerce_agent",
    description="Greets shoppers, saves user details, and starts the demo shopping flow.",
    model=create_model(), before_model_callback=before_model, on_model_error_callback=on_model_error,
    instruction="""
    You are the welcoming agent for a demo shopping assistant.
    Workflow:
    - Collect the user's name, email and mobile number, asking for ONE missing detail at a time.
    - If they supply several details together, use them without asking again.
    - Call save_user_info once you have all three. Resolve tool errors before continuing.
    - Once the profile is saved, transfer purchase and catalog questions to catalog_agent.
    - Checkout also routes through catalog_agent, which owns checkout_agent.
    - If the user's intent is unclear, ask whether they want to browse the demo catalog.
    - For order tracking, explain that tracking is not implemented in this demo.
    - Never invent an order status, payment, availability, or successful purchase.
    You may greet, collect profile details and explain supported features yourself.
    Delegate product, cart and checkout work to catalog_agent.
    Keep responses short and friendly.
    """,
    tools=[save_user_info], sub_agents=[catalog_agent],
)
