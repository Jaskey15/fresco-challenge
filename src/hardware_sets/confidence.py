from __future__ import annotations

import re

from hardware_sets.types import FieldScore, HardwareSet

FINISH_PATTERN = re.compile(
    r"^("
    r"6\d{2}"
    r"|US\d{1,2}[A-Z]?"
    r"|BSP|BRASS|BRONZE|CHROME|BLACK"
    r"|SATIN|NICKEL|PEWTER|STAINLESS"
    r"|PAINTED ENAMEL|OIL RUBBED BRONZE|LIGHT BRONZE"
    r"|DARK BRONZE|SATIN BRONZE|SATIN CHROME"
    r"|POLISHED|PRIMED|ALUMINUM|DULL"
    r")$",
    re.IGNORECASE,
)

CATALOG_MIXED_PATTERN = re.compile(r"(?=.*[A-Za-z])(?=.*\d)")

SMALL_DOC_THRESHOLD = 5

REVIEW_THRESHOLD = 0.5


def _matches_finish(value: str) -> bool:
    return bool(FINISH_PATTERN.match(value.strip()))


def score_finish(value: str | None) -> FieldScore:
    if value is None:
        return FieldScore(1.0, None)
    if _matches_finish(value):
        return FieldScore(1.0, None)
    return FieldScore(0.5, "finish code not recognized")


def build_mfr_frequency(sets: list[HardwareSet]) -> dict[str, int]:
    freq: dict[str, int] = {}
    for s in sets:
        seen_in_set: set[str] = set()
        for comp in s.components:
            if comp.mfr and comp.mfr not in seen_in_set:
                seen_in_set.add(comp.mfr)
                freq[comp.mfr] = freq.get(comp.mfr, 0) + 1
    return freq


def score_mfr(
    value: str | None,
    mfr_freq: dict[str, int],
    total_sets: int,
) -> FieldScore:
    if value is None:
        return FieldScore(1.0, None)
    if _matches_finish(value):
        return FieldScore(0.3, "matches finish pattern — possible mfr/finish swap")
    if total_sets >= SMALL_DOC_THRESHOLD:
        count = mfr_freq.get(value, 0)
        if count >= 2:
            return FieldScore(1.0, None)
        return FieldScore(0.7, "manufacturer code seen only once")
    return FieldScore(1.0, None)


def score_catalog_number(value: str | None) -> FieldScore:
    if value is None:
        return FieldScore(1.0, None)
    stripped = value.strip()
    if _matches_finish(stripped):
        return FieldScore(0.3, "looks like a finish/mfr code, not a catalog number")
    if CATALOG_MIXED_PATTERN.search(stripped):
        return FieldScore(1.0, None)
    return FieldScore(0.5, "unusual catalog number format")


def score_qty(value: int | None, *, has_siblings_with_qty: bool) -> FieldScore:
    if value is not None:
        return FieldScore(1.0, None)
    if has_siblings_with_qty:
        return FieldScore(0.5, "missing quantity while other components have one")
    return FieldScore(1.0, None)


def score_description(value: str | None) -> FieldScore:
    if value is None:
        return FieldScore(0.3, "missing description")
    if len(value.strip()) <= 2:
        return FieldScore(0.5, "very short description — possible parsing artifact")
    return FieldScore(1.0, None)


def score_confidence(sets: list[HardwareSet]) -> None:
    mfr_freq = build_mfr_frequency(sets)
    total_sets = len(sets)

    for s in sets:
        has_siblings_with_qty = any(c.qty is not None for c in s.components)
        min_score = 1.0

        for comp in s.components:
            comp.confidence = {
                "qty": score_qty(comp.qty, has_siblings_with_qty=has_siblings_with_qty),
                "description": score_description(comp.description),
                "catalog_number": score_catalog_number(comp.catalog_number),
                "mfr": score_mfr(comp.mfr, mfr_freq, total_sets),
                "finish": score_finish(comp.finish),
            }
            for fs in comp.confidence.values():
                if fs.score < min_score:
                    min_score = fs.score

        if s.continued_on:
            min_score = max(0.0, min_score - 0.1)

        s.confidence = min_score
