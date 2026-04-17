import { useState } from "react";
import type { NoteDocument } from "../../types";
import { generateNotes, getNote } from "../../api/client";
import { Markdown } from "./Markdown";
import { ExportMenu } from "./ExportMenu";
import { Button } from "../primitives/Button";
import { Input } from "../primitives/Input";
import { useToast } from "../primitives/Toast";
import "./NoteView.css";

export function NoteView({
  sessionId,
  initialNote,
}: {
  sessionId: string;
  initialNote: NoteDocument | null;
}) {
  const [note, setNote] = useState<NoteDocument | null>(initialNote);
  const [topic, setTopic] = useState("");
  const [generating, setGenerating] = useState(false);
  const toast = useToast();

  async function handleGenerate() {
    if (!topic.trim()) { toast("请输入主题", "error"); return; }
    setGenerating(true);
    try {
      await generateNotes({ session_id: sessionId, topic: topic.trim() });
      const fresh = await getNote(sessionId);
      setNote(fresh);
    } catch {
      toast("笔记生成失败", "error");
    } finally {
      setGenerating(false);
    }
  }

  if (!note) {
    return (
      <div className="note-generate">
        <p className="note-generate-label">输入主题后生成结构化笔记</p>
        <Input
          placeholder="例：TCP 拥塞控制机制"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleGenerate()}
          style={{ minWidth: 280 }}
        />
        <Button onClick={handleGenerate} loading={generating}>生成笔记</Button>
      </div>
    );
  }

  return (
    <div className="note-view">
      <div className="note-view-header">
        <h2 className="note-view-title">{note.title}</h2>
        <ExportMenu sessionId={sessionId} />
      </div>
      <div className="note-view-summary">
        <Markdown>{note.summary}</Markdown>
      </div>
      {note.sections.map((section) => (
        <div key={section.section_id} className="note-section">
          <h3 className="note-section-title">{section.title}</h3>
          <Markdown>{section.content_md}</Markdown>
        </div>
      ))}
    </div>
  );
}
