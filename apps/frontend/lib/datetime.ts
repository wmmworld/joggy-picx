// Claude: Datetime helpers for backend interop
// Backend stores datetimes as TIMESTAMP WITHOUT TIME ZONE (UTC naive).
// Pydantic serializes them without offset (e.g. "2026-05-31T16:43:00").
// We must treat these as UTC explicitly so JavaScript converts to local correctly.

/**
 * Parse a backend datetime string, treating naive timestamps as UTC.
 * Strings with explicit timezone (Z or +offset) are parsed as-is.
 */
export function parseBackendDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  // Already has timezone info — let Date parse normally
  if (value.endsWith("Z") || /[+-]\d{2}:?\d{2}$/.test(value)) {
    return new Date(value);
  }
  // Naive → treat as UTC
  return new Date(value + "Z");
}

/**
 * Format a backend datetime as Thai locale string with Gregorian calendar
 * (fixes "2569 BE" appearing instead of "2026 AD").
 */
export function formatThaiDateTime(value: string | null | undefined): string {
  const d = parseBackendDate(value);
  if (!d) return "—";
  return d.toLocaleString("th-TH-u-ca-gregory", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}
