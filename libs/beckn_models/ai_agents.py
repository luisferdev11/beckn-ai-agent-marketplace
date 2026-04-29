"""
Domain-specific models for AI Agent services on Beckn v2.

resourceAttributes in the catalog follow the AgentFacts schema
(projnanda/agentfacts-format), which is compatible with the NANDA
agent directory standard. AgentFacts describes WHO the agent is and
WHAT it can do. Pricing stays as an extra field in resourceAttributes
(it is Beckn-specific, not part of AgentFacts).

Execution results (on_status performanceAttributes) use a separate
schema defined in schemas/execution-result-v1.json.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field

AGENTFACTS_CONTEXT = "https://raw.githubusercontent.com/danielctecla/beckn-ai-agent-marketplace/main/schemas/agentfacts-v1.json"
EXECUTION_RESULT_CONTEXT = "https://raw.githubusercontent.com/danielctecla/beckn-ai-agent-marketplace/main/schemas/execution-result-v1.json"


# ---------------------------------------------------------------------------
# AgentFacts models (catalog resourceAttributes)
# ---------------------------------------------------------------------------

class AgentFactsSkill(BaseModel):
    id: str
    description: str
    inputModes: list[str]
    outputModes: list[str]
    supportedLanguages: Optional[list[str]] = None
    latencyBudgetMs: Optional[int] = None
    maxTokens: Optional[int] = None

    model_config = {"extra": "allow"}


class AgentFactsProvider(BaseModel):
    name: str
    url: str
    did: Optional[str] = None

    model_config = {"extra": "allow"}


class AgentFactsAuthentication(BaseModel):
    methods: list[str]
    requiredScopes: Optional[list[str]] = None

    model_config = {"extra": "allow"}


class AgentFactsCapabilities(BaseModel):
    modalities: list[str]
    streaming: bool = False
    batch: bool = False
    authentication: AgentFactsAuthentication

    model_config = {"extra": "allow"}


class AgentFactsEndpoints(BaseModel):
    static: list[str]
    adaptive_resolver: Optional[dict] = None

    model_config = {"extra": "allow"}


class AgentFactsSLA(BaseModel):
    maxLatencyMs: Optional[int] = None
    accuracy: Optional[float] = None
    uptime: Optional[float] = None

    model_config = {"extra": "allow"}


class AgentFacts(BaseModel):
    """
    Agent identity and capability declaration for the Beckn catalog.
    Compatible with projnanda/agentfacts-format.

    Used as resource.resourceAttributes in catalog/publish and on_discover.
    """

    context_url: str = Field(default=AGENTFACTS_CONTEXT, alias="@context")
    type_name: str = Field(default="beckn:AIAgentService", alias="@type")
    id: str
    agent_name: str
    label: str
    description: str
    version: str
    jurisdiction: Optional[str] = None
    provider: AgentFactsProvider
    endpoints: AgentFactsEndpoints
    capabilities: AgentFactsCapabilities
    skills: list[AgentFactsSkill]
    sla: Optional[AgentFactsSLA] = None
    evaluations: Optional[dict] = None
    telemetry: Optional[dict] = None
    certification: Optional[dict] = None
    # Not part of AgentFacts spec — kept here because handle_select() reads it
    pricing: Optional[dict] = None

    model_config = {"populate_by_name": True, "extra": "allow"}


# Backward-compat alias — old name used in some tests
AIAgentAttributes = AgentFacts


# ---------------------------------------------------------------------------
# Execution result model (on_status performanceAttributes)
# ---------------------------------------------------------------------------

class AgentExecutionResult(BaseModel):
    """
    Result of an agent execution, returned in on_status performanceAttributes.
    Schema: schemas/execution-result-v1.json
    """

    context_url: str = Field(default=EXECUTION_RESULT_CONTEXT, alias="@context")
    type_name: str = Field(default="beckn:AgentExecution", alias="@type")

    startedAt: Optional[str] = None
    completedAt: Optional[str] = None
    latencyMs: Optional[int] = None
    tokensUsed: Optional[dict[str, Any]] = None
    model: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    status: str = "PENDING"

    model_config = {"populate_by_name": True, "extra": "allow"}


# ---------------------------------------------------------------------------
# Legacy helpers (kept for backward compat — not used in new code)
# ---------------------------------------------------------------------------

class PricingInfo(BaseModel):
    model: str = "per_task"
    currency: str = "INR"
    unitPrice: float


class SLAInfo(BaseModel):
    maxLatency: str = "PT30S"
    accuracy: Optional[float] = None
    uptime: Optional[float] = None


class InputSchema(BaseModel):
    accepts: list[str] = Field(default_factory=lambda: ["text/plain"])
    maxSize: Optional[str] = None


class OutputSchema(BaseModel):
    returns: str = "application/json"
