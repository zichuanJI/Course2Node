import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import clsx from "clsx";
import { listSessions } from "../api/client";
import type { CourseSession, SessionStatus } from "../types";
import { useToast } from "../components/primitives/Toast";
import "./HomePage.css";

// ── CoverMark ─────────────────────────────────────────────────────────────────
function CoverMark({ seed, size = 56 }: { seed: string; size?: number }) {
  let h = 0;
  for (let i = 0; i < (seed || "").length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  const rot = h % 360;
  const n = 3 + (h % 4);
  const dots = Array.from({ length: n }, (_, i) => {
    const a = (i / n) * Math.PI * 2 + (rot * Math.PI) / 180;
    const r = 14 + ((h >> i) & 7);
    return { x: 50 + Math.cos(a) * r, y: 50 + Math.sin(a) * r, r: 3 + ((h >> (i * 2)) & 3) };
  });
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" style={{ display: "block" }}>
      <rect x="1" y="1" width="98" height="98" rx="8" fill="var(--panel-2)" stroke="var(--rule)" />
      {dots.map((d, i) =>
        dots.slice(i + 1).map((d2, j) => (
          <line
            key={`${i}-${j}`}
            x1={d.x} y1={d.y} x2={d2.x} y2={d2.y}
            stroke="var(--rule-strong)" strokeWidth="0.8"
          />
        )),
      )}
      {dots.map((d, i) => (
        <circle key={i} cx={d.x} cy={d.y} r={d.r} fill="var(--accent)" opacity="0.7" />
      ))}
    </svg>
  );
}

// ── StatusChip ────────────────────────────────────────────────────────────────
const STATUS_MAP: Record<SessionStatus, { cls: string; label: string }> = {
  draft:       { cls: "chip",       label: "草稿" },
  uploaded:    { cls: "chip chip-info",  label: "已上传" },
  ingesting:   { cls: "chip chip-live",  label: "解析中" },
  graph_ready: { cls: "chip chip-warn",  label: "图谱就绪" },
  notes_ready: { cls: "chip chip-ok",    label: "已就绪" },
  failed:      { cls: "chip chip-err",   label: "失败" },
};

function StatusChip({ status }: { status: SessionStatus }) {
  const { cls, label } = STATUS_MAP[status] ?? { cls: "chip", label: status };
  return (
    <span className={cls}>
      <span className="chip-dot" />
      {label}
    </span>
  );
}

// ── Status filter groups ──────────────────────────────────────────────────────
type FilterGroup = "all" | "ready" | "processing" | "failed";

function matchFilter(status: SessionStatus, filter: FilterGroup): boolean {
  if (filter === "all") return true;
  if (filter === "ready") return status === "notes_ready" || status === "graph_ready";
  if (filter === "processing") return status === "ingesting" || status === "uploaded" || status === "draft";
  if (filter === "failed") return status === "failed";
  return true;
}

