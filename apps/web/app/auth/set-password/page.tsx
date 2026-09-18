import { Suspense } from "react";
import SetPasswordInner from "./set-password-inner";

export default function SetPasswordPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center">Loading…</div>}>
      <SetPasswordInner />
    </Suspense>
  );
}
