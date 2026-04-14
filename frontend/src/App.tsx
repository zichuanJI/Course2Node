import { useState } from "react";
import { NoteEditor } from "./components/NoteEditor/NoteEditor";
import { PipelineStatus } from "./components/Pipeline/PipelineStatus";
import { UploadForm } from "./components/Upload/UploadForm";

type View = "upload" | "processing" | "workspace";

export default function App() {
  const [view, setView] = useState<View>("upload");
  const [sessionId, setSessionId] = useState<string | null>(null);

  function handleSessionCreated(id: string) {
    setSessionId(id);
    setView("processing");
  }

  function handleReady() {
    setView("workspace");
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "radial-gradient(circle at top left, #fff4df 0%, #f6efe5 38%, #eef6f4 100%)",
        color: "#24180f",
      }}
    >
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "48px 24px 72px", display: "grid", gap: 32 }}>
        <header style={{ display: "grid", gap: 10 }}>
          <span style={{ color: "#876b57", fontSize: 14, letterSpacing: "0.08em", textTransform: "uppercase" }}>
            Course2Node
          </span>
          <h1 style={{ margin: 0, fontSize: "clamp(2.4rem, 4vw, 4.6rem)", lineHeight: 1 }}>
            让每个节点都成为一个知识点
          </h1>
          <p style={{ margin: 0, maxWidth: 760, color: "#5b493d", lineHeight: 1.7, fontSize: 16 }}>
            上传课程 PDF 和录音音频，自动抽取知识点、建立关系图，并基于图谱生成带来源证据的结构化笔记。
          </p>
        </header>

        {view === "upload" ? <UploadForm onSessionCreated={handleSessionCreated} /> : null}
        {view === "processing" && sessionId ? <PipelineStatus sessionId={sessionId} onReady={handleReady} /> : null}
        {view === "workspace" && sessionId ? <NoteEditor sessionId={sessionId} /> : null}
      </div>
    </div>
  );
}
