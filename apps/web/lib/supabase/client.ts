import { createBrowserClient } from "@supabase/ssr";

const MISSING_SUPABASE_ENV_MSG =
  "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY. " +
  "Create apps/web/.env.local (copy from apps/web/.env.example) and set both variables from Supabase Dashboard → Project Settings → API.";

export function createClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url?.trim() || !key?.trim()) {
    throw new Error(MISSING_SUPABASE_ENV_MSG);
  }
  return createBrowserClient(url, key);
}
