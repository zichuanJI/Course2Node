import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { uploadPdfWithProgress, uploadAudioWithProgress } from "../api/client";
import { DropZone } from "../components/upload/DropZone";
import { FileRow, type FileEntry } from "../components/upload/FileRow";
import { Button } from "../components/primitives/Button";
import { Input } from "../components/primitives/Input";
import { useToast } from "../components/primitives/Toast";
import type { SourceKind } from "../types";
import "./NewSessionPage.css";

function guessKind(file: File): SourceKind {
  if (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")) return "pdf";
  return "audio";
}

let idCounter = 0;

export function NewSessionPage() {
  const [courseTitle, setCourseTitle] = useState("");
  const [lectureTitle, setLectureTitle] = useState("");
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [uploading, setUploading] = useState(false);
  const sessionIdRef = useRef<string | null>(null);
  const toast = useToast();
  const navigate = useNavigate();

  const handleFiles = useCallback((files: File[]) => {
    setEntries((prev) => [
      ...prev,
      ...files.map((f) => ({
        id: String(++idCounter),
        file: f,
        kind: guessKind(f),
        status: "queued" as const,
        progress: 0,
      })),
    ]);
  }, []);

  function updateEntry(id: string, patch: Partial<FileEntry>) {
    setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, ...patch } : e)));
  }

  async function handleUpload() {
    if (entries.length === 0) return;
    if (!courseTitle.trim() || !lectureTitle.trim()) {
      toast("请填写课程名和讲座名", "error");
      return;
    }
    setUploading(true);

    for (const entry of entries) {
      updateEntry(entry.id, { status: "uploading", progress: 0 });
      try {
        const form = new FormData();
        form.append("file", entry.file);
        form.append("course_title", courseTitle.trim());
        form.append("lecture_title", lectureTitle.trim());
        if (sessionIdRef.current) {
          form.append("session_id", sessionIdRef.current);
        }

        const uploadFn = entry.kind === "pdf" ? uploadPdfWithProgress : uploadAudioWithProgress;
        const result = await uploadFn(form, (pct) => updateEntry(entry.id, { progress: pct }));
        sessionIdRef.current = result.session_id;
        updateEntry(entry.id, { status: "done", progress: 100 });
      } catch (e) {
        updateEntry(entry.id, { status: "failed", error: String(e) });
        toast(`${entry.file.name} 上传失败`, "error");
      }
    }

    setUploading(false);
    if (sessionIdRef.current) {
      navigate(`/session/${sessionIdRef.current}/pipeline`);
    }
  }

  const canUpload = entries.length > 0 && !uploading;

  return (
    <div className="new-session-page">
      <h1 className="new-session-heading">新建课程</h1>
      <div className="new-session-form">
        <div className="new-session-fields">
          <Input
            label="课程名称"
            placeholder="例：计算机网络原理"
            value={courseTitle}
            onChange={(e) => setCourseTitle(e.target.value)}
          />
          <Input
            label="讲座标题"
            placeholder="例：第三讲 TCP 拥塞控制"
            value={lectureTitle}
            onChange={(e) => setLectureTitle(e.target.value)}
          />
        </div>

        <DropZone onFiles={handleFiles} />

        {entries.length > 0 && (
          <div className="new-session-file-list">
            {entries.map((e) => (
              <FileRow key={e.id} entry={e} />
            ))}
          </div>
        )}

        <div className="new-session-actions">
          <Button variant="ghost" onClick={() => navigate("/")}>取消</Button>
          <Button onClick={handleUpload} loading={uploading} disabled={!canUpload}>
            {uploading ? "上传中…" : "上传并开始解析"}
          </Button>
        </div>
      </div>
    </div>
  );
}
