/**
 * CSV export for the current view.
 *
 * Written by hand rather than pulled in as a dependency: the only hard part is quoting, and
 * getting that wrong is what makes exports open as one mangled column in Excel.
 */

/** Escape a single cell. */
function cell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return escape(value.join("; "));
  if (typeof value === "object") return escape(JSON.stringify(value));
  return escape(String(value));
}

function escape(text: string): string {
  // A field containing a comma, quote or newline must be quoted, and inner quotes doubled.
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  // Spreadsheets treat a leading =, +, - or @ as a formula. Prefixing breaks that without
  // changing what the reader sees.
  if (/^[=+\-@]/.test(text)) {
    return `"'${text.replace(/"/g, '""')}"`;
  }
  return text;
}

export type CsvColumn<T> = {
  header: string;
  value: (row: T) => unknown;
};

export function toCsv<T>(rows: T[], columns: CsvColumn<T>[]): string {
  const head = columns.map((c) => cell(c.header)).join(",");
  const body = rows.map((row) => columns.map((c) => cell(c.value(row))).join(","));
  // A BOM so Excel reads it as UTF-8 rather than the local codepage, which otherwise
  // mangles any non-ASCII company name.
  return "﻿" + [head, ...body].join("\r\n");
}

export function downloadCsv(filename: string, contents: string) {
  const blob = new Blob([contents], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/** `leads-2026-08-26.csv` */
export function timestampedName(prefix: string): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${prefix}-${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}.csv`;
}
