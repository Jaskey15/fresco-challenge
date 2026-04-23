# Extraction Pipeline Architecture

The pipeline answers one question: given a specbook PDF, which door hardware sets does it contain, and exactly where in the document does each one live?

It runs in three sequential stages — filter, layout, extract — each with a narrow responsibility.

---

## Stage 1 — Filter (`hardware_sets/filter.py`)

**What it does:** Scans every page and returns a list of `ScheduleRegion(start_page, end_page)` — the page ranges that actually contain hardware schedules.

**Why it exists as a separate stage:** Specbooks are long (50–200+ pages). Sending the whole document to the LLM would be expensive, slow, and would dilute the signal. Most pages are architectural drawings, structural specs, or Division 01 boilerplate — irrelevant to hardware. The filter stage is cheap (pure regex over extracted text) and narrows the LLM's input to only the pages that matter.

**How it finds regions:** Two-tier pattern matching on page text. High-confidence patterns (`HW 1`, `Hardware Group No. 3`, `Set: A`) fire immediately. Low-confidence patterns (`DOOR HARDWARE SCHEDULE`, `Hardware Schedule`) are section headers that appear on every page of the schedule section — they only count if the page also passes a tabular content guard (quantity rows, component names, etc.) that distinguishes real schedule pages from narrative prose. A heuristic fallback catches PDFs that use none of the named patterns by looking for a density of SET tokens + quantity keywords.

**End conditions:** An explicit `END OF SECTION` marker closes a region cleanly. A CSI section number change (e.g. 087100 → 088000) closes it by inference. Regions without either close at EOF.

---

## Stage 2 — Layout (`hardware_sets/layout.py`)

**What it does:** For each page in a schedule region, extracts the text as a numbered list of lines — `L01: SET 1.1`, `L02: 3 EA Heavy Duty Hinge ...` — and attaches a bounding box `(x0, top, x1, bottom)` in PDF-point coordinates to each line.

**Why numbered lines:** The LLM needs a stable addressing scheme to cite where each set lives. Line numbers give it that — it returns `line_range: [4, 12]` and we can map that back unambiguously to the source document. Continuous numbering (no blanks) keeps the count predictable.

**Why pdfplumber instead of pdftotext:** The original implementation used `pdftotext -layout` (Poppler) which produces readable text but throws away geometry. Switching to pdfplumber's word-level extraction preserves `(x0, top, x1, bottom)` for every word, which is required to compute set-level bounding boxes for the PDF viewer overlay. The tradeoff is that pdfplumber reconstructs lines by clustering word coordinates (see `cluster_words_into_lines`) rather than getting them pre-formatted — slightly more code, but no system dependency and bbox support as a first-class output.

---

## Stage 3 — Extract (`hardware_sets/extract.py`)

**What it does:** Sends the numbered page text for a schedule region to Claude and receives back a structured list of `HardwareSet` objects — set number, description, components, and line ranges.

**Why forced tool use:** Tool use with a strict JSON Schema contract guarantees the model's output matches the expected shape. Free-text JSON risks malformed output or missing fields. `tool_choice: {type: "tool", name: "emit_hardware_sets"}` forces the model to respond via the schema — it cannot reply in prose. Every field is marked `required` so the model emits explicit `null`s rather than omitting keys, which lets downstream code distinguish "this field was absent" from "the model didn't address it."

**Why streaming:** Dense schedule regions can produce large outputs. The synchronous Anthropic API has a timeout that streaming bypasses. The pipeline uses `client.messages.stream()` and collects the final message, trading a small amount of complexity for reliability on large documents.

**Prompt caching:** The system prompt is marked `cache_control: ephemeral`. Pays off on multi-region documents; negligible cost on single-region ones. 

**Retry logic:** If the model returns a malformed tool call, the pipeline retries exactly once, appending the validation error as a `NOTE:` in the user message. One retry covers most transient issues without masking systematic prompt problems.

---

## Bbox attachment (`extract.py: attach_bboxes`)

After the LLM returns `line_range` values, `attach_bboxes` resolves each range against the `PageLayout` line bboxes from Stage 2 and computes a union rectangle for the set. This becomes `SetLocation.bbox` — what the frontend uses to position the green overlay on the rendered PDF. It returns `None` defensively if any line in the range lacks a bbox, rather than guessing.

---

## Data flow summary

```
PDF
 │
 ├─ filter.py ──────► [ScheduleRegion, ...]       (which pages?)
 │
 ├─ layout.py ──────► [PageLayout, ...]            (numbered lines + bboxes)
 │
 ├─ extract.py ─────► [HardwareSet, ...]           (structured sets + line ranges)
 │
 └─ attach_bboxes ──► HardwareSet.location.bbox    (pixel coordinates for viewer)
```
