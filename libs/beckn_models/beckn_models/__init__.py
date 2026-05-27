"""
Beckn v2.0.0 shared models for the AI Agent Marketplace.

This package provides Pydantic models for the Beckn protocol transport layer
(context, ack) and business layer (catalog, contract), plus domain-specific
models for AI agent services.

Install in editable mode from any service:
    pip install -e ../../libs/beckn_models
"""

from beckn_models.context import BecknContext, BecknRequest, BecknAck, ack_response
from beckn_models.catalog import (
    Descriptor,
    Provider,
    GeoPoint,
    Address,
    Location,
    Resource,
    Offer,
    Catalog,
)
from beckn_models.contract import (
    Participant,
    QuantitySpec,
    ContractResource,
    OfferRef,
    CommitmentStatus,
    Commitment,
    Price,
    PriceBreakup,
    Consideration,
    Performance,
    Settlement,
    Contract,
)
from beckn_models.ai_agents import AIAgentAttributes, AgentExecutionResult
from beckn_models.planning import (
    SkillRequest,
    ExtractSkillsRequest,
    ExtractSkillsResponse,
    AgentCandidate,
    ComposeRequest,
    StepRecommendation,
    StepAlternative,
    PlanStep,
    PlanEstimates,
    Plan,
    PlanRequest,
    PlanResponse,
)

__version__ = "0.1.0"
