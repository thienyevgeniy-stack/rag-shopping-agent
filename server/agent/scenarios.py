from dataclasses import dataclass

from server.rag.post_process import SearchFilters


@dataclass(frozen=True)
class ScenarioSlot:
    label: str
    query: str
    filters: SearchFilters
    max_items: int = 1


@dataclass(frozen=True)
class ScenarioBundle:
    title: str
    summary: str
    slots: tuple[ScenarioSlot, ...]


def detect_scenario_bundle(message: str) -> ScenarioBundle | None:
    if any(word in message for word in ["三亚", "海边", "度假", "旅游", "旅行"]):
        return ScenarioBundle(
            title="三亚度假组合方案",
            summary="我把需求拆成防晒保护、轻便穿搭、舒适出行和拍照记录四个槽位。",
            slots=(
                ScenarioSlot(
                    label="防晒保护",
                    query="三亚海边度假 高倍防晒 清爽 防水",
                    filters=SearchFilters(keywords=["防晒"], product_types=["beauty.sunscreen"]),
                ),
                ScenarioSlot(
                    label="轻便上衣",
                    query="三亚度假 速干 轻薄 透气 上衣",
                    filters=SearchFilters(keywords=["速干"]),
                ),
                ScenarioSlot(
                    label="舒适出行",
                    query="三亚旅行 轻量 舒适 运动鞋",
                    filters=SearchFilters(product_types=["clothes.sports_shoes"]),
                ),
                ScenarioSlot(
                    label="拍照记录",
                    query="旅行拍照手机 影像 轻薄",
                    filters=SearchFilters(keywords=["拍照"], product_types=["electronics.phone"]),
                ),
            ),
        )

    if any(word in message for word in ["通勤", "上班", "办公室"]):
        return ScenarioBundle(
            title="日常通勤组合方案",
            summary="我按通勤舒适、办公效率和路上陪伴来搭配。",
            slots=(
                ScenarioSlot(
                    label="通勤背包",
                    query="通勤 背包 轻便 多功能",
                    filters=SearchFilters(keywords=["背包"]),
                ),
                ScenarioSlot(
                    label="降噪耳机",
                    query="通勤 降噪 蓝牙耳机",
                    filters=SearchFilters(product_types=["electronics.headphones"]),
                ),
                ScenarioSlot(
                    label="轻办公设备",
                    query="轻薄 办公 平板 笔记本",
                    filters=SearchFilters(keywords=["办公"]),
                ),
            ),
        )

    if any(word in message for word in ["健身", "训练", "跑步装备", "运动套装"]):
        return ScenarioBundle(
            title="运动训练组合方案",
            summary="我按鞋、裤、上衣和运动陪伴设备来组合。",
            slots=(
                ScenarioSlot(
                    label="训练跑鞋",
                    query="训练 跑步 运动鞋 缓震",
                    filters=SearchFilters(product_types=["clothes.sports_shoes"]),
                ),
                ScenarioSlot(
                    label="运动裤",
                    query="运动裤 训练 速干",
                    filters=SearchFilters(product_types=["clothes.sports_pants"]),
                ),
                ScenarioSlot(
                    label="速干上衣",
                    query="速干 透气 训练 上衣",
                    filters=SearchFilters(keywords=["速干"]),
                ),
                ScenarioSlot(
                    label="运动耳机",
                    query="运动 蓝牙耳机 降噪",
                    filters=SearchFilters(product_types=["electronics.headphones"]),
                ),
            ),
        )

    if any(word in message for word in ["搭配一套", "组合推荐", "一套方案", "购买方案", "全套"]):
        return ScenarioBundle(
            title="跨类目组合方案",
            summary="我先给你一套覆盖护理、穿搭和数码辅助的通用组合。",
            slots=(
                ScenarioSlot(
                    label="基础护理",
                    query=f"{message} 护理 防晒 保湿",
                    filters=SearchFilters(keywords=["保湿"]),
                ),
                ScenarioSlot(
                    label="穿搭单品",
                    query=f"{message} 轻便 运动 穿搭",
                    filters=SearchFilters(product_types=["clothes.sports_shoes", "clothes.sports_pants"]),
                ),
                ScenarioSlot(
                    label="数码辅助",
                    query=f"{message} 手机 耳机",
                    filters=SearchFilters(product_types=["electronics.phone", "electronics.headphones"]),
                ),
            ),
        )

    return None


def build_bundle_answer(bundle: ScenarioBundle, grouped_cards: list[tuple[ScenarioSlot, list[dict]]]) -> str:
    pieces = [f"我按“{bundle.title}”来搭配。{bundle.summary}"]
    for slot, cards in grouped_cards:
        if cards:
            card = cards[0]
            pieces.append(f"{slot.label}：{card['name']}，¥{int(float(card['price']))}，{card['reason']}")
        else:
            pieces.append(f"{slot.label}：当前商品库里暂时没有足够匹配的商品。")
    pieces.append("你可以继续说预算、品牌偏好或删掉某一类，我会按这套方案继续收敛。")
    return " ".join(pieces)
