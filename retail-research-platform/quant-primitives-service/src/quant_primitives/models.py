"""The versioned, cited result wrapper every primitive returns.

This is the schema docs/engineering/data-architecture.md calls for at the
storage layer: `value` alone is never enough to publish a claim on -- a
citation like "alpha 1.2, computed [date]" only works if `computed_at`,
`pipeline_version`, and `input_as_of` travel with the value itself.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PrimitiveResult(BaseModel):
    name: str
    value: Any
    computed_at: datetime
    pipeline_version: str
    input_as_of: date
    confidence: ConfidenceLevel
    confidence_reason: str
    sample_size: int | None = None
