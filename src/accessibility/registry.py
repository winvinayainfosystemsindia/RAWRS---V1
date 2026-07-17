"""Accessibility rule registry - asset-agnostic, mirrors
src/verification/engine.py's CrossSourceVerificationEngine/engine singleton
exactly (Section 3). Adding a rule means writing one AccessibilityRule
subclass and calling registry.register(...) - nothing here changes.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from loguru import logger

from src.accessibility.models import AccessibilityRule


class DuplicateRuleIdError(ValueError):
    """Raised when two rules register with the same rule_id - fails loudly
    at import time, not silently at scoring time (Section 3)."""


class AccessibilityRuleRegistry:
    def __init__(self) -> None:
        self._rules: Dict[str, AccessibilityRule] = {}

    def register(self, rule: AccessibilityRule) -> None:
        if rule.rule_id in self._rules:
            raise DuplicateRuleIdError(f"Duplicate rule_id: {rule.rule_id}")
        self._rules[rule.rule_id] = rule
        logger.debug("Accessibility registry: registered rule '{}'", rule.rule_id)

    def all(self) -> List[AccessibilityRule]:
        return list(self._rules.values())

    def by_category(self, category: str) -> List[AccessibilityRule]:
        return [r for r in self._rules.values() if r.category == category]

    def get(self, rule_id: str) -> Optional[AccessibilityRule]:
        return self._rules.get(rule_id)


# Module-level singleton - rule modules (e.g. src/accessibility/rules/headings.py)
# import this and call registry.register(...) at import time.
registry = AccessibilityRuleRegistry()
