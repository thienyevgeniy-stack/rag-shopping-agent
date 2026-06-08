from collections.abc import AsyncIterator
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from server.agent.intent import UserIntent
from server.session.state import FilterCondition


SemanticIntent = Literal["recommend", "compare", "cart", "ask_product_detail", "clarify", "browse", "bundle"]
CartAction = Literal["none", "add", "remove", "update_quantity", "view", "checkout"]
ReferenceType = Literal["none", "last", "ordinal", "name", "brand", "cheapest"]
FilterKind = Literal["keyword", "max_price", "exclude", "product_type"]


class ChatMessageClient(Protocol):
    async def stream_messages(self, messages: list[dict]) -> AsyncIterator[str]:
        ...


class SemanticFilter(BaseModel):
    kind: FilterKind
    value: str


class SemanticPlan(BaseModel):
    intent: SemanticIntent = "recommend"
    cart_action: CartAction = "none"
    reference_type: ReferenceType = "none"
    reference_index: int | None = None
    reference_text: str = ""
    quantity: int | None = None
    query: str = ""
    filters: list[SemanticFilter] = Field(default_factory=list)
    needs_search: bool = True
    confidence: float = 0.0

    def to_user_intent(self) -> UserIntent:
        if self.intent == "compare":
            return UserIntent.COMPARE
        if self.intent == "cart":
            return UserIntent.CART
        if self.intent == "browse":
            return UserIntent.BROWSING
        return UserIntent.BUYING

    def to_filter_conditions(self) -> list[FilterCondition]:
        return [FilterCondition(kind=item.kind, value=item.value) for item in self.filters if item.value.strip()]
