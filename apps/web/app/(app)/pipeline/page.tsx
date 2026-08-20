import { redirect } from "next/navigation";

/** Legacy route — Kanban lives under `/opportunities`. */
export default function PipelineRedirectPage() {
  redirect("/opportunities");
}
