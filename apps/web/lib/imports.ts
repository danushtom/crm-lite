/** CSV import: the field catalog's types, column auto-mapping, and batching. Pure. */

import { toCsv } from "@/lib/csv";

export type ImportKind = "companies" | "contacts" | "leads";

export type ImportField = {
  key: string;
  label: string;
  required: boolean;
  aliases: string[];
  help: string;
};

export type ImportCatalog = {
  kinds: Record<ImportKind, ImportField[]>;
  max_rows_per_request: number;
};

export type ImportRowResult = {
  row_number: number;
  status: "created" | "existing" | "skipped" | "error";
  record_id: string | null;
  message: string | null;
  warnings: string[];
};

export type ImportResult = {
  kind: ImportKind;
  created: number;
  existing: number;
  skipped: number;
  failed: number;
  rows: ImportRowResult[];
};

/** field key -> column index in the file, or -1 for "not imported". */
export type ColumnMapping = Record<string, number>;

export const MAX_IMPORT_ROWS = 10_000;
export const MAX_IMPORT_BYTES = 10 * 1024 * 1024;

const normalizeHeader = (header: string) =>
  header
    .toLowerCase()
    .replace(/[_\-]+/g, " ")
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();

/**
 * Pre-map each field to the column whose header matches one of its aliases. Each column is
 * used at most once, in field order, so "Name" goes to the first field that claims it.
 */
export function autoMap(headers: string[], fields: ImportField[]): ColumnMapping {
  const normalized = headers.map(normalizeHeader);
  const taken = new Set<number>();
  const mapping: ColumnMapping = {};
  for (const field of fields) {
    const candidates = [field.key.replace(/_/g, " "), field.label, ...field.aliases].map(normalizeHeader);
    const index = normalized.findIndex((h, i) => !taken.has(i) && candidates.includes(h));
    mapping[field.key] = index;
    if (index >= 0) taken.add(index);
  }
  return mapping;
}

/** Required fields with no column mapped. Contacts and leads also need some way to name a person. */
export function missingRequired(fields: ImportField[], mapping: ColumnMapping, kind: ImportKind): string[] {
  const missing = fields.filter((f) => f.required && (mapping[f.key] ?? -1) < 0).map((f) => f.label);
  if (kind === "contacts") {
    const hasPerson = ["full_name", "first_name", "last_name", "email"].some((k) => (mapping[k] ?? -1) >= 0);
    if (!hasPerson) missing.push("a name or email column");
  }
  return missing;
}

export type ImportRow = { row_number: number; values: Record<string, string | null> };

/**
 * Undo lib/csv.ts's formula-injection guard ("'+91 98..." -> "+91 98..."), so a failed-rows
 * file downloaded from here re-imports cleanly. Only that exact shape is touched.
 */
function cleanCell(value: string | undefined): string | null {
  if (!value) return null;
  return value.replace(/^'(?=[=+\-@])/, "");
}

/** File rows -> API rows. `row_number` is the line in the file (the header is line 1). */
export function buildRows(rows: string[][], mapping: ColumnMapping): ImportRow[] {
  const mapped = Object.entries(mapping).filter(([, index]) => index >= 0);
  return rows.map((row, i) => ({
    row_number: i + 2,
    values: Object.fromEntries(mapped.map(([key, index]) => [key, cleanCell(row[index])])),
  }));
}

export function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

/**
 * The rows that failed, exactly as they were in the file plus an "Import error" column -- fix
 * them in a spreadsheet and upload this file again. Re-importing is safe: rows that already
 * went in are matched, not duplicated.
 */
export function failedRowsCsv(headers: string[], rows: string[][], results: ImportRowResult[]): string {
  const failed = results.filter((r) => r.status === "error");
  return toCsv(failed, [
    ...headers.map((header, index) => ({ header, value: (r: ImportRowResult) => rows[r.row_number - 2]?.[index] ?? "" })),
    { header: "Import error", value: (r: ImportRowResult) => r.message ?? "" },
  ]);
}
