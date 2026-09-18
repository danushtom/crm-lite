"use client";

import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Skeleton, cn } from "@dracara/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, Building2, CheckCircle2, FileUp, Loader2, Target, UsersRound } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useRef, useState } from "react";
import { ApiError, apiFetch } from "@/lib/api";
import { downloadCsv, timestampedName, toCsv } from "@/lib/csv";
import { parseCsv } from "@/lib/csv-parse";
import {
  MAX_IMPORT_BYTES,
  MAX_IMPORT_ROWS,
  autoMap,
  buildRows,
  chunk,
  failedRowsCsv,
  missingRequired,
  type ColumnMapping,
  type ImportCatalog,
  type ImportKind,
  type ImportResult,
  type ImportRowResult,
} from "@/lib/imports";
import { selectClass } from "@/components/shared/entity-drawer";
import { describeError } from "@/lib/use-api-mutation";

const KINDS: { kind: ImportKind; title: string; blurb: string; icon: typeof Building2; href: string }[] = [
  { kind: "leads", title: "Leads", blurb: "Deals with their company and contact. Stage, value and owner optional.", icon: Target, href: "/leads" },
  { kind: "contacts", title: "Contacts", blurb: "People, each at a company. Companies are created as needed.", icon: UsersRound, href: "/contacts" },
  { kind: "companies", title: "Companies", blurb: "Accounts on their own: website, industry, size, location.", icon: Building2, href: "/companies" },
];

type Loaded = { fileName: string; headers: string[]; rows: string[][] };
type Stage =
  | { step: "upload" }
  | { step: "map" }
  | { step: "importing"; done: number; total: number }
  | { step: "finished"; stoppedBecause?: string };

export default function ImportPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64 w-full max-w-4xl" />}>
      <ImportWizard />
    </Suspense>
  );
}

