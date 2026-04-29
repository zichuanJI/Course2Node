import { lazy, Suspense, useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import clsx from "clsx";
import { getNote, getGraph, getSession } from "../api/client";
import { NoteView } from "../components/notes/NoteView";
import { SearchPanel } from "../components/search/SearchPanel";
import { ConceptDrawer } from "../components/graph/ConceptDrawer";
import { Skeleton } from "../components/primitives/Skeleton";
import type { CourseSession, GraphArtifact, NoteDocument } from "../types";
import "./WorkspacePage.css";

const ConceptGraph = lazy(() =>
  import("../components/graph/ConceptGraph").then((m) => ({ default: m.ConceptGraph })),
);

interface WorkspacePageProps {
  graphStyle?: string;
}

export function WorkspacePage({ graphStyle = "force" }: WorkspacePageProps) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const conceptId = searchParams.get("concept");

  const [note, setNote] = useState<NoteDocument | null>(null);
  const [graph, setGraph] = useState<GraphArtifact | null>(null);
  const [session, setSession] = useState<CourseSession | null>(null);
  const [searchCollapsed, setSearchCollapsed] = useState(false);
  const [notesCollapsed, setNotesCollapsed] = useState(false);
  const [rightTool, setRightTool] = useState<"notes" | "exam">("notes");

  useEffect(() => {
    if (!id) return;
    getNote(id).then(setNote).catch(() => {});
    getGraph(id).then(setGraph).catch(() => {});
    getSession(id).then((s) => setSession(s as CourseSession)).catch(() => {});
  }, [id]);

  if (!id) { navigate("/"); return null; }

  const selectedConcept = conceptId
    ? graph?.concepts.find((c) => c.concept_id === conceptId) ?? null
    : null;

  return (
    <div className={clsx("workspace", {
      "search-collapsed": searchCollapsed,
      "notes-collapsed": notesCollapsed,
    })}>
      {/* Left: Search */}
      <div className="ws-col">
        {searchCollapsed ? (
          <div
            className="ws-rail"
            onClick={() => setSearchCollapsed(false)}
            role="button"
            tabIndex={0}
            aria-label="展开搜索面板"
            onKeyDown={(e) => e.key === "Enter" && setSearchCollapsed(false)}
          >
            <button className="btn-icon" type="button">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
              </svg>
            </button>
            <span className="ws-rail-label">搜索</span>
          </div>
        ) : (
          <>
            <div className="ws-head">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--ink-3)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
              </svg>
              <span className="ws-title">检索</span>
              <div style={{ flex: 1 }} />
              <button
                className="btn-icon"
                onClick={() => setSearchCollapsed(true)}
                type="button"
                aria-label="折叠搜索面板"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="m15 18-6-6 6-6" />
                </svg>
              </button>
            </div>
            <div className="ws-search-body">
              <SearchPanel sessionId={id} />
            </div>
          </>
        )}
      </div>

      {/* Middle: Graph */}
      <div className="ws-col ws-col-graph">
        <div className="ws-head">
          <button
            className="btn-icon"
            onClick={() => navigate("/")}
            type="button"
            title="返回首页"
            aria-label="返回首页"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="m15 18-6-6 6-6" />
            </svg>
          </button>
          <span className="ws-title">
            {session?.lecture_title ?? "概念图谱"}
          </span>
          {session?.course_title && (
            <span className="ws-head-course">{session.course_title}</span>
          )}
        </div>
        <div className="ws-graph-wrap">
          <div className="graph-bg" />

          {/* Overlay: breadcrumb */}
          <div className="graph-head">
            <div className="graph-breadcrumb">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3" />
                <circle cx="5" cy="5" r="2" />
                <circle cx="19" cy="5" r="2" />
                <circle cx="5" cy="19" r="2" />
                <circle cx="19" cy="19" r="2" />
                <path d="m7 7 3 3m4 0 3-3m0 10-3-3m-4 0-3 3" />
              </svg>
              <span>全景</span>
              {selectedConcept && (
                <>
                  <span className="divider">/</span>
                  <span className="current">{selectedConcept.name}</span>
                  <button
                    className="btn-icon"
                    onClick={() => setSearchParams({})}
                    type="button"
                    aria-label="关闭聚焦"
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                      <path d="M18 6 6 18M6 6l12 12" />
                    </svg>
                  </button>
                </>
              )}
            </div>
          </div>

          <Suspense fallback={<Skeleton style={{ width: "100%", height: "100%", borderRadius: 0 }} />}>
            <ConceptGraph sessionId={id} graphStyle={graphStyle} />
          </Suspense>
          <ConceptDrawer sessionId={id} />

          {/* Overlay: stats */}
          {graph && (
            <div className="graph-stats">
              <span><b>{graph.concepts.length}</b> 概念</span>
              <span><b>{graph.edges.length}</b> 边</span>
              <span><b>{graph.topic_clusters.length}</b> 聚类</span>
            </div>
          )}
        </div>
      </div>

      {/* Right: Study tools */}
      <div className="ws-col ws-col-notes">
        {notesCollapsed ? (
          <div
            className="ws-rail"
            onClick={() => setNotesCollapsed(false)}
            role="button"
            tabIndex={0}
            aria-label="展开笔记面板"
            onKeyDown={(e) => e.key === "Enter" && setNotesCollapsed(false)}
          >
            <button className="btn-icon" type="button">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14,2 14,8 20,8"/>
              </svg>
            </button>
            <span className="ws-rail-label">工具</span>
          </div>
        ) : (
          <>
            <div className="ws-head">
              <div className="ws-tool-tabs" role="tablist" aria-label="学习工具">
                <button
                  className={clsx("ws-tool-tab", rightTool === "notes" && "ws-tool-tab-active")}
                  onClick={() => setRightTool("notes")}
                  type="button"
                  role="tab"
                  aria-selected={rightTool === "notes"}
                >
                  笔记
                </button>
                <button
                  className={clsx("ws-tool-tab", rightTool === "exam" && "ws-tool-tab-active")}
                  onClick={() => setRightTool("exam")}
                  type="button"
                  role="tab"
                  aria-selected={rightTool === "exam"}
                >
                  出卷
                </button>
              </div>
              <div style={{ flex: 1 }} />
              <button
                className="btn-icon"
                onClick={() => setNotesCollapsed(true)}
                type="button"
                aria-label="折叠笔记面板"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="m9 18 6-6-6-6" />
                </svg>
              </button>
            </div>
            <div className="ws-notes-body">
              {rightTool === "notes" ? (
                <NoteView sessionId={id} initialNote={note} />
              ) : (
                <div className="ws-exam-placeholder">
                  <div className="ws-exam-icon">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M9 11h6" />
                      <path d="M9 15h4" />
                      <path d="M5 3h14v18l-2-1-2 1-2-1-2 1-2-1-2 1-2-1z" />
                    </svg>
                  </div>
                  <h2>出卷功能预留</h2>
                  <p>
                    后续会基于知识点重要度、关系密度和课程目标生成题目。当前版本先保留入口，不触发后端请求。
                  </p>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
