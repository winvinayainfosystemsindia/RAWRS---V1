"""ValidationIssue model for RAWRS.

See docs/VALIDATION_RULES.md for severity levels, validation categories,
and the required issue fields.
"""

import uuid
from datetime import datetime
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


class ValidationIssueStatus(str, Enum):
    """Reviewer disposition of one validation issue.

    Mirrors the two triage actions ValidationIssueTable.tsx already
    offered as client-only state (Ignore / Review later) before this
    got a backend — OPEN is the default, IGNORED/DEFERRED are set via
    PATCH /documents/{job_id}/validation-issues/{issue_id}. No richer
    lifecycle than that: unlike CorrectionRecord, a validation issue
    never gets "applied" — see the model docstring's "read-only
    side-channel" note.
    """

    OPEN = "open"
    IGNORED = "ignored"
    DEFERRED = "deferred"


class ValidationIssue(BaseModel):
    """A single issue raised by the validation stage.

    References the affected page by ``page_number`` rather than holding
    a Page object (approved architecture decision #5), keeping
    validation a read-only side-channel that never couples back into the
    content tree. ``page_number`` is optional because some checks are
    document-wide rather than page-scoped (e.g. a missing H1).

    ``status``/``reviewed_at`` are reviewer triage state only — setting
    them never mutates the document or bumps document.version, per the
    read-only side-channel note above.
    """

    issue_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    severity: Severity
    rule_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    page_number: Optional[int] = Field(default=None, ge=1)
    suggested_action: Optional[str] = None
    status: ValidationIssueStatus = ValidationIssueStatus.OPEN
    reviewed_at: Optional[datetime] = None
