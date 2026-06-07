import re

from server.rag.taxonomy import extract_product_type_matches
from server.session.state import FilterCondition


def extract_filters(message: str) -> list[FilterCondition]:
    filters: list[FilterCondition] = []

    for match in extract_product_type_matches(message):
        filters.append(FilterCondition(kind="product_type", value=match.product_type_id))

    max_price_values: list[str] = []
    for pattern in [
        r"预算\s*(?:是|为|大概|约|在)?\s*(\d+)\s*(元|块)?",
        r"(\d+)\s*(元|块)?\s*(以内|以下|之内)",
    ]:
        for match in re.finditer(pattern, message):
            value = match.group(1)
            if value not in max_price_values:
                max_price_values.append(value)
    for value in max_price_values:
        filters.append(FilterCondition(kind="max_price", value=value))

    if any(word in message for word in ["轻量", "轻便", "轻一点"]):
        filters.append(FilterCondition(kind="keyword", value="轻量"))

    if any(word in message for word in ["油皮", "混油"]):
        filters.append(FilterCondition(kind="keyword", value="油皮"))

    if any(word in message for word in ["敏感肌", "低刺激"]):
        filters.append(FilterCondition(kind="keyword", value="敏感肌"))

    for keyword in [
        "眼霜",
        "卸妆油",
        "咖啡",
        "蓝牙耳机",
        "耳机",
        "防晒",
        "防晒霜",
        "面霜",
        "手机",
        "拍照",
        "续航",
        "性能",
        "性价比",
    ]:
        if keyword in message:
            filters.append(FilterCondition(kind="keyword", value=keyword))

    exclusion_pattern = r"(?:不要|不想要|除了|排除)([^，。,.]+)"
    for match in re.finditer(exclusion_pattern, message):
        value = normalize_exclusion(match.group(1))
        if value:
            filters.append(FilterCondition(kind="exclude", value=value))

    return filters


def normalize_exclusion(value: str) -> str:
    value = value.strip().removesuffix("的").strip()
    if value.startswith("含") and len(value) > 1:
        value = value[1:].strip()
    return value
