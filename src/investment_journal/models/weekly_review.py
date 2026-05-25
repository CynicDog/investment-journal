"""Weekly review issue: per-position update + catalysts + risks delta."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ThesisStatus = Literal["still-holds", "monitor", "re-check-needed"]


class PositionUpdate(BaseModel):
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,9}$")
    news_bullets: list[str] = Field(
        min_length=0,
        description="Each bullet should include an inline citation (link).",
    )
    valuation_line: str = Field(
        description="One line, e.g. 'Fwd P/E ~Xx vs 5y avg ~Yx ([source](url))'.",
    )
    thesis_status: ThesisStatus
    thesis_status_note: str = Field(
        min_length=1, description="One sentence explaining the status."
    )


class Catalyst(BaseModel):
    when: date
    ticker: str
    event: str = Field(min_length=1)
    issue_link: str | None = None


class WeeklyReview(BaseModel):
    iso_week: str = Field(pattern=r"^\d{4}-W\d{2}$")
    generated_on: date
    per_position: dict[str, PositionUpdate]
    catalysts_30d: list[Catalyst] = Field(default_factory=list)
    risks_surfaced: list[str] = Field(
        default_factory=list,
        description="Risk IDs created in this review (each gets a child issue + risks/<id>.md file).",
    )
    risks_resolved: list[str] = Field(
        default_factory=list,
        description="Risk IDs resolved this week.",
    )

    @model_validator(mode="after")
    def _per_position_keys_match(self) -> "WeeklyReview":
        for k, v in self.per_position.items():
            if k != v.ticker:
                raise ValueError(
                    f"per_position key '{k}' does not match its PositionUpdate.ticker '{v.ticker}'"
                )
        return self
