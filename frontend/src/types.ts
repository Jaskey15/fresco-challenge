export interface NumberedLine {
  number: number;
  text: string;
  bbox: [number, number, number, number];
}

export interface PageLayout {
  lines: NumberedLine[];
  page_width: number;
  page_height: number;
}

export interface SetLocation {
  page: number;
  line_range: [number, number];
  bbox: [number, number, number, number] | null;
}

export interface Component {
  qty: number | null;
  description: string | null;
  catalog_number: string | null;
  mfr: string | null;
  finish: string | null;
  notes: string | null;
  confidence?: Record<string, { score: number; reason: string | null }>;
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

export interface ExtractionResult {
  source_pdf: string;
  hardware_sets: HardwareSet[];
  page_layouts: Record<string, PageLayout>;
  session_id: string;
  diagnostics: {
    pages_scanned: number;
    regions_found: number;
    pages_with_sets: number;
    llm_calls: number;
    warnings: string[];
  };
}

export interface ProgressEvent {
  phase: "filter" | "extract";
  message: string;
}

export interface Sample {
  id: string;
  name: string;
  label: string;
}
