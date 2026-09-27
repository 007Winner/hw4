from __future__ import annotations

import os
import json
import re
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

try:
    from .models import AgentDeps, ChatReply
    from .tools import audit_event, get_product_details, get_product_stock, search_catalog
except ImportError:  # Supports `uvicorn main:app` from inside backend/.
    from models import AgentDeps, ChatReply
    from tools import audit_event, get_product_details, get_product_stock, search_catalog

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parent / ".env")
load_dotenv(ROOT.parent.parent / ".env")
PROMPT = (ROOT / "prompts" / "prompt.md").read_text(encoding="utf-8")


def build_agent() -> Agent:
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not configured. Copy .env.example to .env and add the key.")
    provider = OpenAIProvider(api_key=api_key, base_url=os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1"))
    model = OpenAIChatModel(os.getenv("PORTKEY_MODEL", "gpt-5.6-luna"), provider=provider)
    agent = Agent(model, output_type=ChatReply, deps_type=AgentDeps, system_prompt=PROMPT, retries=2, tools=[search_catalog, get_product_stock, get_product_details])

    @agent.system_prompt
    def customer_and_page_context(ctx: RunContext[AgentDeps]) -> str:
        customer = ctx.deps.customer
        page = ctx.deps.page_context
        identity = f"The shopper is {customer.name} ({customer.email})." if customer.name and customer.email else "The shopper is a guest; do not assume an identity."
        current_page = f"The shopper is currently viewing product_id={page.product_id}. Use get_product_details for that item before answering references like 'this' or 'it'." if page and page.product_id else "There is no specific product page context."
        return f"{identity} {current_page} Never reveal private identity details to the shopper or mention internal context plumbing."

    return agent


def run_chat(message: str, deps: AgentDeps | None = None) -> ChatReply:
    # Always perform the authoritative SQLite lookup before asking the model
    # to write a response. Product cards returned to the browser are these
    # database-backed records, never model-invented prices or quantities.
    deps = deps or AgentDeps()
    verified_products = search_catalog(message, limit=8)
    focused_product = None
    if deps.page_context and deps.page_context.product_id:
        # Page context comes from the browser, so treat stale or malformed
        # product IDs as missing context instead of turning a chat request
        # into a server error.
        try:
            focused_product = get_product_details(deps.page_context.product_id)
        except ValueError:
            focused_product = None
            audit_event("get_product_details", {"product_id": deps.page_context.product_id}, "stopped_product_not_found")
    if focused_product and all(product.product_id != focused_product.product_id for product in verified_products):
        verified_products.insert(0, focused_product)
    direct = deterministic_answer(message, focused_product or (verified_products[0] if len(verified_products) == 1 else None))
    if direct:
        audit_event("deterministic_answer", {"question_type": "price_or_stock"}, "returned_database_answer")
        return ChatReply(reply=direct, products=verified_products)
    verified_context = json.dumps([product.model_dump() for product in verified_products])
    if not os.getenv("PORTKEY_API_KEY"):
        audit_event("pydanticai_agent", {"model": os.getenv("PORTKEY_MODEL", "gpt-5.6-luna")}, "stopped_missing_portkey_key")
        return ChatReply(reply="The Campus Customs stylist is not connected yet. Add PORTKEY_API_KEY to the backend .env to enable live recommendations.", products=verified_products)
    page_note = f"The current page product is {focused_product.model_dump_json()}" if focused_product else "No product detail page is active."
    prompt = f"Verified database results (use these for all product facts): {verified_context}\n{page_note}\n\nShopper message: {message}"
    try:
        result = build_agent().run_sync(prompt, deps=deps).output
        reply = validate_reply(result.reply, verified_products)
        audit_event("pydanticai_agent", {"model": os.getenv("PORTKEY_MODEL", "gpt-5.6-luna")}, "returned_validated_reply")
    except Exception:
        # Keep catalogue discovery useful if Portkey or the configured model
        # is temporarily unavailable. The cards remain authoritative SQLite
        # results, and the shopper gets an honest status message.
        reply = "I found these verified catalogue matches. The stylist is temporarily unavailable, but you can open any card for exact price and size stock."
        audit_event("pydanticai_agent", {"model": os.getenv("PORTKEY_MODEL", "gpt-5.6-luna")}, "stopped_external_model_unavailable")
    return ChatReply(reply=reply, products=verified_products)


def deterministic_answer(message: str, product) -> str | None:
    """Answer unambiguous price/stock questions from SQLite without an LLM call."""
    if product is None:
        return None
    text = message.lower()
    asks_price = any(term in text for term in ("price", "cost", "how much"))
    asks_stock = any(term in text for term in ("stock", "available", "availability", "left", "in size"))
    if not (asks_price or asks_stock):
        return None
    stock = get_product_stock(product.product_id)
    size_match = re.search(r"\b(XXL|XL|XS|S|M|L)\b", message, re.IGNORECASE)
    size_words = {"double extra large": "XXL", "extra small": "XS", "extra large": "XL", "small": "S", "medium": "M", "large": "L"}
    size_word_match = next((word for word in size_words if re.search(rf"\b{word}\b", message, re.IGNORECASE)), None)
    size = size_match.group(1).upper() if size_match else size_words.get(size_word_match) if size_word_match else None
    if asks_stock:
        if size:
            entry = next((item for item in stock.inventory if item.size.upper() == size), None)
            if entry is None:
                availability = f"size {size} is not listed in the catalogue"
            elif entry.quantity == 0:
                availability = f"size {size} is Out of stock"
            else:
                availability = f"size {size} has {entry.quantity} available"
            return f"{product.name} is ${product.price:.2f}; {availability}."
        available = ", ".join(f"{item.size}: {item.quantity}" for item in stock.inventory if item.quantity > 0) or "none"
        unavailable = ", ".join(item.size for item in stock.inventory if item.quantity == 0)
        suffix = f" Out of stock: {unavailable}." if unavailable else ""
        return f"{product.name} is ${product.price:.2f}. Available sizes and quantities: {available}.{suffix}"
    return f"{product.name} is priced at ${product.price:.2f}."


def validate_reply(reply: str, products: list) -> str:
    """Reject unsupported product names, currency, or explicit stock claims in model prose."""
    known_names = {product.name.casefold() for product in products}
    bold_claims = re.findall(r"\*\*([^*]+)\*\*", reply)
    for claim in bold_claims:
        normalized_claim = re.sub(r"\$\s*\d+(?:\.\d{1,2})?", "", claim).strip(" -–—:").casefold()
        if not any(name in normalized_claim for name in known_names):
            return "I found verified catalogue matches, but I could not safely validate the stylist's product summary. Please open a product card for exact details."
    valid_prices = {f"{product.price:.2f}" for product in products}
    mentioned_prices = re.findall(r"\$\s*(\d+(?:\.\d{1,2})?)", reply)
    if any(f"{float(price):.2f}" not in valid_prices for price in mentioned_prices):
        return "I found these verified catalogue matches, but I could not safely validate the stylist's pricing summary. Please open a product card for exact price and size stock."
    valid_quantities = {str(item.quantity) for product in products for item in product.inventory}
    claims = re.findall(r"\b(\d+)\s+(?:in stock|available|left)\b", reply.lower())
    if any(quantity not in valid_quantities for quantity in claims):
        return "I found verified catalogue matches. Please open a product card for the exact size-level stock; I could not safely validate the stylist's availability summary."
    return reply
