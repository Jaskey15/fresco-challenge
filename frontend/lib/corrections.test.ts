import { describe, expect, it } from "vitest";
import { buildExport, normalizeCorrections } from "./corrections";
import type { Correction, HardwareSet } from "./types";

const baseSet: HardwareSet = {
  set_number: "1.1",
  description: "RECEPTION",
  location: { page: 40, line_range: [12, 26], bbox: null },
  components: [
    {
      qty: 1, description: "HINGE", catalog_number: "ABC", mfr: "IVE", finish: "630", notes: null,
      confidence: { mfr: 1.0, finish: 1.0, qty: 1.0 },
    },
  ],
  continued_on: [],
  is_not_used: false,
  confidence: 1.0,
  notes: null,
};

describe("normalizeCorrections", () => {
  it("collapses multiple edits of the same field to one before/after", () => {
    const raw: Correction[] = [
      { type: "field", set_number: "1.1", component_index: 0, field: "mfr", before: "IVE", after: "IVS" },
      { type: "field", set_number: "1.1", component_index: 0, field: "mfr", before: "IVS", after: "IVES" },
    ];
    const out = normalizeCorrections(raw);
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({
      type: "field", set_number: "1.1", component_index: 0, field: "mfr", before: "IVE", after: "IVES",
    });
  });

  it("drops field edits that revert to the original value", () => {
    const raw: Correction[] = [
      { type: "field", set_number: "1.1", component_index: 0, field: "mfr", before: "IVE", after: "IVS" },
      { type: "field", set_number: "1.1", component_index: 0, field: "mfr", before: "IVS", after: "IVE" },
    ];
    expect(normalizeCorrections(raw)).toHaveLength(0);
  });

  it("keeps delete_set, add_component, remove_component unchanged", () => {
    const raw: Correction[] = [
      { type: "delete_set", set_number: "1.1" },
      { type: "add_component", set_number: "1.1", component_index: 3 },
      { type: "remove_component", set_number: "1.1", component_index: 2 },
    ];
    expect(normalizeCorrections(raw)).toHaveLength(3);
  });
});

describe("buildExport", () => {
  it("wraps applied sets with corrections diff and metadata", () => {
    const corrections: Correction[] = [
      { type: "field", set_number: "1.1", component_index: 0, field: "mfr", before: "IVE", after: "IVES" },
    ];
    const applied: HardwareSet[] = [
      { ...baseSet, components: [{ ...baseSet.components[0], mfr: "IVES" }] },
    ];
    const out = buildExport({
      sourceFilename: "t.pdf",
      appliedSets: applied,
      corrections,
      extractedAt: "2026-04-21T19:30:00Z",
    });
    expect(out).toMatchObject({
      source_pdf: "t.pdf",
      extracted_at: "2026-04-21T19:30:00Z",
      hardware_sets: applied,
      corrections,
    });
  });
});
