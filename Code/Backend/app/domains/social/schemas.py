from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.communication_schemas import ContentCreate, ContentItem, ContentPage

ReactionKind = Literal["interested", "excited", "support", "kudos", "wow", "relate"]
REACTION_KINDS: tuple[ReactionKind, ...] = (
    "interested",
    "excited",
    "support",
    "kudos",
    "wow",
    "relate",
)


class ReactionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reaction: ReactionKind | None = Field(...)


class ReactionSummary(BaseModel):
    counts: dict[ReactionKind, int]
    total: int
    mine: ReactionKind | None
    can_react: bool


__all__ = [
    "ContentCreate",
    "ContentItem",
    "ContentPage",
    "REACTION_KINDS",
    "ReactionInput",
    "ReactionKind",
    "ReactionSummary",
]
