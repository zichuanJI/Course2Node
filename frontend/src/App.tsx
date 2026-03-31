import { useState } from "react";
import { UploadForm } from "./components/Upload/UploadForm";
import { PipelineStatus } from "./components/Pipeline/PipelineStatus";
import { NoteEditor } from "./components/NoteEditor/NoteEditor";
import { exportNote } from "./api/client";
import type { NoteDocument } from "./types";

type View = "upload" | "processing" | "review";

export default function App() {
  const [view, setView] = useState<View>("upload");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [note, setNote] = useState<NoteDocument | null>(null);

  function handleSessionCreated(id: string) {
    setSessionId(id);
    setView("processing");
  }

  async function handlePipelineReady() {
    // Fetch the generated note from the synthesize artifact via export endpoint
    try {
      const md = await exportNote(sessionId!, "markdown");
      // In production, fetch the full NoteDocument JSON instead.
      // For now, construct a minimal shell so the editor renders.
      const shell: NoteDocument = {
        metadata: { session_id: sessionId!, course_title: "", lecture_title: "Lecture", language: "auto", generated_at: new Date().toISOString() },
        one_paragraph_summary: "",
        sections: [{ section_id: "s1", title: "Generated Note", blocks: [{ id: "b1", kind: "section", title: "", content_md: md, provenance: [], citations: [], grounding_level: "lecture" }] }],
        supplemental_context: [],
        key_terms: [],
        open_questions: [],
      };
      setNote(shell);
      setView("review");
    } catch {
      // stay on processing if note not ready yet
    }
  }

  return (
    <div style={{ padding: 32, fontFamily: "Georgia, serif", background: "#faf9f5", minHeight: "100vh" }}>
      <h1 style={{ color: "#1c1815" }}>Course2Note</h1>

      {view === "upload" && (
        <UploadForm onSessionCreated={handleSessionCreated} />
      )}

      {view === "processing" && sessionId && (
        <PipelineStatus sessionId={sessionId} onReady={handlePipelineReady} />
      )}

      {view === "review" && sessionId && note && (
        <NoteEditor sessionId={sessionId} note={note} />
      )}
    </div>
  );
}
