import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Protocol

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
    def __init__(
        self,
        *,
        max_items: int = 500,
        ttl_seconds: int = 43200,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.max_items = max(1, max_items)
        self.ttl_seconds = max(1, ttl_seconds)
        self._clock = clock or time.time
        self._sessions: dict[str, tuple[SessionState, float]] = {}

    def get(self, session_id: str) -> SessionState:
        now = self._clock()
        self.prune_expired(now)
        entry = self._sessions.get(session_id)
        if entry is None:
            self.evict_oldest_if_full()
            state = SessionState(session_id=session_id)
        else:
            state = entry[0]
        self._sessions[session_id] = (state, now)
        return state

    def save(self, state: SessionState) -> None:
        self._sessions[state.session_id] = (state, self._clock())

    def count(self) -> int:
        self.prune_expired(self._clock())
        return len(self._sessions)

    def prune_expired(self, now: float) -> None:
        expired = [
            session_id
            for session_id, (_, last_seen) in self._sessions.items()
            if now - last_seen > self.ttl_seconds
        ]
        for session_id in expired:
            del self._sessions[session_id]

    def evict_oldest_if_full(self) -> None:
        if len(self._sessions) < self.max_items:
            return
        oldest_session_id = min(self._sessions.items(), key=lambda item: item[1][1])[0]
        del self._sessions[oldest_session_id]


class PersistentSessionStore(Protocol):
    def get(self, session_id: str) -> SessionState:
        ...

    def save(self, state: SessionState) -> None:
        ...

    def count(self) -> int:
        ...


class SQLiteSessionStore:
    def __init__(
        self,
        db_path: str | Path,
        *,
        max_items: int = 500,
        ttl_seconds: int = 43200,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.max_items = max(1, max_items)
        self.ttl_seconds = max(1, ttl_seconds)
        self._clock = clock or time.time
        self._lock = RLock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    last_seen REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_sessions_last_seen ON sessions(last_seen)")

    def get(self, session_id: str) -> SessionState:
        now = self._clock()
        with self._lock:
            self.prune_expired(now)
            row = self._fetch_session(session_id)
            if row is None:
                self.evict_oldest_if_full()
                state = SessionState(session_id=session_id)
            else:
                state = self._load_state(session_id, row[0])

            self._upsert_state(state, now)
            return state

    def save(self, state: SessionState) -> None:
        with self._lock:
            self.prune_expired(self._clock())
            self._upsert_state(state, self._clock())

    def count(self) -> int:
        with self._lock:
            self.prune_expired(self._clock())
            with self._connect() as connection:
                row = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()
        return int(row[0]) if row else 0

    def prune_expired(self, now: float) -> None:
        cutoff = now - self.ttl_seconds
        with self._connect() as connection:
            connection.execute("DELETE FROM sessions WHERE last_seen < ?", (cutoff,))

    def evict_oldest_if_full(self) -> None:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()
            if row is None or int(row[0]) < self.max_items:
                return
            oldest = connection.execute(
                "SELECT session_id FROM sessions ORDER BY last_seen ASC LIMIT 1"
            ).fetchone()
            if oldest is not None:
                connection.execute("DELETE FROM sessions WHERE session_id = ?", (oldest[0],))

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=30)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _fetch_session(self, session_id: str) -> tuple[str] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state_json FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return row

    def _load_state(self, session_id: str, state_json: str) -> SessionState:
        try:
            state = SessionState.model_validate_json(state_json)
        except ValueError:
            return SessionState(session_id=session_id)
        if state.session_id != session_id:
            return state.model_copy(update={"session_id": session_id})
        return state

    def _upsert_state(self, state: SessionState, last_seen: float) -> None:
        now = self._clock()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (session_id, state_json, last_seen, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    state_json = excluded.state_json,
                    last_seen = excluded.last_seen,
                    updated_at = excluded.updated_at
                """,
                (state.session_id, state.model_dump_json(), last_seen, now),
            )


class RedisSessionStore:
    def __init__(
        self,
        redis_url: str,
        *,
        max_items: int = 500,
        ttl_seconds: int = 43200,
        key_prefix: str = "rag:session",
        clock: Callable[[], float] | None = None,
        client=None,
    ) -> None:
        self.redis_url = redis_url
        self.max_items = max(1, max_items)
        self.ttl_seconds = max(1, ttl_seconds)
        self.key_prefix = key_prefix.rstrip(":")
        self.index_key = f"{self.key_prefix}:index"
        self._clock = clock or time.time
        self.client = client or self._create_client(redis_url)

    def get(self, session_id: str) -> SessionState:
        raw = self.client.get(self._key(session_id))
        if raw is None:
            state = SessionState(session_id=session_id)
        else:
            state = self._load_state(session_id, raw)
        self._touch(state)
        return state

    def save(self, state: SessionState) -> None:
        self._touch(state)

    def count(self) -> int:
        self._prune_stale_index_entries()
        return int(self.client.zcard(self.index_key))

    def _touch(self, state: SessionState) -> None:
        now = self._clock()
        self.client.setex(self._key(state.session_id), self.ttl_seconds, state.model_dump_json())
        self.client.zadd(self.index_key, {state.session_id: now})
        self._evict_oldest_if_full()

    def _evict_oldest_if_full(self) -> None:
        while int(self.client.zcard(self.index_key)) > self.max_items:
            popped = self.client.zpopmin(self.index_key, 1)
            if not popped:
                return
            session_id = self._decode(popped[0][0])
            self.client.delete(self._key(session_id))

    def _prune_stale_index_entries(self) -> None:
        for raw_session_id in self.client.zrange(self.index_key, 0, -1):
            session_id = self._decode(raw_session_id)
            if not self.client.exists(self._key(session_id)):
                self.client.zrem(self.index_key, session_id)

    def _key(self, session_id: str) -> str:
        return f"{self.key_prefix}:{session_id}"

    def _load_state(self, session_id: str, raw: str | bytes) -> SessionState:
        payload = self._decode(raw)
        try:
            state = SessionState.model_validate_json(payload)
        except ValueError:
            return SessionState(session_id=session_id)
        if state.session_id != session_id:
            return state.model_copy(update={"session_id": session_id})
        return state

    def _decode(self, value) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    def _create_client(self, redis_url: str):
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError(
                "SESSION_BACKEND=redis requires the redis package. "
                "Install server requirements before starting the service."
            ) from exc
        return redis.Redis.from_url(redis_url, decode_responses=True)


def product_type_values(filters: list[FilterCondition]) -> list[str]:
    values: list[str] = []
    for item in filters:
        if item.kind == "product_type" and item.value not in values:
            values.append(item.value)
    return values
