import { describe, expect, it } from "vitest";
import { toCsv } from "@/lib/csv";
import { detectDelimiter, parseCsv, parseCsvRecords } from "@/lib/csv-parse";
import { autoMap, buildRows, chunk, failedRowsCsv, missingRequired, type ImportField } from "@/lib/imports";

describe("parseCsv", () => {
  it("handles quotes, doubled quotes, embedded newlines, CRLF and a BOM", () => {
    const text = '﻿Name,Notes\r\n"Acme, Inc","said ""hi""\nthen left"\r\nGlobex,plain\r\n';
    const parsed = parseCsv(text);
    expect(parsed.headers).toEqual(["Name", "Notes"]);
    expect(parsed.rows).toEqual([
      ["Acme, Inc", 'said "hi"\nthen left'],
      ["Globex", "plain"],
    ]);
  });

  it("detects semicolon and tab delimiters from the header line", () => {
    expect(detectDelimiter("Name;Email;Phone\na;b;c")).toBe(";");
    expect(detectDelimiter("Name\tEmail\na\tb")).toBe("\t");
    expect(detectDelimiter('"Last; First",Email\n')).toBe(",");
    expect(parseCsv("Name;Email\nAsha;asha@acme.com").rows).toEqual([["Asha", "asha@acme.com"]]);
  });

  it("drops blank lines and pads short rows to the header width", () => {
    const parsed = parseCsv("A,B,C\n1,2\n\n,,\n4,5,6\n");
    expect(parsed.rows).toEqual([
      ["1", "2", ""],
      ["4", "5", "6"],
    ]);
  });

  it("names blank headers so they can still be mapped", () => {
    expect(parseCsv("Name,,Email\nA,x,a@b.co").headers).toEqual(["Name", "Column 2", "Email"]);
  });

  it("reads back what the exporter writes", () => {
    const csv = toCsv([{ name: 'He said "yes", twice', phone: "+91 98765" }], [
      { header: "Name", value: (r) => r.name },
      { header: "Phone", value: (r) => r.phone },
    ]);
    const [, row] = parseCsvRecords(csv);
    expect(row[0]).toBe('He said "yes", twice');
  });
});

const FIELDS: ImportField[] = [
  { key: "company", label: "Company name", required: true, aliases: ["company", "account name"], help: "" },
  { key: "full_name", label: "Contact full name", required: false, aliases: ["name", "full name"], help: "" },
  { key: "email", label: "Email", required: false, aliases: ["email", "email address"], help: "" },
  { key: "phone", label: "Phone", required: false, aliases: ["phone"], help: "" },
];

describe("autoMap", () => {
  it("matches headers regardless of case, punctuation and underscores", () => {
    const mapping = autoMap(["Account_Name", "E-mail Address", "Full Name", "Notes"], FIELDS);
    expect(mapping).toEqual({ company: 0, full_name: 2, email: -1, phone: -1 });
  });

  it("maps a HubSpot-style export", () => {
    const mapping = autoMap(["Company", "Name", "Email", "Phone"], FIELDS);
    expect(mapping).toEqual({ company: 0, full_name: 1, email: 2, phone: 3 });
  });

  it("never maps one column to two fields", () => {
    const fields: ImportField[] = [
      { key: "a", label: "A", required: false, aliases: ["x"], help: "" },
      { key: "b", label: "B", required: false, aliases: ["x"], help: "" },
    ];
    expect(autoMap(["X"], fields)).toEqual({ a: 0, b: -1 });
  });
});

describe("missingRequired", () => {
  it("names unmapped required fields", () => {
    expect(missingRequired(FIELDS, { company: -1, email: 1 }, "leads")).toEqual(["Company name"]);
  });

  it("asks contacts for some way to identify the person", () => {
    expect(missingRequired(FIELDS, { company: 0 }, "contacts")).toEqual(["a name or email column"]);
    expect(missingRequired(FIELDS, { company: 0, email: 1 }, "contacts")).toEqual([]);
  });
});

describe("buildRows", () => {
  it("keys each row by field, numbers it by file line, and sends blanks as null", () => {
    const rows = buildRows([["Acme", ""], ["Globex", "g@globex.com"]], { company: 0, email: 1, phone: -1 });
    expect(rows).toEqual([
      { row_number: 2, values: { company: "Acme", email: null } },
      { row_number: 3, values: { company: "Globex", email: "g@globex.com" } },
    ]);
  });

  it("undoes the exporter's formula guard so a failed-rows file re-imports cleanly", () => {
    const [row] = buildRows([["'+91 98765 43210", "'=not a formula", "it's fine"]], { a: 0, b: 1, c: 2 });
    expect(row.values).toEqual({ a: "+91 98765 43210", b: "=not a formula", c: "it's fine" });
  });
});

it("chunks into fixed-size batches", () => {
  expect(chunk([1, 2, 3, 4, 5], 2)).toEqual([[1, 2], [3, 4], [5]]);
});

it("the failed-rows file carries the original cells plus the reason", () => {
  const csv = failedRowsCsv(
    ["Company", "Email"],
    [
      ["Acme", "ok@acme.com"],
      ["Globex", "broken"],
    ],
    [
      { row_number: 2, status: "created", record_id: "c1", message: null, warnings: [] },
      { row_number: 3, status: "error", record_id: null, message: "'broken' is not a valid email address", warnings: [] },
    ],
  );
  const records = parseCsvRecords(csv);
  expect(records).toEqual([
    ["Company", "Email", "Import error"],
    ["Globex", "broken", "'broken' is not a valid email address"],
  ]);
});
