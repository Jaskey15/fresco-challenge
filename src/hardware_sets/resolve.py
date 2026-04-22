"""Vocabulary-match confidence scoring for LLM-extracted sets.

See spec §4.4. **Never auto-corrects** — only annotates each field and
each set with a confidence number so a downstream UI can sort
"look at this first" items. Measures 'does the extracted value match
known vocabulary', not 'is the extraction correct'.
"""

from __future__ import annotations

from statistics import mean

from hardware_sets.types import Component, HardwareSet
from hardware_sets.vocab import (
    GLOBAL_FINISH_VOCAB,
    GLOBAL_MFR_VOCAB,
    MFR_SHORTCODE_RE,
    looks_like_finish,
    looks_like_mfr_code,
    norm,
)


def _score_mfr(value: str | None) -> float:
    if value is None:
        return 1.0
    v = norm(value) or ""
    if v in GLOBAL_MFR_VOCAB:
        return 1.0
    if looks_like_finish(v):
        return 0.2            # looks like a finish — swap risk
    if MFR_SHORTCODE_RE.match(v):
        return 0.7            # plausible short code not in vocab
    return 0.5


def _score_finish(value: str | None) -> float:
    if value is None:
        return 1.0
    v = norm(value) or ""
    if v in GLOBAL_FINISH_VOCAB:
        return 1.0
    if looks_like_finish(v):
        return 0.9
    if looks_like_mfr_code(v):
        return 0.2            # looks like a mfr — swap risk
    return 0.5


def _score_qty(value: int | None) -> float:
    return 1.0


def _score_component(comp: Component) -> Component:
    comp.confidence = {
        "mfr": _score_mfr(comp.mfr),
        "finish": _score_finish(comp.finish),
        "qty": _score_qty(comp.qty),
    }
    return comp


def _component_min(conf: dict[str, float]) -> float:
    return min(conf.values()) if conf else 1.0


def validate_and_score(sets: list[HardwareSet]) -> list[HardwareSet]:
    """Annotate every component with per-field confidences and every set with a mean."""
    for hw_set in sets:
        if hw_set.is_not_used or not hw_set.components:
            hw_set.confidence = 1.0
            continue
        for comp in hw_set.components:
            _score_component(comp)
        hw_set.confidence = mean(_component_min(c.confidence) for c in hw_set.components)
    return sets