// ── HomePage ──────────────────────────────────────────────────────────────────
export function HomePage() {
  const [sessions, setSessions] = useState<CourseSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<FilterGroup>("all");
  const [courseFilter, setCourseFilter] = useState<string>("all");
  const toast = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    listSessions()
      .then((data) => setSessions(data.sort((a, b) => b.updated_at.localeCompare(a.updated_at))))
      .catch(() => toast("加载会话列表失败", "error"))
      .finally(() => setLoading(false));
  }, [toast]);

  const courses = useMemo(() => {
    const seen = new Set<string>();
    return sessions.filter((s) => {
      if (seen.has(s.course_title)) return false;
      seen.add(s.course_title);
      return true;
    }).map((s) => s.course_title);
  }, [sessions]);

  const filtered = useMemo(() => {
    const lq = query.toLowerCase();
    return sessions.filter((s) => {
      if (!matchFilter(s.status, statusFilter)) return false;
      if (courseFilter !== "all" && s.course_title !== courseFilter) return false;
      if (lq && !s.lecture_title.toLowerCase().includes(lq) && !s.course_title.toLowerCase().includes(lq)) return false;
      return true;
    });
  }, [sessions, statusFilter, courseFilter, query]);

  // Group by course_title
  const groups = useMemo(() => {
    const map = new Map<string, CourseSession[]>();
    for (const s of filtered) {
      const arr = map.get(s.course_title) ?? [];
      arr.push(s);
      map.set(s.course_title, arr);
    }
    return map;
  }, [filtered]);

  const totalConcepts = sessions.reduce((a, s) => a + (s.stats?.concept_count ?? 0), 0);
  const totalRelations = sessions.reduce((a, s) => a + (s.stats?.relation_count ?? 0), 0);

  return (
    <div className="page">
      {/* Header */}
      <div className="home-head">
        <div className="home-head-left">
          <div className="home-head-label">课程库 · LIBRARY</div>
          <h1 className="home-title">
            我的课程 / <em>notes</em>
          </h1>
          <p className="home-sub">
            {sessions.length} 节课 · 累计 <b>{totalConcepts.toLocaleString()}</b> 个知识点，<b>{totalRelations.toLocaleString()}</b> 条关系
          </p>
        </div>
        <button
          className="btn btn-accent"
          onClick={() => navigate("/new")}
          type="button"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
          新建课程
        </button>
      </div>

      {/* Toolbar */}
      <div className="home-toolbar">
        <div className="home-search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
          </svg>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索课程或讲座…"
          />
        </div>

        <div className="filter-group">
          <span className="filter-label">状态</span>
          {(["all", "ready", "processing", "failed"] as FilterGroup[]).map((f) => (
            <button
              key={f}
              className={clsx("filter-pill", { active: statusFilter === f })}
              onClick={() => setStatusFilter(f)}
              type="button"
            >
              {{ all: "全部", ready: "已就绪", processing: "处理中", failed: "失败" }[f]}
            </button>
          ))}
        </div>

        <div className="filter-group">
          <span className="filter-label">课程</span>
          <select
            className="filter-select"
            value={courseFilter}
            onChange={(e) => setCourseFilter(e.target.value)}
          >
            <option value="all">全部</option>
            {courses.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="session-list">
          {[1, 2, 3].map((i) => <div key={i} className="home-skeleton" />)}
        </div>
      ) : groups.size === 0 ? (
        <div className="home-empty">
          <div className="home-empty-title">暂无课程</div>
          {sessions.length === 0
            ? "上传你的第一节课 PDF 或录音，开始构建知识点图谱。"
            : "没有符合筛选条件的课程。"}
        </div>
      ) : (
        <div className="session-list">
          {Array.from(groups.entries()).map(([course, rows]) => (
            <div key={course}>
              <div className="session-group-header">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--ink-3)", flexShrink: 0 }}>
                  <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" /><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
                </svg>
                <span className="session-group-name">{course}</span>
                <span className="session-group-count">{rows.length} 讲</span>
              </div>
              {rows.map((s) => (
                <SessionRow key={s.session_id} session={s} onClick={() => navigate(`/session/${s.session_id}`)} />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SessionRow({ session: s, onClick }: { session: CourseSession; onClick: () => void }) {
  const date = new Date(s.updated_at).toLocaleDateString("zh-CN", { month: "short", day: "numeric" });
  const hasPdf = s.source_files.some((f) => f.kind === "pdf");
  const hasAudio = s.source_files.some((f) => f.kind === "audio");

  return (
    <div className="session-row" onClick={onClick} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onClick()}>
      <CoverMark seed={s.session_id} size={56} />

      <div style={{ minWidth: 0 }}>
        <div className="session-lecture">{s.lecture_title}</div>
        <div className="session-meta">
          <span>{date}</span>
          {hasPdf && (
            <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14,2 14,8 20,8"/></svg>
              PDF
            </span>
          )}
          {hasAudio && (
            <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
              音频
            </span>
          )}
        </div>
      </div>

      <div className="session-stats">
        <span><b>{s.stats?.concept_count ?? "—"}</b> 概念</span>
        <span><b>{s.stats?.relation_count ?? "—"}</b> 关系</span>
      </div>

      <StatusChip status={s.status} />

      <div />

      <svg className="session-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="m9 18 6-6-6-6" />
      </svg>
    </div>
  );
}
