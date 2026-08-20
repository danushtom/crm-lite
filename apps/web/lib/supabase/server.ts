import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

const MISSING_SUPABASE_ENV_MSG =
  "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY. " +
  "Create apps/web/.env.local (copy from apps/web/.env.example) and set both variables from Supabase Dashboard → Project Settings → API.";

export async function createClient() {
  const cookieStore = await cookies();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url?.trim() || !key?.trim()) {
    throw new Error(MISSING_SUPABASE_ENV_MSG);
  }

  return createServerClient(url, key, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet: { name: string; value: string; options?: object }[]) {
        try {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          );
        } catch {
          /* ignore in Server Components */
        }
      },
    },
  });
}
