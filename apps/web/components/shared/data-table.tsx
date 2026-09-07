"use client";

import {
  Card,
  CardContent,
  Skeleton,
  cn,
  tableBodyRow,
  tableCell,
  tableHeadRow,
} from "@dracara/ui";
import { ChevronsUpDown } from "lucide-react";
import type { ReactNode } from "react";
import type { SortDirection } from "@/lib/use-table-controls";

export type Column<Row, Key extends string = string> = {
  /** Stable React key for the column. */
  key: string;
  header: ReactNode;
  /**
   * Set to make the header a sort control; the value is handed back to `onSort`. Omit for
   * columns that cannot be ordered (actions, derived links) -- kept separate from `key` so an
   * actions column does not have to be cast into the sort-key union.
   */
  sortKey?: Key;
  cell: (row: Row) => ReactNode;
  /** Extra classes for this column's `td`. */
  className?: string;
  /** Skeleton width while loading, e.g. "w-32". */
  skeletonWidth?: string;
};

/**
 * The app's one table. Before this, Contacts, Companies, Leads, Opportunities, Agents and the
 * voice-agent call log each had their own header/row/loading treatment -- different paddings,
 * different border opacities, and only Contacts had working sort or a skeleton state.
 *
 * Rows are expected to be already sorted and paged by the caller (these pages load the full
 * collection via `apiListAll`); this component owns presentation and the sort affordance only.
 */
export function DataTable<Row extends { id: string }, Key extends string = string>({
  rows,
  columns,
  isLoading,
  error,
  emptyMessage = "Nothing here yet.",
  sortKey,
  sortDirection,
  onSort,
  minWidth = "min-w-[920px]",
  skeletonRows = 5,
}: {
  rows: Row[];
  columns: Column<Row, Key>[];
  isLoading?: boolean;
  error?: Error | null;
  emptyMessage?: string;
  sortKey?: Key;
  sortDirection?: SortDirection;
  onSort?: (key: Key) => void;
  minWidth?: string;
  skeletonRows?: number;
}) {
  return (
    <Card>
      <CardContent className="overflow-x-auto px-3 py-2">
        {error ? (
          <p className="py-4 text-sm text-destructive">{error.message}</p>
        ) : isLoading ? (
          <table className={cn("w-full border-collapse text-sm", minWidth)}>
            <thead>
              <tr className={tableHeadRow}>
                {columns.map((col) => (
                  <th key={col.key} className={tableCell}>
                    {col.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: skeletonRows }).map((_, i) => (
                <tr key={i} className="border-b border-border/50">
                  {columns.map((col) => (
                    <td key={col.key} className={tableCell}>
                      <Skeleton className={cn("h-4", col.skeletonWidth ?? "w-24")} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : rows.length === 0 ? (
          <p className="py-4 text-sm text-muted-foreground">{emptyMessage}</p>
        ) : (
          <table className={cn("w-full border-collapse text-sm", minWidth)}>
            <thead>
              <tr className={tableHeadRow}>
                {columns.map((col) => {
                  const columnSortKey = col.sortKey;
                  const isSortable = Boolean(columnSortKey && onSort);
                  const isActive = isSortable && sortKey === columnSortKey;
                  return (
                    <th
                      key={col.key}
                      className={cn(tableCell, isSortable && "cursor-pointer hover:text-foreground")}
                      onClick={
                        isSortable && columnSortKey ? () => onSort?.(columnSortKey) : undefined
                      }
                      aria-sort={
                        isActive ? (sortDirection === "asc" ? "ascending" : "descending") : undefined
                      }
                    >
                      <div className="inline-flex items-center gap-1.5">
                        {col.header}
                        {isSortable ? (
                          <ChevronsUpDown
                            className={cn("h-3 w-3", isActive && "text-foreground")}
                          />
                        ) : null}
                      </div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr
                  key={row.id}
                  className={tableBodyRow}
                  style={{ animationDelay: `${index * 50}ms` }}
                >
                  {columns.map((col) => (
                    <td key={col.key} className={cn(tableCell, col.className)}>
                      {col.cell(row)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
