import re


IN_STOCK_PATTERNS = ("只看有货", "仅看有货", "有货", "现货", "有现货", "库存充足")
PRESALE_NEGATION_PATTERNS = ("不要预售", "不看预售", "非预售", "不是预售", "排除预售")

SERVICE_PATTERNS: dict[str, tuple[str, ...]] = {
    "invoice_policy": ("支持企业开票", "企业开票", "开发票", "发票"),
    "after_sales_policy": ("官方保修", "保修", "质保", "售后"),
    "same_day_shipping": ("今天能发货", "当天发货", "今日发货", "今天发", "现货发"),
    "coupon_policy": ("优惠券", "有券", "领券", "优惠", "折扣", "促销"),
}

NEGATIVE_REFINEMENT_TERMS = (
    "不要",
    "不想要",
    "不推荐",
    "排除",
    "除了",
    "先不要",
    "别",
    "不看",
)

FACET_PATTERNS: tuple[tuple[str, str, re.Pattern], ...] = (
    ("memory", "内存", re.compile(r"(?P<value>\d{1,3})\s*(?:g|gb|GB|G)\s*内存")),
    ("storage", "硬盘", re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?:t|tb|TB|T)\s*(?:硬盘|存储|固态)")),
    ("storage", "硬盘", re.compile(r"(?P<value>\d{2,4})\s*(?:g|gb|GB|G)\s*(?:硬盘|存储|固态)")),
    ("color", "颜色", re.compile(r"(?P<value>白色|黑色|蓝色|绿色|粉色|灰色|银色|金色|红色|紫色)")),
    ("shoe_size", "尺码", re.compile(r"(?P<value>\d{2})\s*(?:码|yards?)")),
)
