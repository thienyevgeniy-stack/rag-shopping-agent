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
    cart: list[dict] = Field(default_factory=list)

    def add_user_message(self, content: str) -> None:
        self.history.append(ConversationTurn(role="user", content=content))

    def add_assistant_message(self, content: str) -> None:
        self.history.append(ConversationTurn(role="assistant", content=content))

    def merge_filters(self, filters: list[FilterCondition]) -> None:
        for item in filters:
            target = self.exclusions if item.kind == "exclude" else self.filters
            if item not in target:
                target.append(item)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def get(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState(session_id=session_id)
        return self._sessions[session_id]
