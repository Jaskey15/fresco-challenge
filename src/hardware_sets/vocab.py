"""Vocabulary sets and regex patterns for post-extraction validation.

Seeded from the four observed sample formats (Roselle bordered,
Commons Lanes bordered + prose, Shubenacadie unlabeled list,
Schulz labeled list + legend). Lowercase + uppercase entries are
stored directly; matching code normalizes to uppercase.
"""

from __future__ import annotations

import re

# Full names and short codes. Matching is case-insensitive — see _norm below.
GLOBAL_MFR_VOCAB: frozenset[str] = frozenset(
    s.upper()
    for s in {
        "IVE", "IVES",
        "VON", "VND", "VON DUPRIN",
        "SCH", "SCHLAGE",
        "LCN",
        "NGP",
        "ZER", "ZERO",
        "PEM", "PEMKO",
        "ROC", "ROCKWOOD",
        "GLY", "GJ", "GLYNN-JOHNSON",
        "HAG", "HAGER",
        "ADA", "ADAMS RITE",
        "TRI", "TRIMCO", "BBW",
        "ABH",
        "MED", "MEDECO",
        "SEN", "SENTRONIC",
        "ASS", "ASSA ABLOY",
        "SCE", "SECURITRON",
        "BLU", "BLUMCRAFT",
        "CRL", "C.R. LAURENCE",
        "KNX", "KNOX",
        "RIX", "RIXSON",
        "NOR", "NORTON",
        "ALUR",
        "TUBELITE",
    }
)

GLOBAL_FINISH_VOCAB: frozenset[str] = frozenset(
    s.upper()
    for s in {
        # BHMA 3-digit codes most common in samples
        "613", "626", "630", "652", "689", "691", "693", "622", "711",
        # US codes
        "US3", "US4", "US10", "US10B", "US26", "US26D", "US32", "US32D",
        # Color words
        "BLACK", "BSP", "OIL RUBBED BRONZE", "LIGHT BRONZE",
        "MILL ALUM", "PAINTED ENAMEL", "ALUMINUM",
    }
)

# BHMA 3-digit codes live in 600-695. US codes: US followed by 1-2 digits and an optional D/L.
_BHMA_RE = re.compile(r"^(6[0-9]{2})$")
_US_RE = re.compile(r"^US\d{1,2}[DLdl]?$")

FINISH_PATTERNS: tuple[re.Pattern[str], ...] = (_BHMA_RE, _US_RE)

MFR_SHORTCODE_RE = re.compile(r"^[A-Z]{2,4}$")


def norm(s: str | None) -> str | None:
    """Uppercase + strip; `None` passes through."""
    return s.strip().upper() if s else s


def looks_like_finish(value: str) -> bool:
    v = value.strip().upper()
    if v in GLOBAL_FINISH_VOCAB:
        return True
    for pat in FINISH_PATTERNS:
        m = pat.match(v)
        if not m:
            continue
        if pat is _BHMA_RE:
            code = int(m.group(1))
            return 600 <= code <= 695
        return True
    return False


def looks_like_mfr_code(value: str) -> bool:
    v = value.strip().upper()
    return v in GLOBAL_MFR_VOCAB or bool(MFR_SHORTCODE_RE.match(v))
