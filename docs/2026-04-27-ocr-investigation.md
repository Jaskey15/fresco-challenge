# OCR Investigation: Vector-Outlined PDFs

**Date:** 2026-04-27
**Trigger:** Akhil (Fresco CTO) reported 3/4 test PDFs produced no results, 1 hung. He provided `little_rock.pdf` as a failing sample.

## Root Cause

`little_rock.pdf` has zero extractable text. Every page contains ~1000-1700 vector curves and rectangles, but zero text characters. The authoring tool converted all text to outlines/paths (bezier curves that draw letter shapes instead of encoding them as characters).

Both pdfplumber and pypdf find nothing. The filter correctly reports "no schedule region found" because there's no text to match against.

## Three Types of PDFs

1. **Native/Digital** - Text exists as character data with fonts and positions. pdfplumber reads perfectly. All existing samples except little_rock are this type.
2. **Scanned/Image** - Pages are raster images (pixels). No text objects, just embedded JPEGs/PNGs. None of our samples are this type.
3. **Vector-Outlined** - Text converted to drawing instructions (curves). Visually perfect, programmatically opaque. `little_rock.pdf` is this type.

There's no PDF metadata flag to distinguish these. Detection requires checking page content: chars > 0 means native text; chars = 0 with curves or images means OCR is needed.

## Evidence

All samples checked with pdfplumber:

| PDF | Pages | Text Chars | Curves | Type |
|-----|-------|-----------|--------|------|
| little_rock.pdf | 9 | 0 | 12,887 | Vector-outlined |
| All other samples | varies | 23k-503k | 0 | Native |

Also found: `lyons_township.pdf` has text but the filter finds no regions - separate bug (filter pattern gap, not an OCR issue).

## Proposed Solution: ocrmypdf Preprocessing

**Approach:** When pdfplumber finds no text, run `ocrmypdf` to produce a new PDF with an invisible text layer, then feed that into the existing pipeline unchanged.

**Validated locally:**
```
ocrmypdf samples/little_rock.pdf /tmp/little_rock_ocr.pdf --skip-text
```
- Took ~15 seconds for 9 pages
- pdfplumber successfully reads the OCR'd output (943 chars on page 1, all pages populated)
- Filter finds region: pages 1-9 with `set_label` start marker, `END OF SECTION` end marker
- Text quality is good: manufacturer codes, set numbers, component descriptions all readable

**Why ocrmypdf over Vision API fallback:**
- Existing pipeline (filter, layout, bboxes) works unchanged on the OCR'd PDF - one codepath, not two
- No special-case logic needed downstream
- `--skip-text` flag means it's a no-op on native PDFs
- Tesseract is highly reliable on clean printed spec documents

**Dependencies to add:**
- `ocrmypdf` (Python package)
- `tesseract-ocr` (system package, needed in Dockerfile)
- Adds ~200MB to Docker image

## Pipeline Flow (Proposed)

```
PDF in
  -> check: does pdfplumber find text on any page?
     -> yes: proceed with existing pipeline
     -> no: run ocrmypdf to produce text-layered PDF, then proceed with existing pipeline
  -> filter -> layout -> extract -> result
```

## Open Questions

- Are all 4 of Akhil's test PDFs vector-outlined, or do some fail for other reasons?
- What caused the 4th PDF to "hang"? (different symptom - could be timeout, large PDF, or WebSocket issue)
- Should OCR run as a preprocessing step on every PDF (using `--skip-text`), or only when no text is detected?
