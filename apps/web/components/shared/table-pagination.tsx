"use client";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  cn,
} from "@dracara/ui";
import { ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";
import { PAGE_SIZE_OPTIONS, pageNumbers } from "@/lib/use-table-controls";

/**
 * The pagination footer shared by every list page. Previously each page rendered a hardcoded
 * `[1,2,3]` with no handlers -- Companies even highlighted page 2 while showing page 1 -- so
 * this exists to make one real implementation rather than three decorative ones.
 */
export function TablePagination({
  page,
  pageCount,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  pageCount: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}) {
  const firstRow = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const lastRow = Math.min(page * pageSize, total);
  const boxClass =
    "inline-flex h-8 items-center justify-center rounded-md border border-border/70 bg-white text-foreground disabled:opacity-40 disabled:pointer-events-none dark:bg-card";

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 px-1 pb-1 pt-2">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>
          Showing {firstRow}&ndash;{lastRow} of {total}
        </span>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className={cn(boxClass, "gap-1 px-2 text-xs font-medium")}>
              {pageSize} per page
              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {PAGE_SIZE_OPTIONS.map((size) => (
              <DropdownMenuItem key={size} onClick={() => onPageSizeChange(size)}>
                {size} per page
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="flex items-center gap-1.5">
        <button
          type="button"
          aria-label="Previous page"
          className={cn(boxClass, "w-8 text-muted-foreground")}
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <ChevronLeft className="h-4 w-4" />
        </button>

        {pageNumbers(page, pageCount).map((n, index) =>
          n === "gap" ? (
            <span key={`gap-${index}`} className="px-1 text-sm text-muted-foreground">
              &hellip;
            </span>
          ) : (
            <button
              key={n}
              type="button"
              aria-current={n === page ? "page" : undefined}
              onClick={() => onPageChange(n)}
              className={cn(
                "inline-flex h-8 w-8 items-center justify-center rounded-md border text-sm",
                n === page
                  ? "border-[#0A1128] bg-[#0A1128] font-semibold text-white"
                  : "border-border/70 bg-white text-foreground dark:bg-card"
              )}
            >
              {n}
            </button>
          )
        )}

        <button
          type="button"
          aria-label="Next page"
          className={cn(boxClass, "w-8 text-muted-foreground")}
          disabled={page >= pageCount}
          onClick={() => onPageChange(page + 1)}
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
