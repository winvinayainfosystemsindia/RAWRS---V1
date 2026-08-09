"""Architectural guardrail - mechanical enforcement of ADR-016 … ADR-020.

Not a validation system. Validation asks whether a *document* is correct;
this asks whether the *architecture* is still the one the ADRs describe. It
checks shape, not behaviour: which layer may import which, whether reading
order is being stored, whether the correction rail still has one owner per
rule, whether a projection has declared what it cannot do.

Why it exists: the freeze wrote the invariants down, and a written invariant
decays. The pre-P2 renderer violated an unwritten one for months. Anything
that is only true because everyone remembers it is not an invariant.

**Declared exceptions.** Three known deviations are listed with a reason and
what retires each. They are reported, never silently allowed - the same
violations vs findings split ADR-020 uses. Adding a fourth requires editing
this file, which is a visible act in review. That is the whole mechanism.

Run: ``python -m src.architecture.invariants``
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

SRC = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------- #
# layers
# --------------------------------------------------------------------------- #

# Depend downward only. A package may import itself and anything in
# FOUNDATION; nothing may import upward.
FOUNDATION = ("models", "architecture", "config", "utils")
PROJECTIONS = ("markdown", "docx")
BENCHMARK = ("benchmark",)

# Packages that decide semantics. A projection importing one of these is
# reconstructing rather than consuming (ADR-019, PI-6).
DECISION = (
    "headings", "structure", "verification", "tables", "images",
    "footnotes", "frontmatter", "accessibility", "ocr", "parser", "mathpix",
)


@dataclass(frozen=True)
class Violation:
    invariant: str
    subject: str
    detail: str

    def __str__(self) -> str:  # pragma: no cover - diagnostic only
        return f"[{self.invariant}] {self.subject}: {self.detail}"


@dataclass(frozen=True)
class DeclaredException:
    """A known deviation, with the reason it survives and what retires it."""

    invariant: str
    subject: str  # path suffix, e.g. "markdown_builder.py" or "models"
    imports: str
    reason: str
    retired_by: str


# Every entry here was found by this checker and kept deliberately. None is a
# licence to add more: an undeclared deviation is a violation.
EXCEPTIONS: Tuple[DeclaredException, ...] = (
    DeclaredException(
        invariant="AI-1",
        subject="src/models",
        imports="src.verification.evidence",
        reason=(
            "EvidenceSignal/EvidenceBundle are shared model primitives with zero "
            "internal imports; they sit under src/verification/ for historical "
            "reasons only. 21 modules import them, so relocating is a rename "
            "refactor, not an architecture change."
        ),
        retired_by="move evidence.py to src/models/evidence.py",
    ),
    DeclaredException(
        invariant="AI-2",
        subject="src/markdown/markdown_builder.py",
        imports="src.structure.paragraph_assembly",
        reason=(
            "build_markdown() assembles paragraphs when handed a Document that "
            "never ran Stage 5c (a direct call, a fixture). Calling the model's "
            "own function beats keeping a second copy of the rule, but a "
            "projection still should not be invoking a decision-maker."
        ),
        retired_by="P3 - the projection reads a ContentStream; the caller guarantees Stage 5c",
    ),
    DeclaredException(
        invariant="AI-2",
        subject="src/markdown/markdown_builder.py",
        imports="src.structure.content_stream",
        reason=(
            "L5'a: front matter is placed by the traversal, not by the renderer. "
            "Consuming a ContentStream is the direction AI-2 exists to push a "
            "projection in — but the projection still *builds* the stream, "
            "because nothing hands it one yet."
        ),
        retired_by="P3 - the caller builds the stream and passes it in",
    ),
    DeclaredException(
        invariant="AI-2",
        subject="src/docx/docx_generator.py",
        imports="src.structure.content_stream",
        reason=(
            "L5'a, same reason as the Markdown projection above: a front-matter "
            "item's role and text are read off the traversal instead of being "
            "mirrored from another module's rendering gates."
        ),
        retired_by="P3 - the caller builds the stream and passes it in",
    ),
    DeclaredException(
        invariant="AI-2",
        subject="src/docx/docx_generator.py",
        imports="src.markdown.markdown_builder",
        reason=(
            "DOCX still recovers structure by parsing Markdown, so it needs "
            "PAGE_BREAK_MARKER. A projection depending on another projection is "
            "the central defect ADR-019 named."
        ),
        retired_by="P4 - DocxProjection renders from the model; text parsing deleted",
    ),
)

# Modules that are projections today. DOCX is deliberately absent: it is not
# yet a first-class projection (it parses Markdown), so requiring a contract
# would record one it cannot honour. P4 adds it.
DECLARED_PROJECTIONS = ("src.markdown.markdown_builder",)


# --------------------------------------------------------------------------- #
# static analysis
# --------------------------------------------------------------------------- #

def _package_of(path: Path) -> str:
    rel = path.relative_to(SRC)
    return rel.parts[0] if len(rel.parts) > 1 else ""


def _imports(path: Path) -> List[str]:
    """Every ``src.*`` module this file imports, as dotted paths."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
        return []
    out: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            if node.module.startswith("src."):
                out.append(node.module)
        elif isinstance(node, ast.Import):
            out += [a.name for a in node.names if a.name.startswith("src.")]
    return out


def _python_files() -> List[Path]:
    return [p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts]


def _subject(path: Path) -> str:
    return str(path.relative_to(SRC.parent)).replace("\\", "/")


