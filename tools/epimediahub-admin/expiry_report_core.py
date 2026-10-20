"""Strict provider-confirmed public-facing report row; no provider credentials."""
from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class Expiry:
    customer: str
    playlist: str
    day: date
