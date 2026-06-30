"""ValidationIssue model for RAWRS.

See docs/VALIDATION_RULES.md for severity levels, validation categories,
and the required issue fields.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Severity of a validation issue.

    See docs/VALIDATION_RULES.md (Severity Levels) for definitions.
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationIssue(BaseModel):
    """A single issue raised by the validation stage.

    References the affected page by ``page_number`` rather than holding
    a Page object (approved architecture decision #5), keeping
    validation a read-only side-channel that never couples back into the
    content tree. ``page_number`` is optional because some checks are
    document-wide rather than page-scoped (e.g. a missing H1).
    """

    severity: Severity
    rule_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    page_number: Optional[int] = Field(default=None, ge=1)
    suggested_action: Optional[str] = None
