# Model Comparison: Sonnet vs Haiku

**Date:** 2026-04-23
**Test:** `confidence_audit.py --extract --model <model>` against 3 demo PDFs with ground truth.

## Results

| Metric | Sonnet (claude-sonnet-4-6) | Haiku (claude-haiku-4-5) |
|---|---|---|
| Overall accuracy | ~97% | 82.9% (647/780) |
| Total errors | ~25 | 133 |
| Confidence recall | partial | 0% (nothing flagged) |

### Per-field accuracy (Haiku)

| Field | Accuracy | Errors |
|---|---|---|
| qty | 156/156 | 0 |
| description | 77/156 | 79 |
| catalog_number | 123/156 | 33 |
| mfr | 147/156 | 9 |
| finish | 144/156 | 12 |

### Per-PDF accuracy (Haiku)

| PDF | Correct | Errors |
|---|---|---|
| roselle_demo.pdf | 305/310 | 5 |
| morris_bank_demo.pdf | 96/140 | 44 |
| SJC_Div_demo.pdf | 246/330 | 84 |

## Key failure patterns with Haiku

- **Description pollution:** prepends qty units ("Ea.", "Set") and merges catalog numbers into descriptions.
- **Catalog truncation:** drops suffixes like "TBTRX", "EDA", "BUMP TORX" from catalog numbers, or pushes the whole value into description.
- **mfr/finish column confusion:** swaps mfr codes into finish (PE, BE) — the exact ambiguity Sonnet resolves from column context.
- **Confidence scoring useless:** all fields rated high confidence, 0% recall on actual errors.

## Conclusion

Sonnet is worth the cost for this task. Haiku's 14-point accuracy drop concentrates in the hardest parts of the problem (tabular column disambiguation, catalog number parsing) and its confidence scores provide no signal.
