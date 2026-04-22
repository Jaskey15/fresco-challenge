// Mirrors Python dataclasses in src/hardware_sets/types.py. Hand-maintained for v1.

export type BBox = [number, number, number, number]; // (x0, top, x1, bottom), PDF points

export interface SetLocation {
  page: number;
  line_range: [number, number];
  bbox: BBox | null;
}

export interface Component {
  qty: number | null;
  description: string | null;
  catalog_number: string | null;
  mfr: string | null;
  finish: string | null;
  notes: string | null;
  confidence: { mfr?: number; finish?: number; qty?: number };
}

export interface HardwareSet {
  set_number: string;
  description: string | null;
  location: SetLocation;
  components: Component[];
  continued_on: SetLocation[];
  is_not_used: boolean;
  confidence: number;
  notes: string | null;
}

// SSE events ------------------------------------------------------------

export type SseEvent =
  | { event: "session_started"; data: { session_id: string; filename: string } }
  | { event: "region_found"; data: { page_start: number; page_end: number; marker: string } }
  | { event: "extracting"; data: { region_index: number; total_regions: number; page_start: number; page_end: number } }
  | { event: "set_extracted"; data: HardwareSet }
  | { event: "scored"; data: { set_index: number; confidence: number } }
  | { event: "warning"; data: { message: string } }
  | { event: "done"; data: { total_sets: number; llm_calls: number; warnings: string[] } }
  | { event: "error"; data: { code: "scanned_pdf" | "no_schedule" | "api_error" | "parse_error"; message: string } };

export type EditableField = "qty" | "description" | "catalog_number" | "mfr" | "finish" | "notes";

export type Correction =
  | { type: "field"; set_number: string; component_index: number; field: EditableField; before: unknown; after: unknown }
  | { type: "delete_set"; set_number: string }
  | { type: "add_component"; set_number: string; component_index: number }
  | { type: "remove_component"; set_number: string; component_index: number };