function ImportWizard() {
  const params = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const initial = KINDS.find((k) => k.kind === params.get("kind"))?.kind ?? "leads";
  const [kind, setKind] = useState<ImportKind>(initial);
  const [stage, setStage] = useState<Stage>({ step: "upload" });
  const [file, setFile] = useState<Loaded | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [mapping, setMapping] = useState<ColumnMapping>({});
  const [results, setResults] = useState<ImportRowResult[]>([]);
  const cancelled = useRef(false);

  const { data: catalog, isLoading } = useQuery({
    queryKey: ["import-fields"],
    queryFn: () => apiFetch<ImportCatalog>("/imports/fields"),
    staleTime: Infinity,
  });
  const fields = catalog?.kinds[kind] ?? [];
  const meta = KINDS.find((k) => k.kind === kind)!;

  function chooseKind(next: ImportKind) {
    setKind(next);
    router.replace(`/import?kind=${next}`);
    if (file && catalog) setMapping(autoMap(file.headers, catalog.kinds[next]));
  }

  async function onFile(picked: File | undefined) {
    setFileError(null);
    if (!picked || !catalog) return;
    if (picked.size > MAX_IMPORT_BYTES) {
      setFileError(`That file is over ${MAX_IMPORT_BYTES / 1024 / 1024} MB. Split it into smaller files.`);
      return;
    }
    const parsed = parseCsv(await picked.text());
    if (!parsed.rows.length) {
      setFileError("That file has a header row but no data rows.");
      return;
    }
    if (parsed.rows.length > MAX_IMPORT_ROWS) {
      setFileError(`That file has ${parsed.rows.length.toLocaleString()} rows; the limit is ${MAX_IMPORT_ROWS.toLocaleString()} per file. Split it and import each part.`);
      return;
    }
    setFile({ fileName: picked.name, headers: parsed.headers, rows: parsed.rows });
    setMapping(autoMap(parsed.headers, catalog.kinds[kind]));
    setStage({ step: "map" });
  }

  async function runImport() {
    if (!file || !catalog) return;
    const batches = chunk(buildRows(file.rows, mapping), catalog.max_rows_per_request);
    const collected: ImportRowResult[] = [];
    cancelled.current = false;
    setResults([]);
    setStage({ step: "importing", done: 0, total: file.rows.length });
    for (const batch of batches) {
      if (cancelled.current) {
        setStage({ step: "finished", stoppedBecause: "You stopped the import. Rows after this point were not imported." });
        break;
      }
      try {
        const result = await apiFetch<ImportResult>(`/imports/${kind}`, {
          method: "POST",
          body: JSON.stringify({ rows: batch }),
        });
        collected.push(...result.rows);
        setResults([...collected]);
        setStage({ step: "importing", done: collected.length, total: file.rows.length });
      } catch (err) {
        const reason =
          err instanceof ApiError && err.status === 402
            ? `${err.message}`
            : `The import stopped: ${describeError(err)}. Rows imported so far are saved; import the file again to finish (rows already in are matched, not duplicated).`;
        setStage({ step: "finished", stoppedBecause: reason });
        qc.invalidateQueries();
        return;
      }
    }
    qc.invalidateQueries();
    setStage((s) => (s.step === "finished" ? s : { step: "finished" }));
  }

  function reset() {
    setFile(null);
    setResults([]);
    setMapping({});
    setStage({ step: "upload" });
  }

  return (
    <div className="max-w-4xl space-y-6">
      <div className="space-y-1">
        <Link href={meta.href} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-3.5 w-3.5" /> {meta.title}
        </Link>
        <h1 className="text-xl font-semibold tracking-tight">Import from CSV</h1>
        <p className="text-sm text-muted-foreground">
          Export from your old CRM or spreadsheet as CSV, then map its columns here. Existing companies,
          contacts and leads are matched rather than duplicated, so it is safe to import a file twice.
        </p>
      </div>

      {stage.step === "upload" ? (
        <>
          <div className="grid gap-3 sm:grid-cols-3" role="radiogroup" aria-label="What are you importing?">
            {KINDS.map(({ kind: k, title, blurb, icon: Icon }) => (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={kind === k}
                onClick={() => chooseKind(k)}
                className={cn(
                  "rounded-xl border bg-card p-4 text-left transition hover:border-[hsl(var(--primary))]",
                  kind === k ? "border-[hsl(var(--primary))] ring-1 ring-[hsl(var(--primary))]" : "border-border"
                )}
              >
                <Icon className="mb-2 h-5 w-5 text-muted-foreground" aria-hidden />
                <p className="font-medium">{title}</p>
                <p className="mt-1 text-xs text-muted-foreground">{blurb}</p>
              </button>
            ))}
          </div>

          <Card>
            <CardContent className="py-6">
              {isLoading ? (
                <Skeleton className="h-32 w-full" />
              ) : (
                <label
                  htmlFor="csv-file"
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    void onFile(e.dataTransfer.files[0]);
                  }}
                  className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border px-6 py-10 text-center hover:bg-muted/40"
                >
                  <FileUp className="h-8 w-8 text-muted-foreground" aria-hidden />
                  <span className="font-medium">Drop a CSV file here, or click to choose one</span>
                  <span className="text-xs text-muted-foreground">
                    Up to {MAX_IMPORT_ROWS.toLocaleString()} rows. Saving from Excel or Google Sheets? Choose “CSV (UTF-8)”.
                  </span>
                  <input
                    id="csv-file"
                    type="file"
                    accept=".csv,text/csv"
                    className="sr-only"
                    onChange={(e) => {
                      void onFile(e.target.files?.[0]);
                      e.target.value = "";
                    }}
                  />
                </label>
              )}
              {fileError ? <p className="mt-3 text-sm text-destructive">{fileError}</p> : null}
              <p className="mt-4 text-center text-xs text-muted-foreground">
                Starting from scratch?{" "}
                <button
                  type="button"
                  className="underline underline-offset-4 hover:text-foreground"
                  onClick={() =>
                    downloadCsv(
                      `${kind}-import-template.csv`,
                      toCsv<null>([], fields.map((f) => ({ header: f.label, value: () => "" })))
                    )
                  }
                >
                  Download a {meta.title.toLowerCase()} template
                </button>
              </p>
            </CardContent>
          </Card>
        </>
      ) : null}

      {stage.step === "map" && file ? (
        <MappingStep
          kindTitle={meta.title}
          file={file}
          fields={fields}
          mapping={mapping}
          missing={missingRequired(fields, mapping, kind)}
          onChange={(key, index) => setMapping((m) => ({ ...m, [key]: index }))}
          onBack={reset}
          onImport={runImport}
        />
      ) : null}

      {stage.step === "importing" ? (
        <Card>
          <CardContent className="space-y-3 py-6">
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 font-medium">
                <Loader2 className="h-4 w-4 animate-spin" /> Importing {meta.title.toLowerCase()}…
              </span>
              <span className="tabular-nums text-muted-foreground">
                {stage.done.toLocaleString()} / {stage.total.toLocaleString()}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-[hsl(var(--primary))] transition-all"
                style={{ width: `${Math.round((stage.done / Math.max(1, stage.total)) * 100)}%` }}
              />
            </div>
            <Button variant="outline" size="sm" onClick={() => (cancelled.current = true)}>
              Stop after this batch
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {stage.step === "finished" && file ? (
        <ResultsStep
          kindTitle={meta.title}
          href={meta.href}
          file={file}
          results={results}
          stoppedBecause={stage.stoppedBecause}
          onAgain={reset}
        />
      ) : null}
    </div>
  );
}

