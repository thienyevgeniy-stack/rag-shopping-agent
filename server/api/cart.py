import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from server.agent.orchestrator import Orchestrator
from server.app_container import get_orchestrator
from server.commerce.facts import get_fact_provider
from server.config import Settings, get_settings
from server.session.memory import refresh_session_memory
from server.tools.cart import build_cart_item, build_cart_payload
from server.tools.product_urls import build_product_detail_url, build_product_image_url


router = APIRouter(prefix="/cart", tags=["cart"])


class CartItemMutation(BaseModel):
    session_id: str = Field(default="default", min_length=1, max_length=128)
    product_id: str = Field(min_length=1, max_length=128)
    quantity_delta: int = Field(default=1, ge=-99, le=99)


@router.post("/items")
async def mutate_cart_item(
    request: CartItemMutation,
    orchestrator: Orchestrator = Depends(get_orchestrator),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if request.quantity_delta == 0:
        raise HTTPException(status_code=400, detail="quantity_delta must not be zero")

    session = orchestrator.sessions.get(request.session_id)
    try:
        product = find_product_card(session.candidate_product_cards, request.product_id)
        if product is None:
            product = load_product_card_from_catalog(
                settings.product_data_file,
                product_id=request.product_id,
                public_base_url=settings.public_base_url,
            )
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")

        apply_quantity_delta(session.cart, product=product, quantity_delta=request.quantity_delta)
        refresh_session_memory(session)
        return build_cart_payload(session.cart)
    finally:
        orchestrator.sessions.save(session)


@router.get("")
async def get_cart(
    session_id: str = "default",
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> dict[str, Any]:
    session = orchestrator.sessions.get(session_id)
    return build_cart_payload(session.cart)


def apply_quantity_delta(cart: list[dict], *, product: dict, quantity_delta: int) -> None:
    existing = next((item for item in cart if item.get("product_id") == product.get("id")), None)
    if existing is None:
        if quantity_delta > 0:
            cart.append(build_cart_item(product, quantity_delta))
        return

    next_quantity = int(existing.get("quantity", 0)) + quantity_delta
    if next_quantity <= 0:
        cart.remove(existing)
        return
    existing["quantity"] = next_quantity


def find_product_card(cards: list[dict], product_id: str) -> dict | None:
    for card in cards:
        if str(card.get("id", "")) == product_id:
            return card
    return None


def load_product_card_from_catalog(
    product_data_file: Path,
    *,
    product_id: str,
    public_base_url: str,
) -> dict | None:
    products = json.loads(product_data_file.read_text(encoding="utf-8"))
    for item in products:
        if str(item.get("id", "")) != product_id:
            continue
        facts = get_fact_provider()
        price = facts.price(item)
        stock = facts.stock(item)
        return {
            "id": item.get("id", ""),
            "name": item.get("name", ""),
            "category": item.get("category", ""),
            "brand": item.get("brand", ""),
            "price": float(price.value if price.available else item.get("price", 0)),
            "stock": stock.value if stock.available else item.get("stock"),
            "image_url": build_product_image_url(item.get("image_url", ""), public_base_url),
            "detail_url": build_product_detail_url(
                product_id=item.get("id", ""),
                raw_detail_url=item.get("detail_url", ""),
                public_base_url=public_base_url,
            ),
            "reason": "",
        }
    return None
