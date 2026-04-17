"""
Domain-specific models for AI Agent services on Beckn v2.

These extend the generic Beckn Resource with AI-specific attributes
using JSON-LD (@context, @type). This schema is local to the project —
no official Beckn domain schema for AI agents exists yet.

Usage in catalog resourceAttributes:
    {
        "@context": "https://schema.beckn.io/ai-agents/v1/",
        "@type": "beckn:AIAgentService",
        "capabilities": ["document_summary"],
        ...
    }
"""

from typing import Any, Optional
from pydantic import BaseModel, Field

JSONLD_CONTEXT = "https://schema.beckn.io/ai-agents/v1/"
JSONLD_TYPE = "beckn:AIAgentService"


class InputSchema(BaseModel):
    accepts: list[str] = Field(default_factory=lambda: ["text/plain"])
    maxSize: Optional[str] = None


class OutputSchema(BaseModel):
    returns: str = "application/json"


class PricingInfo(BaseModel):
    model: str = "per_task"
    currency: str = "INR"
    unitPrice: float


class SLAInfo(BaseModel):
    maxLatency: str = "PT30S"
    accuracy: Optional[float] = None
    uptime: Optional[float] = None


class CredentialInfo(BaseModel):
    type: str
    issuer: str
    validUntil: Optional[str] = None


class ModelInfo(BaseModel):
    provider: Optional[str] = None
    version: Optional[str] = None


class AIAgentAttributes(BaseModel):
    """
    Domain-specific attributes for an AI agent resource.

    This maps to resource.resourceAttributes in the Beckn catalog.
    Uses JSON-LD @context and @type for semantic interoperability.
    """

    context_url: str = Field(default=JSONLD_CONTEXT, alias="@context")
    type_name: str = Field(default=JSONLD_TYPE, alias="@type")

    capabilities: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=lambda: ["en"])
    inputSchema: Optional[InputSchema] = None
    outputSchema: Optional[OutputSchema] = None
    pricing: Optional[PricingInfo] = None
    sla: Optional[SLAInfo] = None
    dataResidency: Optional[str] = None
    modelInfo: Optional[ModelInfo] = None
    credentials: list[CredentialInfo] = Field(default_factory=list)

    model_config = {"populate_by_name": True, "extra": "allow"}


class AgentExecutionResult(BaseModel):
    """
    Result of an agent execution, returned in on_status performanceAttributes.
    For Iter 0 this is a mock; real agents will populate this with actual results.
    """

    context_url: str = Field(default=JSONLD_CONTEXT, alias="@context")
    type_name: str = Field(default="beckn:AgentExecution", alias="@type")

    startedAt: Optional[str] = None
    completedAt: Optional[str] = None
    latencyMs: Optional[int] = None
    tokensConsumed: Optional[int] = None
    result: Optional[dict[str, Any]] = None
    status: str = "PENDING"

    model_config = {"populate_by_name": True, "extra": "allow"}
