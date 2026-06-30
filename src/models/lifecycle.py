"""Universal object lifecycle status for RAWRS accessibility remediation.

Every visual object in RAWRS (tables, images, headings, footnotes, and
future object types) moves through the same lifecycle phases before a
document is considered fully accessible.

DETECTED         → The pipeline has found the object and added it to the
                   Document. No AI or human action taken yet.

AI_PROCESSED     → An AI model has run on the object (alt text generated,
                   table analyzed, etc.). Result is available for review
                   but has not yet been confirmed by a human.

HUMAN_REVIEWED   → A human reviewer has examined the object, possibly
                   edited AI output or corrected metadata. May need
                   validation before final approval.

ACCESSIBILITY_VALIDATED → All relevant accessibility validation rules
                   pass for this object (no ERROR or WARNING issues
                   directly associated with it).

EXPORT_VERIFIED  → The object was successfully written to the DOCX output
                   and the output was verified (e.g. image embedded,
                   table rendered correctly).

APPROVED         → The reviewer has explicitly marked this object as
                   complete and accessible. The document export gate
                   can consider this object done.

The lifecycle is intentionally linear (each status implies all previous
ones are satisfied), but objects may regress: editing a reviewed table
resets it to HUMAN_REVIEWED (losing ACCESSIBILITY_VALIDATED status).
"""

from enum import Enum


class ObjectLifecycleStatus(str, Enum):
    DETECTED = "DETECTED"
    AI_PROCESSED = "AI_PROCESSED"
    HUMAN_REVIEWED = "HUMAN_REVIEWED"
    ACCESSIBILITY_VALIDATED = "ACCESSIBILITY_VALIDATED"
    EXPORT_VERIFIED = "EXPORT_VERIFIED"
    APPROVED = "APPROVED"
