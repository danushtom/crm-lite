"use client";

import { Button } from "@dracara/ui";
import { Upload } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

/** Next to Export in the top bar, on the list pages that can be imported into. */
const IMPORTABLE: Record<string, "leads" | "contacts" | "companies"> = {
  "/leads": "leads",
  "/contacts": "contacts",
  "/companies": "companies",
};

export function ImportButton() {
  const kind = IMPORTABLE[usePathname()];
  if (!kind) return null;
  return (
    <Button asChild size="sm" variant="outline" className="h-9 gap-1 rounded-lg px-3">
      <Link href={`/import?kind=${kind}`} title={`Import ${kind} from a CSV file`}>
        <Upload className="h-3.5 w-3.5" />
        Import
      </Link>
    </Button>
  );
}
