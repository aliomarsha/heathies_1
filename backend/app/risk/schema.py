"""The structured object the risk model must return.

Used three ways: as the strict JSON schema passed to `.parse()`, to validate the fallback JSON,
and to validate fixture output - so every path produces exactly the same shape.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RiskTier = Literal["Low", "Average", "Moderate", "High"]


class RiskProfile(BaseModel):
    """Long-term (epidemiological) breast cancer risk-factor breakdown. Not a diagnosis."""

    model_config = ConfigDict(extra="forbid")

    estimated_risk_tier: RiskTier = Field(
        description="Long-term statistical risk tier relative to women of the same age, in the spirit of "
                    "Gail / Tyrer-Cuzick style factors. Never a statement about current disease."
    )
    non_modifiable_historical_factors: list[str] = Field(
        description="Background, reproductive, family-history or genetic factors that cannot be changed."
    )
    modifiable_lifestyle_factors: list[str] = Field(
        description="Routine or lifestyle factors the person could change (alcohol, activity, smoking, ...)."
    )
    clinical_screening_recommendations: list[str] = Field(
        description="Evidence-based preventive next steps to discuss with a clinician."
    )


MAX_ITEMS = 6
MAX_ITEM_CHARS = 240
