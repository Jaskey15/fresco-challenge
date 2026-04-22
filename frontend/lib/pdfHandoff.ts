// In-memory handoff for the dropped File between landing → /extract.
// Survives client-side navigation (router.push) but not a full page reload.
// Avoids base64 + sessionStorage, which blew the call stack and the 5MB cap.

const store = new Map<string, File>();

export function stashPdf(hash: string, file: File): void {
  store.set(hash, file);
}

export function takePdf(hash: string): File | undefined {
  const file = store.get(hash);
  store.delete(hash);
  return file;
}
