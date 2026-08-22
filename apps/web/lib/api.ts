import { createClient } from "@/lib/supabase/client";

/** All resource endpoints live under the versioned prefix; probes (/health) do not. */
export const API_VERSION_PREFIX = "/api/v1";

/** Server-side cap on `limit` (mirrors MAX_LIMIT in apps/api/app/core/pagination.py). */
export const MAX_PAGE_SIZE = 200;

const apiOrigin = () => {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (!url) throw new Error("NEXT_PUBLIC_API_URL is not set");
  return url.replace(/\/$/, "");
};

/** Pagination metadata returned alongside every collection. */
export type PageMeta = {
  limit: number;
  offset: number;
  total: number | null;
  has_more: boolean;
};

/** Envelope returned by every collection endpoint. */
export type Page<T> = {
  items: T[];
  page: PageMeta;
};

/** RFC 9457 Problem Details, as returned by the API for every error. */
export type ProblemDetails = {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  code: string;
  request_id?: string;
  errors?: { field: string; message: string; type: string }[];
};

/** Error carrying the parsed problem document, so callers can branch on `code`. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;
  readonly fieldErrors?: ProblemDetails["errors"];

  constructor(problem: ProblemDetails) {
    super(problem.detail || problem.title || "Request failed");
    this.name = "ApiError";
    this.status = problem.status;
    this.code = problem.code;
    this.requestId = problem.request_id;
    this.fieldErrors = problem.errors;
  }

  /** True when the caller is unauthenticated or their session has expired. */
  get isAuthError() {
    return this.status === 401;
  }
}

async function toApiError(res: Response): Promise<ApiError> {
  const text = await res.text();
  try {
    const problem = JSON.parse(text) as ProblemDetails;
    if (problem && typeof problem.status === "number" && problem.code) {
      return new ApiError(problem);
    }
    return new ApiError({
      type: "about:blank",
      title: res.statusText,
      status: res.status,
      detail: text || res.statusText,
      instance: "",
      code: "error",
    });
  } catch {
    return new ApiError({
      type: "about:blank",
      title: res.statusText,
      status: res.status,
      detail: text || res.statusText,
      instance: "",
      code: "error",
    });
  }
}

/**
 * Call the API with the current Supabase access token attached.
 *
 * `path` is relative to the versioned prefix (e.g. `/leads`). Pass an absolute path starting
 * with `/health` to reach an unversioned probe.
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  if (session?.access_token) {
    headers.set("Authorization", `Bearer ${session.access_token}`);
  }

  const prefix = path.startsWith("/health") || path === "/" ? "" : API_VERSION_PREFIX;
  const res = await fetch(`${apiOrigin()}${prefix}${path}`, { ...init, headers });

  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/**
 * Fetch a single resource, returning `null` instead of throwing when it does not exist.
 *
 * Use for genuinely optional one-to-one lookups (a lead's opportunity, say). Other errors
 * still throw, so a 403 or an outage is never silently rendered as "not found".
 */
export async function apiFetchOptional<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    return await apiFetch<T>(path, init);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

/** Fetch one page of a collection, keeping the pagination metadata. */
export async function apiPage<T>(path: string, init?: RequestInit): Promise<Page<T>> {
  return apiFetch<Page<T>>(path, init);
}

/** Fetch a collection and return just the rows, discarding pagination metadata. */
export async function apiList<T>(path: string, init?: RequestInit): Promise<T[]> {
  const page = await apiFetch<Page<T>>(path, init);
  return page.items ?? [];
}

/**
 * Fetch every page of a collection.
 *
 * Needed where the UI genuinely requires the whole set (the Kanban board, for example) now
 * that the server caps `limit`. `maxPages` bounds the work so a pathological dataset cannot
 * spin forever.
 */
export async function apiListAll<T>(path: string, maxPages = 20): Promise<T[]> {
  const separator = path.includes("?") ? "&" : "?";
  const items: T[] = [];
  let offset = 0;

  for (let pageIndex = 0; pageIndex < maxPages; pageIndex += 1) {
    const page = await apiFetch<Page<T>>(
      `${path}${separator}limit=${MAX_PAGE_SIZE}&offset=${offset}`
    );
    items.push(...(page.items ?? []));
    if (!page.page?.has_more) break;
    offset += MAX_PAGE_SIZE;
  }
  return items;
}
