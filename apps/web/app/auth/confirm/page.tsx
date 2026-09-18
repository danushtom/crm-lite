import { Suspense } from "react";
import ConfirmInner from "./confirm-inner";

export default function ConfirmPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center">Signing you in…</div>}>
      <ConfirmInner />
    </Suspense>
  );
}
