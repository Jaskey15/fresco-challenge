import type { Correction, EditableField, HardwareSet } from "./types";

/**
 * Coalesce repeated edits of the same `(set, component, field)` into a
 * single before/after. Drop edits that revert to the original.
 */
export function normalizeCorrections(raw: Correction[]): Correction[] {
  type Key = string;
  const firstBefore = new Map<Key, unknown>();
  const lastAfter = new Map<Key, unknown>();
  const ordered = new Map<Key, { set_number: string; component_index: number; field: EditableField }>();
  const nonField: Correction[] = [];

  for (const c of raw) {
    if (c.type !== "field") {
      nonField.push(c);
      continue;
    }
    const key = `${c.set_number}::${c.component_index}::${c.field}`;
    if (!firstBefore.has(key)) {
      firstBefore.set(key, c.before);
      ordered.set(key, { set_number: c.set_number, component_index: c.component_index, field: c.field });
    }
    lastAfter.set(key, c.after);
  }

  const fieldOut: Correction[] = [];
  for (const [key, meta] of ordered) {
    const before = firstBefore.get(key);
    const after = lastAfter.get(key);
    if (before === after) continue;
    fieldOut.push({ type: "field", ...meta, before, after });
  }

  return [...fieldOut, ...nonField];
}

export function buildExport(opts: {
  sourceFilename: string;
  appliedSets: HardwareSet[];
  corrections: Correction[];
  extractedAt: string;
}) {
  return {
    source_pdf: opts.sourceFilename,
    extracted_at: opts.extractedAt,
    hardware_sets: opts.appliedSets,
    corrections: normalizeCorrections(opts.corrections),
  };
}
