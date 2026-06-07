from pydantic import BaseModel, Field


class FilterCondition(BaseModel):
    kind: str
    value: str


class ConversationTurn(BaseModel):
    role: str
    content: str


class SessionState(BaseModel):
    session_id: str
    history: list[ConversationTurn] = Field(default_factory=list)
    filters: list[FilterCondition] = Field(default_factory=list)
    exclusions: list[FilterCondition] = Field(default_factory=list)
    candidate_products: list[str] = Field(default_factory=list)
    candidate_product_cards: list[dict] = Field(default_factory=list)
    pending_subject: str = ""
    cart: list[dict] = Field(default_factory=list)

    def add_user_message(self, content: str) -> None:
        self.history.append(ConversationTurn(role="user", content=content))

    def add_assistant_message(self, content: str) -> None:
        self.history.append(ConversationTurn(role="assistant", content=content))

    def merge_filters(self, filters: list[FilterCondition]) -> None:
        if self.starts_new_product_scope(filters):
            self.reset_product_scope()
        for item in filters:
            target = self.exclusions if item.kind == "exclude" else self.filters
            if item not in target:
                target.append(item)

    def starts_new_product_scope(self, incoming_filters: list[FilterCondition]) -> bool:
        incoming_types = product_type_values(incoming_filters)
        if not incoming_types:
            return False

        existing_types = product_type_values(self.filters)
        if not existing_types:
            return False

        return set(incoming_types) != set(existing_types)

    def reset_product_scope(self) -> None:
        self.filters = []
        self.exclusions = []
        self.candidate_products = []
        self.candidate_product_cards = []
        self.pending_subject = ""


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState(session_id=session_id)
        return self._sessions[session_id]


def product_type_values(filters: list[FilterCondition]) -> list[str]:
    values: list[str] = []
    for item in filters:
        if item.kind == "product_type" and item.value not in values:
            values.append(item.value)
    return values
