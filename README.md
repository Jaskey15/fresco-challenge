# Hardware Sets — Division 08 Specbook Extractor

Extracts every door-hardware set from a construction Division 08 (Openings)
specbook PDF into structured JSON, including the page + line range where each
set lives.

## Setup

Requires Python 3.12+, Poppler's `pdftotext`, and an Anthropic API key.

```bash
# Poppler on macOS
brew install poppler

# Python deps (uses the repo's .venv)
.venv/bin/pip install -e ".[dev]"

export ANTHROPIC_API_KEY=sk-ant-...
```

## Run

```bash
.venv/bin/python -m hardware_sets path/to/specbook.pdf --out result.json
```

Flags:

| Flag | Default | Purpose |
|---|---|---|
| `pdf_path` | required | PDF to extract from |
| `--out` / `-o` | stdout | Where to write JSON |
| `--model` | `claude-sonnet-4-6` | Anthropic model id |
| `--no-score` | off | Skip vocabulary-match confidence scoring |
| `--quiet` | off | Suppress progress logs |

Exit codes: `0` success, `1` usage error / missing key, `2` no schedule
region found (includes scanned-only PDFs), `3` unrecoverable API error.

## Batch QA

```bash
.venv/bin/python scripts/run_samples.py
```

Runs the extractor against every PDF under `samples/`, writing one JSON per
PDF to `out/<stem>.json` plus `out/_summary.txt`.

## Architecture

Five-module pipeline under `src/hardware_sets/`:

- `filter.py` — locates contiguous schedule region(s) within the PDF (spec §4.1)
- `layout.py` — renders each page as a list of numbered lines via `pdftotext -layout` (§4.2)
- `extract.py` — one prompt-cached Claude Sonnet 4.6 call per region, emitting structured sets through a tool schema (§4.3)
- `resolve.py` — post-hoc vocabulary-match confidence scoring (§4.4). Never auto-corrects.
- `cli.py` — argparse + pipeline + JSON output (§4.5)

`types.py` and `vocab.py` are shared constants.

## Confidence scoring — what it means

A `confidence` field below 1.0 means "this value didn't exactly match our
built-in vocabulary." For finish codes that signal is reliable — BHMA codes
and `USnn[DL]?` patterns are ANSI-standard. For manufacturer short codes it's
weaker: each project uses its own legend (e.g., `IVE` vs `IVES`), so a
confidence below 0.7 on `mfr` could mean "real LLM error" or "legitimate
project-specific abbreviation we haven't seen yet." Review low-confidence
mfr values rather than trusting the drop.

## Tests

```bash
.venv/bin/pytest
```

Two small suites: `tests/test_filter_patterns.py` covers start/end marker
regex, `tests/test_resolve_scoring.py` covers confidence scoring. LLM
behavior is validated by running `scripts/run_samples.py` and eyeballing the
output, per spec §8.
