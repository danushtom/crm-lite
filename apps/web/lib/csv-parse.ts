/**
 * CSV parsing for imports (RFC 4180), the counterpart to lib/csv.ts's export.
 *
 * Handles what real exports contain: quoted fields with commas, doubled quotes and line breaks
 * inside them, CRLF or LF, a UTF-8 BOM (Excel adds one), and a semicolon or tab delimiter
 * (Excel in most European locales saves "CSV" with semicolons).
 */

export type ParsedCsv = {
  headers: string[];
  /** Data rows, each padded or trimmed to the header count. */
  rows: string[][];
  delimiter: string;
};

/** The delimiter that splits the first line into the most fields, outside quotes. */
export function detectDelimiter(text: string): string {
  const firstLine: string[] = [];
  let inQuotes = false;
  for (const ch of text) {
    if (ch === '"') inQuotes = !inQuotes;
    else if (!inQuotes && (ch === "\n" || ch === "\r")) break;
    firstLine.push(ch);
  }
  const line = firstLine.join("");
  const count = (d: string) => {
    let n = 0;
    let quoted = false;
    for (const ch of line) {
      if (ch === '"') quoted = !quoted;
      else if (!quoted && ch === d) n += 1;
    }
    return n;
  };
  const candidates = [",", ";", "\t"];
  return candidates.reduce((best, d) => (count(d) > count(best) ? d : best), ",");
}

export function parseCsvRecords(text: string, delimiter = ","): string[][] {
  const records: string[][] = [];
  let record: string[] = [];
  let field = "";
  let inQuotes = false;
  let i = 0;
  const source = text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;

  while (i < source.length) {
    const ch = source[i];
    if (inQuotes) {
      if (ch === '"') {
        if (source[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
      } else {
        field += ch;
      }
      i += 1;
      continue;
    }
    if (ch === '"' && field === "") {
      inQuotes = true;
    } else if (ch === delimiter) {
      record.push(field);
      field = "";
    } else if (ch === "\n" || ch === "\r") {
      record.push(field);
      records.push(record);
      record = [];
      field = "";
      if (ch === "\r" && source[i + 1] === "\n") i += 1;
    } else {
      field += ch;
    }
    i += 1;
  }
  if (field !== "" || record.length) {
    record.push(field);
    records.push(record);
  }
  // Blank lines (often a trailing one) are not rows.
  return records.filter((r) => r.some((cell) => cell.trim() !== ""));
}

export function parseCsv(text: string): ParsedCsv {
  const delimiter = detectDelimiter(text);
  const [head = [], ...body] = parseCsvRecords(text, delimiter);
  const headers = head.map((h, i) => h.trim() || `Column ${i + 1}`);
  const rows = body.map((r) => headers.map((_, i) => (r[i] ?? "").trim()));
  return { headers, rows, delimiter };
}
