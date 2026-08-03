"""What a projection declares about itself.

A projection is not allowed to quietly do less than the model asks. When it
cannot materialize a semantic object, or when it emits something the model
does not hold, it must say so **here, in advance** - not by omission at
render time.

This is the machine-readable half of ADR-020's PI-1/PI-2/PI-6: the checker in
``src/benchmark/projection.py`` reads a projection's contract and treats an
undeclared absence or an undeclared generated object as a violation. Adding a
new one means editing the declaration, which is a visible, reviewable act.
Before this existed the allowances were hardcoded inside the checker, where a
new one could be added without anybody noticing the projection had grown a
new opinion.

Deliberately tiny: three frozen dataclasses and no behaviour. This is a
declaration format, not a capability system. ``ProjectionCapabilities`` in
docs/RAWRS_PROJECTION_ARCHITECTURE.md §4 is the fuller design; it earns its
place when a second projection needs to negotiate, not before.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Tuple


@dataclass(frozen=True)
class GeneratedObject:
    """Something the projection emits that no model object holds.

    Every entry is architectural debt by definition (PI-6: a projection
    consumes semantics, it does not create them). Declaring it does not make
    it correct - it makes it counted.
    """

    kind: str  # "heading", "page_marker", ...
    identity: str  # the exact realized identity, e.g. "Endnotes"
    reason: str


@dataclass(frozen=True)
class Limitation:
    """A class of semantic object this projection will not materialize.

    ``code`` is the diagnostic a checker emits when it observes the absence,
    so an unmaterialized object is never simply missing: it is missing *for a
    named, declared reason*.
    """

    code: str  # "front_matter_title_rendered_as_block"
    kind: str  # the object kind it applies to
    reason: str


@dataclass(frozen=True)
class ProjectionContract:
    format_id: str
    generates: Tuple[GeneratedObject, ...] = ()
    limitations: Tuple[Limitation, ...] = ()

    def generated_identities(self, kind: str) -> FrozenSet[str]:
        return frozenset(g.identity for g in self.generates if g.kind == kind)

    def limitation_codes(self) -> FrozenSet[str]:
        return frozenset(lim.code for lim in self.limitations)
