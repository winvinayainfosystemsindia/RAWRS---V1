"""Alt text quality evaluation for RAWRS.

After AI generation, the quality evaluator inspects the result before
it is shown to the reviewer. If quality is poor, the caller (routes.py)
regenerates once automatically. Only after one regeneration attempt does
a low-quality result reach the reviewer — who is always the final gate.

Quality dimensions:
  1. Placeholder detection   — is the description a stub/boilerplate?
  2. Caption similarity      — does the description simply restate the
                               caption (copy-paste instead of describing
                               the visual)?
  3. Length                  — too short → uninformative; too long →
                               overwhelming for screen reader users
  4. Visual information      — does the description add content beyond
                               what is already in the caption?
  5. Model self-confidence   — if the model reported low confidence,
                               that is itself a quality signal

Quality evaluation is purely heuristic and is NOT used to block
publishing — it only informs whether to trigger one automatic retry.
The human reviewer always makes the final call.
"""

import re
from dataclasses import dataclass, field
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.ai.alt_text_generator import AltTextRequest, AltTextResult


@dataclass
class QualityResult:
    """Quality evaluation outcome for one alt text result."""

    overall_score: float        # 0.0–1.0 (higher = better)
    passes: bool                # True when quality is acceptable
    issues: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.passes:
            return f"Quality OK (score={self.overall_score:.2f})"
        return f"Quality issues (score={self.overall_score:.2f}): {'; '.join(self.issues)}"


# Minimum word count for a useful alt text description.
_MIN_WORDS = 8
# Maximum word count before verbosity becomes a problem.
_MAX_WORDS = 150
# If description shares > this fraction of caption's words → restatement.
_CAPTION_SIMILARITY_THRESHOLD = 0.65
# Minimum overall_score to pass quality check.
_PASS_THRESHOLD = 0.45


class AltTextQualityEvaluator:
    """Evaluate the quality of one AI-generated alt text result.

    Usage::

        evaluator = AltTextQualityEvaluator()
        quality = evaluator.evaluate(result, request)
        if not quality.passes:
            # trigger one retry
    """

    def evaluate(self, result: "AltTextResult", request: "AltTextRequest") -> QualityResult:
        scores: List[float] = []
        weights: List[float] = []
        issues: List[str] = []

        description = result.description.strip()

        # 1. Placeholder detection (weight 1.5 — blocking if True)
        if self._is_placeholder(description):
            issues.append(f"Description appears to be a placeholder: {description[:60]!r}")
            scores.append(0.0)
            weights.append(1.5)
        else:
            scores.append(1.0)
            weights.append(1.5)

        # 2. Caption similarity (weight 1.0)
        caption = (request.caption or "").strip()
        if caption:
            sim = self._word_overlap(description, caption)
            if sim > _CAPTION_SIMILARITY_THRESHOLD:
                issues.append(
                    f"Description restates caption at {sim:.0%} word overlap; "
                    "should describe what is visually present, not repeat the caption"
                )
                scores.append(max(0.0, 1.0 - sim))
            else:
                scores.append(1.0)
            weights.append(1.0)

        # 3. Length check (weight 0.8)
        word_count = len(description.split())
        if word_count < _MIN_WORDS:
            issues.append(f"Description too short ({word_count} words; minimum {_MIN_WORDS})")
            scores.append(0.1)
            weights.append(0.8)
        elif word_count > _MAX_WORDS:
            issues.append(
                f"Description too verbose ({word_count} words; maximum {_MAX_WORDS}); "
                "screen reader users benefit from concise alt text"
            )
            scores.append(0.5)
            weights.append(0.8)
        else:
            scores.append(1.0)
            weights.append(0.8)

        # 4. Visual information presence (weight 0.6)
        #    A description that mentions something beyond the caption words
        #    or contains visual vocabulary is a positive signal.
        visual_score = self._visual_info_score(description, caption)
        scores.append(visual_score)
        weights.append(0.6)

        # 5. Model self-confidence (weight 0.4)
        scores.append(min(1.0, result.confidence))
        weights.append(0.4)

        total_weight = sum(weights)
        overall = sum(s * w for s, w in zip(scores, weights)) / total_weight if total_weight else 0.0
        passes = overall >= _PASS_THRESHOLD and not (issues and "placeholder" in issues[0].lower())

        return QualityResult(overall_score=overall, passes=passes, issues=issues)

    # --- helpers ----------------------------------------------------------------

    @staticmethod
    def _is_placeholder(text: str) -> bool:
        if not text or len(text.strip()) < 5:
            return True
        lower = text.lower()
        placeholder_patterns = [
            r"\bstub\b",
            r"\bplaceholder\b",
            r"\btodo\b",
            r"\bn/?a\b",
            r"\bnot available\b",
            r"\bnot provided\b",
            r"\bmodel not loaded\b",
            r"rawrs_ai_stub",
        ]
        return any(re.search(p, lower) for p in placeholder_patterns)

    @staticmethod
    def _word_overlap(a: str, b: str) -> float:
        """Jaccard similarity of lowercased word sets, ignoring stopwords."""
        _STOP = {
            "a", "an", "the", "of", "in", "on", "at", "to", "for",
            "and", "or", "is", "are", "was", "were", "with", "this",
            "that", "it", "as", "by", "from", "be", "has", "had",
        }
        words_a = {w.lower() for w in re.findall(r"\w+", a) if w.lower() not in _STOP}
        words_b = {w.lower() for w in re.findall(r"\w+", b) if w.lower() not in _STOP}
        if not words_a or not words_b:
            return 0.0
        return len(words_a & words_b) / len(words_a | words_b)

    @staticmethod
    def _visual_info_score(description: str, caption: str) -> float:
        """Score 0–1 based on whether description adds visual content.

        Heuristic: descriptions that mention visual terms, measurements,
        colours, or words NOT present in the caption indicate the model
        is describing the image rather than restating context.
        """
        _VISUAL_TERMS = {
            "chart", "graph", "bar", "line", "pie", "scatter", "axis",
            "axes", "legend", "colour", "color", "shows", "depicts",
            "illustrates", "diagram", "figure", "image", "photograph",
            "photo", "map", "table", "grid", "column", "row", "arrow",
            "percent", "%", "trend", "increase", "decrease", "higher",
            "lower", "distribution", "pattern", "circle", "rectangle",
            "box", "horizontal", "vertical", "diagonal",
        }
        lower = description.lower()
        has_visual = any(term in lower for term in _VISUAL_TERMS)
        caption_words = set(re.findall(r"\w+", caption.lower())) if caption else set()
        desc_words = set(re.findall(r"\w+", lower))
        unique_to_desc = desc_words - caption_words
        has_unique = len(unique_to_desc) >= 3

        if has_visual and has_unique:
            return 1.0
        if has_visual or has_unique:
            return 0.7
        return 0.3
