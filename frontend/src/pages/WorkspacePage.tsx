import { lazy, Suspense, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getNote } from "../api/client";
import { NoteView } from "../components/notes/NoteView";
import { SearchPanel } from "../components/search/SearchPanel";
import { ConceptDrawer } from "../components/graph/ConceptDrawer";
import { Button } from "../components/primitives/Button";
import { Skeleton } from "../components/primitives/Skeleton";
import type { NoteDocument } from "../types";
import "./WorkspacePage.css";

const ConceptGraph = lazy(() =>
  import("../components/graph/ConceptGraph").then((m) => ({ default: m.ConceptGraph })),
);

export function WorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [note, setNote] = useState<NoteDocument | null>(null);

  useEffect(() => {
    if (!id) return;
    getNote(id).then(setNote).catch(() => {});
  }, [id]);

  if (!id) { navigate("/"); return null; }

  return (
    <>
      <div className="workspace-page">
        {/* Left: Search */}
        <div className="workspace-panel workspace-search">
          <div className="workspace-section-title">搜索知识点</div>
          <SearchPanel sessionId={id} />
        </div>

        {/* Middle: Graph */}
        <div className="workspace-panel workspace-graph">
          <Suspense fallback={<Skeleton style={{ width: "100%", height: "100%" }} />}>
            <ConceptGraph sessionId={id} />
          </Suspense>
        </div>

        {/* Right: Notes */}
        <div className="workspace-panel workspace-notes">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--space-4)" }}>
            <div className="workspace-section-title" style={{ margin: 0 }}>结构化笔记</div>
            <Button variant="ghost" size="sm" onClick={() => navigate("/")}>← 返回</Button>
          </div>
          <NoteView sessionId={id} initialNote={note} />
        </div>
      </div>

      <ConceptDrawer sessionId={id} />
    </>
  );
}
