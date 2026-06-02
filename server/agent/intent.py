from enum import StrEnum


class UserIntent(StrEnum):
    BROWSING = "browsing"
    BUYING = "buying"
    COMPARE = "compare"
    CART = "cart"


def detect_intent(message: str) -> UserIntent:
    text = message.lower()
    if any(word in text for word in ["对比", "比较", "哪个更", "哪个", "哪款", "谁更", "区别"]):
        return UserIntent.COMPARE
    if any(word in text for word in ["加到购物车", "下单", "购买", "结算"]):
        return UserIntent.CART
    if any(word in text for word in ["预算", "以内", "推荐", "适合", "要", "不要"]):
        return UserIntent.BUYING
    return UserIntent.BROWSING
