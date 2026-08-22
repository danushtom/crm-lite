"use client";

import { useMutation, type UseMutationOptions, type UseMutationResult } from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError } from "@/lib/api";

/**
 * `useMutation` with a sensible default error handler.
 *
 * Most mutations in this app previously had no `onError`, so a rejected write — a 409 from
 * converting an already-converted lead, a 403 from a partner editing CRM intelligence, a 422
 * from a field the API now validates — produced no visible result at all. The user saw the
 * form sit there and assumed it had worked.
 *
 * Pass `errorTitle` for the headline; the API's Problem Details `detail` (and any field
 * errors) become the description. Supplying your own `onError` overrides this entirely.
 */
export function useApiMutation<TData = unknown, TVariables = void, TContext = unknown>(
  options: UseMutationOptions<TData, Error, TVariables, TContext> & { errorTitle?: string }
): UseMutationResult<TData, Error, TVariables, TContext> {
  const { errorTitle = "Something went wrong", onError, ...rest } = options;

  return useMutation<TData, Error, TVariables, TContext>({
    ...rest,
    // Spread rather than naming the parameters: react-query has added arguments to this
    // callback across minor versions, and a fixed arity silently drops them.
    onError: (...args) => {
      if (onError) return onError(...args);
      toast.error(errorTitle, { description: describeError(args[0]) });
    },
  });
}

/** Turn an error into one line a user can act on. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.fieldErrors?.length) {
      return error.fieldErrors.map((f) => `${f.field}: ${f.message}`).join("; ");
    }
    if (error.isAuthError) {
      return "Your session has expired. Please sign in again.";
    }
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return "Unexpected error";
}
