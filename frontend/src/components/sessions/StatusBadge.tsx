import { Badge } from "../primitives/Pill";
import type { SessionStatus } from "../../types";

const STATUS_MAP: Record<SessionStatus, { label: string; variant: "default" | "success" | "danger" | "warning" | "info" | "accent" }> = {
  draft:       { label: "草稿",   variant: "default" },
  uploaded:    { label: "已上传", variant: "accent" },
  ingesting:   { label: "解析中", variant: "warning" },
  graph_ready: { label: "图已就绪", variant: "info" },
  notes_ready: { label: "笔记已就绪", variant: "success" },
  failed:      { label: "失败",   variant: "danger" },
};

export function StatusBadge({ status }: { status: SessionStatus }) {
  const { label, variant } = STATUS_MAP[status] ?? { label: status, variant: "default" };
  return <Badge variant={variant}>{label}</Badge>;
}