function MappingStep({
  kindTitle,
  file,
  fields,
  mapping,
  missing,
  onChange,
  onBack,
  onImport,
}: {
  kindTitle: string;
  file: Loaded;
  fields: ImportCatalog["kinds"][ImportKind];
  mapping: ColumnMapping;
  missing: string[];
  onChange: (key: string, index: number) => void;
  onBack: () => void;
  onImport: () => void;
}) {
  const sample = useMemo(
    () => file.headers.map((_, i) => file.rows.find((r) => r[i])?.[i] ?? ""),
    [file]
  );
  const unmapped = file.headers.filter((_, i) => !Object.values(mapping).includes(i));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Match your columns</CardTitle>
        <CardDescription>
          {file.fileName} · {file.rows.length.toLocaleString()} rows. We matched what we could from the headers; check
          each field and pick a column for anything we missed.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="py-2 pr-3 font-medium">{kindTitle} field</th>
                <th className="py-2 pr-3 font-medium">Column in your file</th>
                <th className="py-2 font-medium">Example</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((field) => {
                const index = mapping[field.key] ?? -1;
                return (
                  <tr key={field.key} className="border-b border-border/60 align-top">
                    <td className="py-2 pr-3">
                      <label htmlFor={`map-${field.key}`} className="font-medium">
                        {field.label}
                        {field.required ? <span className="text-destructive"> *</span> : null}
                      </label>
                      {field.help ? <p className="text-xs text-muted-foreground">{field.help}</p> : null}
                    </td>
                    <td className="py-2 pr-3">
                      <select
                        id={`map-${field.key}`}
                        className={cn(selectClass, "min-w-44")}
                        value={index}
                        onChange={(e) => onChange(field.key, Number(e.target.value))}
                      >
                        <option value={-1}>— Don&apos;t import —</option>
                        {file.headers.map((header, i) => (
                          <option key={i} value={i}>
                            {header}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="max-w-56 truncate py-2 text-muted-foreground" title={index >= 0 ? sample[index] : ""}>
                      {index >= 0 ? sample[index] || <span className="italic">empty</span> : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {unmapped.length ? (
          <p className="text-xs text-muted-foreground">
            Not imported: {unmapped.join(", ")}
          </p>
        ) : null}
        {missing.length ? (
          <p className="flex items-center gap-2 text-sm text-destructive">
            <AlertTriangle className="h-4 w-4" /> Map {missing.join(" and ")} to continue.
          </p>
        ) : null}

        <div className="flex flex-wrap justify-between gap-2 border-t border-border/60 pt-4">
          <Button variant="outline" onClick={onBack}>
            Choose a different file
          </Button>
          <Button onClick={onImport} disabled={missing.length > 0}>
            Import {file.rows.length.toLocaleString()} rows
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ResultsStep({
  kindTitle,
  href,
  file,
  results,
  stoppedBecause,
  onAgain,
}: {
  kindTitle: string;
  href: string;
  file: Loaded;
  results: ImportRowResult[];
  stoppedBecause?: string;
  onAgain: () => void;
}) {
  const count = (status: ImportRowResult["status"]) => results.filter((r) => r.status === status).length;
  const failed = count("error");
  const flagged = results.filter((r) => r.status === "error" || r.warnings.length > 0);
  const tiles = [
    { label: "Created", value: count("created"), tone: "text-emerald-600 dark:text-emerald-400" },
    { label: "Already existed", value: count("existing") + count("skipped"), tone: "text-muted-foreground" },
    { label: "Failed", value: failed, tone: failed ? "text-destructive" : "text-muted-foreground" },
  ];

  return (
    <div className="space-y-4">
      {stoppedBecause ? (
        <div role="alert" className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{stoppedBecause}</span>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-sm font-medium">
          <CheckCircle2 className="h-4 w-4 text-emerald-600" /> Import finished
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        {tiles.map((t) => (
          <Card key={t.label}>
            <CardContent className="py-4">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">{t.label}</p>
              <p className={cn("text-2xl font-semibold tabular-nums", t.tone)}>{t.value.toLocaleString()}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {flagged.length ? (
        <Card>
          <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="text-base">Rows that need a look</CardTitle>
              <CardDescription>
                Failed rows were not imported. Rows with a note were imported with the adjustment described.
              </CardDescription>
            </div>
            {failed ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  downloadCsv(timestampedName(`failed-${kindTitle.toLowerCase()}`), failedRowsCsv(file.headers, file.rows, results))
                }
              >
                Download failed rows
              </Button>
            ) : null}
          </CardHeader>
          <CardContent>
            <ul className="divide-y divide-border/60 text-sm">
              {flagged.slice(0, 200).map((r) => (
                <li key={r.row_number} className="flex gap-3 py-2">
                  <span className="w-16 shrink-0 tabular-nums text-muted-foreground">Row {r.row_number}</span>
                  <Badge variant={r.status === "error" ? "destructive" : "secondary"} className="h-5 shrink-0">
                    {r.status === "error" ? "Failed" : "Note"}
                  </Badge>
                  <span className="min-w-0">
                    {[r.status === "error" ? r.message : null, ...r.warnings].filter(Boolean).join(" · ")}
                  </span>
                </li>
              ))}
            </ul>
            {flagged.length > 200 ? (
              <p className="pt-2 text-xs text-muted-foreground">
                And {(flagged.length - 200).toLocaleString()} more — download the failed rows for the full list.
              </p>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button asChild>
          <Link href={href}>View {kindTitle.toLowerCase()}</Link>
        </Button>
        <Button variant="outline" onClick={onAgain}>
          Import another file
        </Button>
      </div>
    </div>
  );
}
