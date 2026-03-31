import { useState } from "react";
import { exportNote, submitReviewEvent } from "../../api/client";
import type { NoteBlock, NoteDocument } from "../../types";

interface Props {
  sessionId: string;
  note: NoteDocument;
}

export function NoteEditor({ sessionId, note }: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");

  async function saveEdit(block: NoteBlock) {
    await submitReviewEvent(sessionId, {
      note_block_id: block.id,
      action: "edit",
      before: block.content_md,
      after: editContent,
    });
    setEditingId(null);
  }

  async function handleAcceptReject(block: NoteBlock, action: "accept" | "reject") {
    await submitReviewEvent(sessionId, { note_block_id: block.id, action });
  }

  async function handleExport(fmt: "markdown" | "tex" | "txt") {
    const content = await exportNote(sessionId, fmt);
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${note.metadata.lecture_title}.${fmt === "markdown" ? "md" : fmt}`;
    a.click();
  }

  function renderBlock(block: NoteBlock) {
    const isSupplemental = block.grounding_level === "supplemental";
    return (
      <div
        key={block.id}
        style={{
          border: isSupplemental ? "1px dashed #bc6a3a" : "1px solid #ddd5ca",
          borderRadius: 8,
          padding: "12px 16px",
          marginBottom: 12,
          background: isSupplemental ? "#fff8f2" : "#faf9f5",
        }}
      >
        {isSupplemental && (
          <span style={{ fontSize: 11, color: "#bc6a3a", fontWeight: 700 }}>
            [Supplemental – external source]
          </span>
        )}
        {block.title && <h4 style={{ margin: "4px 0" }}>{block.title}</h4>}
        {editingId === block.id ? (
          <>
            <textarea
              value={editContent}
              onChange={e => setEditContent(e.target.value)}
              rows={6}
              style={{ width: "100%", fontFamily: "monospace" }}
            />
            <button onClick={() => saveEdit(block)}>Save</button>
            <button onClick={() => setEditingId(null)}>Cancel</button>
          </>
        ) : (
          <>
            <p style={{ whiteSpace: "pre-wrap" }}>{block.content_md}</p>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => { setEditingId(block.id); setEditContent(block.content_md); }}>Edit</button>
              {isSupplemental && (
                <>
                  <button onClick={() => handleAcceptReject(block, "accept")}>Accept</button>
                  <button onClick={() => handleAcceptReject(block, "reject")}>Reject</button>
                </>
              )}
            </div>
          </>
        )}
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 780, margin: "0 auto" }}>
      <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
        <button onClick={() => handleExport("markdown")}>Export Markdown</button>
        <button onClick={() => handleExport("tex")}>Export TeX</button>
        <button onClick={() => handleExport("txt")}>Export TXT</button>
      </div>

      <h1>{note.metadata.lecture_title}</h1>
      <p><em>{note.metadata.course_title}</em></p>

      {note.one_paragraph_summary && (
        <blockquote style={{ borderLeft: "4px solid #bc6a3a", paddingLeft: 16 }}>
          {note.one_paragraph_summary}
        </blockquote>
      )}

      {note.sections.map(section => (
        <section key={section.section_id}>
          <h2>{section.title}</h2>
          {section.blocks.map(renderBlock)}
        </section>
      ))}

      {note.supplemental_context.length > 0 && (
        <section>
          <h2>Supplemental Context</h2>
          {note.supplemental_context.map(renderBlock)}
        </section>
      )}

      {note.key_terms.length > 0 && (
        <section>
          <h2>Key Terms</h2>
          {note.key_terms.map(renderBlock)}
        </section>
      )}

      {note.open_questions.length > 0 && (
        <section>
          <h2>Open Questions</h2>
          {note.open_questions.map(renderBlock)}
        </section>
      )}
    </div>
  );
}
