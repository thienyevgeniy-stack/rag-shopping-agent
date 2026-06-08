from server.agent.commerce_handlers import CartHandler, CompareHandler, ScenarioBundleHandler
from server.agent.conversation_handlers import ClarificationHandler, ContextFollowUpHandler
from server.agent.recommendation_handler import RecommendationHandler
from server.agent.workflow import AgentWorkflow


def build_default_workflow() -> AgentWorkflow:
    return AgentWorkflow(
        handlers=[
            ClarificationHandler(),
            CartHandler(),
            CompareHandler(),
            ScenarioBundleHandler(),
            ContextFollowUpHandler(),
            RecommendationHandler(),
        ]
    )
