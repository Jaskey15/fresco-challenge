#!/usr/bin/env python3
"""Extraction accuracy audit: compare pipeline output against ground truth.

Usage:
    # Extract fresh and audit (costs API calls):
    .venv/bin/python scripts/confidence_audit.py --extract

    # Audit using cached extraction results:
    .venv/bin/python scripts/confidence_audit.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "demo_samples"
GT_DIR = DEMO_DIR / "ground_truth"
CACHE_DIR = DEMO_DIR / "extracted"

DEMOS = [
    ("roselle_demo.pdf", "roselle_demo.json"),
    ("morris_bank_demo.pdf", "morris_bank_demo.json"),
    ("SJC_Div_demo.pdf", "SJC_Div_demo.json"),
]

SCORED_FIELDS = ["qty", "description", "catalog_number", "mfr", "finish"]


def normalize(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    return " ".join(str(value).strip().lower().split())


def fields_match(extracted, truth):
    e = normalize(extracted)
    t = normalize(truth)
    if e is None and t is None:
        return True
    if e is None or t is None:
        return False
    return e == t


def run_extraction(pdf_path: Path, model: str | None = None) -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    from hardware_sets_api.pipeline import run_pipeline

    def progress(msg):
        print(f"  {msg['phase']}: {msg['message']}", file=sys.stderr)

    return run_pipeline(pdf_path, on_progress=progress, model=model)


def load_json(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def match_components(ext_comps, gt_comps):
    """Match extracted components to ground truth by description similarity.

    Returns list of (ext_index, gt_index) pairs.
    Falls back to positional matching when descriptions diverge.
    """
    pairs = []
    used_gt = set()

    for ei, ec in enumerate(ext_comps):
        e_desc = normalize(ec.get("description"))
        best_gi = None
        best_score = 0

        for gi, gc in enumerate(gt_comps):
            if gi in used_gt:
                continue
            g_desc = normalize(gc.get("description"))
            if e_desc and g_desc and e_desc == g_desc:
                best_gi = gi
                best_score = 2
                break
            if e_desc and g_desc:
                e_words = set(e_desc.split())
                g_words = set(g_desc.split())
                overlap = len(e_words & g_words)
                if overlap > best_score:
                    best_score = overlap
                    best_gi = gi

        if best_gi is not None and best_score > 0:
            pairs.append((ei, best_gi))
            used_gt.add(best_gi)
        elif ei < len(gt_comps) and ei not in used_gt:
            pairs.append((ei, ei))
            used_gt.add(ei)

    return pairs


def audit_one(extracted_sets, gt_sets, pdf_name):
    results = []
    gt_by_num = {}
    for s in gt_sets:
        key = normalize(s["set_number"])
        gt_by_num[key] = s

    matched_gt = set()
    for ext_set in extracted_sets:
        set_num = normalize(ext_set["set_number"])
        gt_set = gt_by_num.get(set_num)
        if gt_set is None:
            continue
        matched_gt.add(set_num)

        ext_comps = ext_set.get("components", [])
        gt_comps = gt_set.get("components", [])
        pairs = match_components(ext_comps, gt_comps)

        for ei, gi in pairs:
            ext_comp = ext_comps[ei]
            gt_comp = gt_comps[gi]

            for field in SCORED_FIELDS:
                ext_val = ext_comp.get(field)
                gt_val = gt_comp.get(field)
                correct = fields_match(ext_val, gt_val)

                results.append({
                    "pdf": pdf_name,
                    "set": ext_set["set_number"],
                    "field": field,
                    "extracted": ext_val,
                    "truth": gt_val,
                    "correct": correct,
                })

    missing_gt = set(gt_by_num.keys()) - matched_gt
    extra_ext = set()
    for s in extracted_sets:
        key = normalize(s["set_number"])
        if key not in gt_by_num:
            extra_ext.add(s["set_number"])

    return results, missing_gt, extra_ext


def print_report(all_results, all_missing, all_extra):
    total = len(all_results)
    if total == 0:
        print("No fields to evaluate.")
        return

    correct_count = sum(1 for r in all_results if r["correct"])
    incorrect_count = total - correct_count

    print(f"\n{'=' * 60}")
    print(f"  EXTRACTION ACCURACY REPORT")
    print(f"{'=' * 60}")
    print(f"  Total fields evaluated:  {total}")
    print(f"  Extraction accuracy:     {correct_count / total * 100:.1f}%  ({correct_count}/{total})")
    print(f"  Incorrect fields:        {incorrect_count}")

    if all_missing:
        print(f"\n  Missing sets (in GT but not extracted): {all_missing}")
    if all_extra:
        print(f"  Extra sets (extracted but not in GT):    {all_extra}")

    print(f"\n  Per-field breakdown:")
    print(f"  {'Field':20s} {'Accuracy':>10s} {'Errors':>10s}")
    print(f"  {'-' * 42}")
    for field in SCORED_FIELDS:
        fr = [r for r in all_results if r["field"] == field]
        c = sum(1 for r in fr if r["correct"])
        e = sum(1 for r in fr if not r["correct"])
        acc = f"{c}/{len(fr)}"
        print(f"  {field:20s} {acc:>10s} {e:>10d}")

    print(f"\n  Per-PDF breakdown:")
    print(f"  {'PDF':30s} {'Fields':>8s} {'Correct':>10s} {'Errors':>10s}")
    print(f"  {'-' * 52}")
    for pdf in dict.fromkeys(r["pdf"] for r in all_results):
        pr = [r for r in all_results if r["pdf"] == pdf]
        c = sum(1 for r in pr if r["correct"])
        e = sum(1 for r in pr if not r["correct"])
        print(f"  {pdf:30s} {len(pr):>8d} {c:>10d} {e:>10d}")

    errors = [r for r in all_results if not r["correct"]]
    if errors:
        print(f"\n  All extraction errors ({len(errors)}):")
        print(f"  {'-' * 52}")
        for r in errors:
            print(f"  {r['pdf']}  Set {r['set']}  .{r['field']}")
            print(f"           extracted: {r['extracted']}")
            print(f"           truth:     {r['truth']}")
            print()


def main():
    parser = argparse.ArgumentParser(description="Audit extraction accuracy against ground truth")
    parser.add_argument("--extract", action="store_true", help="Run extraction (costs API calls)")
    parser.add_argument("--model", default=None, help="Anthropic model id (default: extractor default)")
    args = parser.parse_args()

    CACHE_DIR.mkdir(exist_ok=True)

    all_results = []
    all_missing = set()
    all_extra = set()

    for pdf_name, gt_name in DEMOS:
        pdf_path = DEMO_DIR / pdf_name
        gt_path = GT_DIR / gt_name
        cache_path = CACHE_DIR / gt_name

        if not gt_path.exists():
            print(f"SKIP {pdf_name}: no ground truth at {gt_path}", file=sys.stderr)
            continue

        if args.extract or not cache_path.exists():
            if not pdf_path.exists():
                print(f"SKIP {pdf_name}: PDF not found", file=sys.stderr)
                continue
            print(f"Extracting {pdf_name}...", file=sys.stderr)
            result = run_extraction(pdf_path, model=args.model)
            cache_path.write_text(json.dumps(result, indent=2, default=str) + "\n")
            extracted_sets = result["hardware_sets"]
        else:
            print(f"Using cached {cache_path.name}", file=sys.stderr)
            data = load_json(cache_path)
            if isinstance(data, dict):
                extracted_sets = data.get("hardware_sets", [])
            else:
                extracted_sets = data

        gt_sets = load_json(gt_path)
        results, missing, extra = audit_one(extracted_sets, gt_sets, pdf_name)
        all_results.extend(results)
        all_missing.update(missing)
        all_extra.update(extra)

    print_report(all_results, all_missing, all_extra)


if __name__ == "__main__":
    main()
