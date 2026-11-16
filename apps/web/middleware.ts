import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { safeNext } from "@/lib/auth";
import { needsSecondFactor } from "@/lib/mfa";

/** Reachable without a session. /auth/confirm must be: it is what creates the session. */
const PUBLIC_PATHS = ["/login", "/signup", "/forgot-password", "/auth/confirm"];
/** A signed-in user visiting these is sent on to the app instead. */
const SIGNED_OUT_ONLY = ["/login", "/signup", "/forgot-password"];

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({
    request: {
      headers: request.headers,
    },
  });

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !key) {
    return response;
  }

  const supabase = createServerClient(url, key, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet: { name: string; value: string; options?: object }[]) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({
          request,
        });
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options)
        );
      },
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const path = request.nextUrl.pathname;
  // Everything is signed-in only except these. An allow-list of public paths (rather than a
  // list of protected ones) means a new page is protected by default -- the old protected list
  // had already missed /voice-agents.
  const isPublic = PUBLIC_PATHS.some((p) => path === p || path.startsWith(p + "/"));
  // Exact matches: /login/verify is under /login but is where a signed-in user finishes 2FA.
  const isSignedOutOnly = SIGNED_OUT_ONLY.includes(path);

  if (!user && !isPublic) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = "/login";
    redirectUrl.search = "";
    redirectUrl.searchParams.set("next", path + request.nextUrl.search);
    return NextResponse.redirect(redirectUrl);
  }

  // A user with a second factor who has not used it this session goes to the code prompt.
  // The database refuses such a session anyway (20260920010000_enforce_mfa.sql); this turns
  // what would be empty screens into the step they need to take.
  if (user && !path.startsWith("/login/verify") && !path.startsWith("/auth/")) {
    if (await needsSecondFactor(supabase)) {
      const verifyUrl = request.nextUrl.clone();
      verifyUrl.pathname = "/login/verify";
      verifyUrl.search = "";
      verifyUrl.searchParams.set("next", isSignedOutOnly ? "/dashboard" : path + request.nextUrl.search);
      return NextResponse.redirect(verifyUrl);
    }
  }

  if (user && isSignedOutOnly) {
    const next = safeNext(request.nextUrl.searchParams.get("next"));
    return NextResponse.redirect(new URL(next, request.url));
  }

  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
