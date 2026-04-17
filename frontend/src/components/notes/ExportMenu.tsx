import { useEffect, useRef, useState } from "react";
import { exportNote } from "../../api/client";
import { Button } from "../primitives/Button";
import { useToast } from "../primitives/Toast";
import "./ExportMenu.css";

export function ExportMenu({ sessionId }: { sessionId: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const toast = useToast();

  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  async function handleExport(fmt: "markdown" | "tex" | "txt") {
    setOpen(false);
    try {
      const content = await exportNote(sessionId, fmt);
      const ext = fmt === "markdown" ? "md" : fmt;
      const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `notes.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast("导出失败", "error");
    }
  }

  async function handleCopy() {
    setOpen(false);
    try {
      const content = await exportNote(sessionId, "markdown");
      await navigator.clipboard.writeText(content);
      toast("已复制到剪贴板", "success");
    } catch {
      toast("复制失败", "error");
    }
  }

  return (
    <div className="export-menu" ref={ref}>
      <Button variant="ghost" size="sm" onClick={() => setOpen((v) => !v)}>
        导出 ▾
      </Button>
      {open && (
        <div className="export-dropdown">
          <button className="export-item" onClick={() => handleExport("markdown")}>
            <span className="export-item-icon">📝</span> Markdown
          </button>
          <button className="export-item" onClick={() => handleExport("tex")}>
            <span className="export-item-icon">📐</span> LaTeX
          </button>
          <button className="export-item" onClick={() => handleExport("txt")}>
            <span className="export-item-icon">📄</span> 纯文本
          </button>
          <button className="export-item" onClick={handleCopy}>
            <span className="export-item-icon">📋</span> 复制到剪贴板
          </button>
        </div>
      )}
    </div>
  );
}
