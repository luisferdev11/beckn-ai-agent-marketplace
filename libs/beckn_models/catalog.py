"""
Beckn v2.0.0 catalog models.

These model the catalog/publish payload: providers, resources (agents),
offers, and locations. Resources carry domain-specific attributes via
the `resourceAttributes` dict, which for AI agents uses the schema
defined in ai_agents.py.

Reference: protocol-specifications-v2/api/v2.0.0/beckn.yaml
"""

from typing import Any, Optional
from pydantic import BaseModel, Field


class MediaFile(BaseModel):
    uri: str
    mimeType: Optional[str] = None
    label: Optional[str] = None


class Descriptor(BaseModel):
    """Human-readable description of any Beckn entity."""

    name: str
    shortDesc: Optional[str] = None
    longDesc: Optional[str] = None
    code: Optional[str] = None
    mediaFile: Optional[list[MediaFile]] = None

    model_config = {"extra": "allow"}


class GeoPoint(BaseModel):
    type: str = "Point"
    coordinates: list[float]


class Address(BaseModel):
    streetAddress: Optional[str] = None
    addressLocality: Optional[str] = None
    addressRegion: Optional[str] = None
    postalCode: Optional[str] = None
    addressCountry: Optional[str] = None


class Location(BaseModel):
    geo: Optional[GeoPoint] = None
    address: Optional[Address] = None


class Rating(BaseModel):
    ratingValue: Optional[float] = None
    ratingCount: Optional[int] = None
    bestRating: Optional[int] = None
    worstRating: Optional[int] = None


class Provider(BaseModel):
    id: str
    descriptor: Descriptor
    availableAt: Optional[list[Location]] = None

    model_config = {"extra": "allow"}


class Resource(BaseModel):
    """A resource in the catalog — for our domain, an AI agent."""

    id: str
    descriptor: Descriptor
    provider: Optional[Provider] = None
    rating: Optional[Rating] = None
    availableAt: Optional[list[Location]] = None
    resourceAttributes: Optional[dict[str, Any]] = None

    model_config = {"extra": "allow"}


class OfferValidity(BaseModel):
    startDate: str
    endDate: str


class Offer(BaseModel):
    id: str
    descriptor: Descriptor
    resourceIds: list[str]
    provider: Optional[Provider] = None
    validity: Optional[OfferValidity] = None
    considerations: Optional[list[dict[str, Any]]] = None

    model_config = {"extra": "allow"}


class PublishDirectives(BaseModel):
    catalogType: str = "regular"


class Catalog(BaseModel):
    """A published catalog of resources and offers."""

    id: str
    descriptor: Descriptor
    provider: Provider
    resources: list[Resource] = Field(default_factory=list)
    offers: list[Offer] = Field(default_factory=list)
    publishDirectives: Optional[PublishDirectives] = None

    model_config = {"extra": "allow"}
