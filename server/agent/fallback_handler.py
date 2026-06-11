from collections.abc import AsyncIterator

from server.agent.responses import build_done_payload, stream_text
from server.agent.workflow import AgentTurnContext


class FallbackHandler:
    def matches(self, context: AgentTurnContext) -> bool:
        return True

    async def handle(self, context: AgentTurnContext) -> AsyncIterator[dict]:
        context.metadata["fallback"] = {
            "reason": "no_explicit_handler_matched",
            "plan_intent": context.plan.intent,
        }
        answer = (
            "我还没有足够信息继续这个操作。你可以先告诉我想看的商品类型、预算、品牌，"
            "或者明确说“推荐”“对比”“加入购物车”。"
        )
        async for item in stream_text(answer):
            yield item
        context.session.add_assistant_message(answer)
        yield {
            "event": "done",
            "data": build_done_payload(
                context.session_id,
                context.session,
                needs_clarification=True,
                plan=context.plan,
                trace_id=context.trace_id,
            ),
        }
