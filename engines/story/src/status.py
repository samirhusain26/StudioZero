"""PipelineStatus: the status update both routes yield (kept small so the series route
does not import the recap tree)."""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class PipelineStatus:
    """Represents a status update from the pipeline."""
    step: int
    message: str
    data: Optional[Dict[str, Any]] = None
    is_error: bool = False
    review_gate: bool = False
    retry_gate: bool = False  # Veo scene failure — user must retry/edit/skip before continuing
