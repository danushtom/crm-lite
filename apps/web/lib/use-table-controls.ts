"use client";

import { useMemo, useState } from "react";

export type SortDirection = "asc" | "desc";

/**
 * Client-side sort state for a table whose rows are already fully loaded (these list pages
 * fetch via `apiListAll`, so sorting and paging happen in the browser rather than as query
 * params). Clicking the active column flips direction; clicking a new one selects it.
 */
export function useSort<K extends string>(defaultKey: K, defaultDirection: SortDirection = "asc") {
  const [sortKey, setSortKey] = useState<K>(defaultKey);
  const [sortDirection, setSortDirection] = useState<SortDirection>(defaultDirection);

  const toggleSort = (key: K) => {
    if (key === sortKey) {
      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDirection("asc");
  };

  return { sortKey, sortDirection, toggleSort, setSortKey, setSortDirection };
}

/** Compare two cell values, keeping numbers numeric and strings case-insensitive. */
export function compareValues(a: unknown, b: unknown, direction: SortDirection): number {
  const factor = direction === "asc" ? 1 : -1;

  // Null/undefined always sort last, regardless of direction: an empty cell is not "smallest",
  // it is absent, and burying it under a descending sort hides real rows.
  const aMissing = a === null || a === undefined || a === "";
  const bMissing = b === null || b === undefined || b === "";
  if (aMissing && bMissing) return 0;
  if (aMissing) return 1;
  if (bMissing) return -1;

  if (typeof a === "number" && typeof b === "number") return (a - b) * factor;

  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" }) * factor;
}

export const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const;

/**
 * Slices already-loaded rows into pages. `page` is clamped rather than stored blindly, so
 * filtering a list down while on page 4 shows the last real page instead of an empty table.
 */
export function usePagination<T>(rows: T[], initialPageSize = 10) {
  const [pageSize, setPageSize] = useState<number>(initialPageSize);
  const [requestedPage, setRequestedPage] = useState(1);

  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const page = Math.min(Math.max(1, requestedPage), pageCount);

  const pageRows = useMemo(
    () => rows.slice((page - 1) * pageSize, page * pageSize),
    [rows, page, pageSize]
  );

  return {
    page,
    pageCount,
    pageSize,
    pageRows,
    total: rows.length,
    setPage: setRequestedPage,
    setPageSize: (size: number) => {
      setPageSize(size);
      setRequestedPage(1);
    },
  };
}

/**
 * Which page numbers to render. Collapses to a leading/trailing window with ellipses once
 * there are more pages than fit, so a 40-page list does not render 40 buttons.
 */
export function pageNumbers(page: number, pageCount: number): (number | "gap")[] {
  if (pageCount <= 7) return Array.from({ length: pageCount }, (_, i) => i + 1);

  const pages: (number | "gap")[] = [1];
  const start = Math.max(2, page - 1);
  const end = Math.min(pageCount - 1, page + 1);

  if (start > 2) pages.push("gap");
  for (let n = start; n <= end; n += 1) pages.push(n);
  if (end < pageCount - 1) pages.push("gap");
  pages.push(pageCount);

  return pages;
}