def _excepted(invariant: str, subject: str, module: str) -> bool:
    return any(
        e.invariant == invariant
        and subject.startswith(e.subject)
        and module.startswith(e.imports)
        for e in EXCEPTIONS
    )


def check_layering() -> List[Violation]:
    """AI-1 · the model layer depends on nothing above it.
    AI-2 · a projection imports no module that decides semantics.
    AI-3 · production never imports the benchmark harness."""
    out: List[Violation] = []
    for path in _python_files():
        pkg = _package_of(path)
        subject = _subject(path)
        for mod in _imports(path):
            parts = mod.split(".")
            target = parts[1] if len(parts) > 1 else ""
            if not target:
                continue

            if pkg == "models" and target not in FOUNDATION:
                if not _excepted("AI-1", subject, mod):
                    out.append(Violation("AI-1", subject, f"model layer imports {mod}"))

            if pkg in PROJECTIONS and target != pkg:
                if target in DECISION or target in PROJECTIONS:
                    if not _excepted("AI-2", subject, mod):
                        out.append(
                            Violation("AI-2", subject, f"projection imports {mod}")
                        )

            if pkg not in BENCHMARK and target in BENCHMARK:
                out.append(Violation("AI-3", subject, f"production imports {mod}"))
    return out


def check_reading_order_not_stored() -> List[Violation]:
    """AI-4 · reading order is derived, never persisted (ADR-018 rule 2).

    A stored stream is a second home for reading order, free to drift from the
    objects - the defect being removed from Markdown, recreated one layer up.
    """
    from src.models.content_stream import ContentStream
    from src.models.document import Document

    out: List[Violation] = []
    for name, field in Document.model_fields.items():
        annotation = str(field.annotation)
        if "ContentStream" in annotation or "ContentNode" in annotation:
            out.append(
                Violation("AI-4", "Document", f"field {name!r} stores a traversal ({annotation})")
            )
    if "nodes" not in ContentStream.model_fields:  # pragma: no cover - shape guard
        out.append(Violation("AI-4", "ContentStream", "lost its nodes field"))
    return out


def check_correction_rail() -> List[Violation]:
    """AI-5 · one owner per rule id.  AI-6 · every verifier satisfies the rail.

    ADR-016 makes the rail the only path a semantic decision takes. Two
    verifiers claiming one rule id, or a verifier that cannot apply what it
    proposes, breaks that guarantee quietly.
    """
    import src.verification.artifacts  # noqa: F401
    import src.verification.callouts  # noqa: F401
    import src.verification.figures  # noqa: F401
    import src.verification.footnotes  # noqa: F401
    import src.verification.frontmatter  # noqa: F401
    import src.verification.headings  # noqa: F401
    import src.verification.lists  # noqa: F401
    import src.verification.tables  # noqa: F401
    from src.verification.engine import engine

    out: List[Violation] = []
    owner: Dict[str, str] = {}
    for asset_type, verifier in sorted(engine._verifiers.items()):  # noqa: SLF001
        for required in ("inspect", "apply", "revert", "rule_table"):
            if not callable(getattr(verifier, required, None)):
                out.append(
                    Violation("AI-6", asset_type, f"verifier does not implement {required}()")
                )
        try:
            table = verifier.rule_table()
        except Exception as exc:  # pragma: no cover - defensive
            out.append(Violation("AI-6", asset_type, f"rule_table() raised {exc!r}"))
            continue
        for kind, spec in table.items():
            prior = owner.get(spec.rule_id)
            if prior is not None and prior != asset_type:
                out.append(
                    Violation(
                        "AI-5",
                        spec.rule_id,
                        f"claimed by both {prior!r} and {asset_type!r} (kind {kind!r})",
                    )
                )
            owner[spec.rule_id] = asset_type
    return out


def check_projection_contracts() -> List[Violation]:
    """AI-7 · every declared projection declares what it cannot do.

    An absence with no declared reason is a silent renderer decision, which is
    the class ADR-020 forbids outright.
    """
    from importlib import import_module

    from src.architecture.contract import ProjectionContract

    out: List[Violation] = []
    for module_path in DECLARED_PROJECTIONS:
        module = import_module(module_path)
        contract = getattr(module, "PROJECTION_CONTRACT", None)
        if not isinstance(contract, ProjectionContract):
            out.append(Violation("AI-7", module_path, "declares no PROJECTION_CONTRACT"))
            continue
        for lim in contract.limitations:
            if not lim.code or not lim.reason:
                out.append(Violation("AI-7", module_path, f"limitation {lim!r} is unexplained"))
        for gen in contract.generates:
            if not gen.reason:
                out.append(
                    Violation("AI-7", module_path, f"generated object {gen!r} has no reason")
                )
    return out


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #

CHECKS = (
    check_layering,
    check_reading_order_not_stored,
    check_correction_rail,
    check_projection_contracts,
)


def check_all() -> List[Violation]:
    out: List[Violation] = []
    for check in CHECKS:
        out.extend(check())
    return out


def main() -> int:  # pragma: no cover - CLI
    for exc in EXCEPTIONS:
        print(f"  declared exception [{exc.invariant}] {exc.subject} -> {exc.imports}")
        print(f"      retired by: {exc.retired_by}")
    print()
    violations = check_all()
    if not violations:
        print(f"architectural invariants: OK ({len(EXCEPTIONS)} declared exception(s))")
        return 0
    for v in violations:
        print(f"  VIOLATION {v}")
    print(f"\narchitectural invariants: {len(violations)} violation(s)")
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
