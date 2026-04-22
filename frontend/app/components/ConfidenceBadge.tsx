"use client";

export function ConfidenceBadge({ value, label }: { value: number | undefined; label: string }) {
  if (value === undefined) return null;
  const color =
    value >= 0.9 ? "bg-cyan" : value >= 0.6 ? "bg-amber-400" : "bg-red-400";
  return (
    <span
      title={`${label} confidence: ${value.toFixed(2)}`}
      className={`inline-block w-1.5 h-1.5 rounded-full ${color} align-middle`}
    />
  );
}
