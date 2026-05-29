"""
Beckn v2.0.0 contract models.

The Contract is the central object of a transaction. It evolves through
the flow: select (DRAFT) → init (DRAFT + performance/settlements) →
confirm (ACTIVE) → status (COMPLETED).

Reference: protocol-specifications-v2/api/v2.0.0/beckn.yaml
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


class Participant(BaseModel):
    id: str
    descriptor: Optional[dict[str, Any]] = None

    model_config = {"extra": "allow"}


class QuantitySpec(BaseModel):
    unitQuantity: int = 1
    unitCode: str = "UNIT"


class ContractResource(BaseModel):
    """A resource referenced within a contract commitment."""

    id: str
    descriptor: Optional[dict[str, Any]] = None
    quantity: Optional[QuantitySpec] = None

    model_config = {"extra": "allow"}


class OfferRef(BaseModel):
    id: str
    resourceIds: Optional[list[str]] = None

    model_config = {"extra": "allow"}


class CommitmentStatus(BaseModel):
    code: Optional[str] = None
    descriptor: Optional[dict[str, Any]] = None

    model_config = {"extra": "allow"}


class Commitment(BaseModel):
    id: Optional[str] = None
    descriptor: Optional[dict[str, Any]] = None
    status: Optional[CommitmentStatus] = None
    resources: list[ContractResource] = Field(default_factory=list)
    offer: Optional[OfferRef] = None

    model_config = {"extra": "allow"}


class Price(BaseModel):
    currency: str = "INR"
    value: str


class PriceBreakup(BaseModel):
    title: str
    price: Price


class Consideration(BaseModel):
    """Pricing information returned in on_select."""

    id: Optional[str] = None
    price: Optional[Price] = None
    status: Optional[CommitmentStatus] = None
    breakup: list[PriceBreakup] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class Performance(BaseModel):
    """Fulfillment tracking — updated in on_status with execution results."""

    id: str
    status: Optional[CommitmentStatus] = None
    performanceAttributes: Optional[dict[str, Any]] = None

    model_config = {"extra": "allow"}


class Settlement(BaseModel):
    id: str
    status: Optional[str] = None

    model_config = {"extra": "allow"}


class Contract(BaseModel):
    """The central transaction object in Beckn v2."""

    id: Optional[str] = None
    participants: list[Participant] = Field(default_factory=list)
    commitments: list[Commitment] = Field(default_factory=list)
    consideration: list[Consideration] = Field(default_factory=list)
    performance: list[Performance] = Field(default_factory=list)
    settlements: list[Settlement] = Field(default_factory=list)

    model_config = {"extra": "allow"}
