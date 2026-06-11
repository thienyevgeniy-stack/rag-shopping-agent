from server.agent.commerce_handlers import CartHandler, CompareHandler, ScenarioBundleHandler
from server.agent.conversation_handlers import ClarificationHandler, ContextFollowUpHandler
from server.agent.fallback_handler import FallbackHandler
from server.agent.recommendation_handler import RecommendationHandler
from server.agent.scenarios import ScenarioCatalog
from server.agent.visual_handler import VisualMatchHandler
from server.agent.workflow import AgentWorkflow
from server.nlu.clarification_policy import CategoryClarificationPolicy


def build_default_workflow(
    scenario_catalog: ScenarioCatalog | None = None,
    clarification_policy: CategoryClarificationPolicy | None = None,
) -> AgentWorkflow:
    return AgentWorkflow(
        handlers=[
            ClarificationHandler(clarification_policy),
            CartHandler(),
            CompareHandler(),
            ScenarioBundleHandler(scenario_catalog),
            VisualMatchHandler(),
            ContextFollowUpHandler(),
            RecommendationHandler(),
            FallbackHandler(),
        ]
    )
