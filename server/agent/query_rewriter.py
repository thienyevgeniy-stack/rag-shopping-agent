from server.session.state import SessionState


def rewrite_query(message: str, session: SessionState) -> str:
    """Keep the MVP deterministic while preserving a hook for LLM rewriting."""
    filters = " ".join(item.value for item in session.filters)
    exclusions = " ".join(item.value for item in session.exclusions)
    parts = [message.strip()]
    if filters:
        parts.append(f"已确认条件: {filters}")
    if exclusions:
        parts.append(f"排除条件: {exclusions}")
    return " ".join(parts)
