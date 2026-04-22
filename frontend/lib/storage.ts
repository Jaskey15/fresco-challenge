import type { Correction, HardwareSet } from "./types";

const KEY_PREFIX = "hwsets::";

type Snapshot = {
  corrections: Correction[];
  deletedSets: string[];
  applied: Record<number, HardwareSet>;
  updatedAt: number;
};

export function saveSnapshot(pdfHash: string, snap: Snapshot): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(KEY_PREFIX + pdfHash, JSON.stringify(snap));
  } catch {
    /* quota, private mode, etc. — persistence is best-effort */
  }
}

export function loadSnapshot(pdfHash: string): Snapshot | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(KEY_PREFIX + pdfHash);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Snapshot;
  } catch {
    return null;
  }
}

export function clearSnapshot(pdfHash: string): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(KEY_PREFIX + pdfHash);
}
