import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import clsx from "clsx";
import { getSession, ingestPdf, ingestAudio, buildGraph } from "../api/client";
import { useSessionStatus } from "../hooks/useSessionStatus";
import { useToast } from "../components/primitives/Toast";
import type { CourseSession, SessionStatus } from "../types";
import "./PipelinePage.css";

// ── PipelineCanvas ────────────────────────────────────────────────────────────
function PipelineCanvas({ phase, progress }: { phase: number; progress: number }) {
  // Deterministic layout: 3 doc sheets, 12 chunks, 18 concept dots
  const WIDTH = 900;
  const HEIGHT = 540;
  const tick = (progress / 100) * Math.min(1, (phase + 1) / 3);

  const docs = useMemo(() =>
    Array.from({ length: 3 }, (_, i) => ({
      x: 100 + i * 120,
      y: 200,
    })), []);

  const chunks = useMemo(() =>
    Array.from({ length: 12 }, (_, i) => {
      const col = i % 4;
      const row = Math.floor(i / 4);
      return { x: 380 + col * 60, y: 150 + row * 70 };
    }), []);

  const dots = useMemo(() =>
    Array.from({ length: 18 }, (_, i) => {
      const angle = (i / 18) * Math.PI * 2;
      const r = 80 + ((i * 13) % 40);
      return { x: 720 + Math.cos(angle) * r * 0.6, y: 270 + Math.sin(angle) * r };
    }), []);

  const docOpacity = phase >= 0 ? Math.min(1, tick * 4) : 0;
  const chunkOpacity = phase >= 1 ? Math.min(1, (tick - 0.2) * 3) : 0;
  const dotOpacity = phase >= 2 ? Math.min(1, (tick - 0.5) * 3) : 0;
  const edgeOpacity = phase >= 3 ? Math.min(1, (tick - 0.8) * 5) : 0;

  return (
    <svg className="viz-canvas" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="xMidYMid meet">
      {/* Doc to chunk lines */}
      {phase >= 1 && docs.map((d, di) =>
        chunks.slice(di * 4, di * 4 + 4).map((c, ci) => (
          <line
            key={`dc-${di}-${ci}`}
            x1={d.x + 24} y1={d.y} x2={c.x} y2={c.y}
            stroke="var(--rule-strong)" strokeWidth="0.8"
            opacity={chunkOpacity * 0.6}
          />
        ))
      )}

      {/* Doc sheets */}
      {docs.map((d, i) => (
        <g key={i} opacity={docOpacity}>
          <rect x={d.x} y={d.y - 36} width={48} height={64} rx="4"
            fill="var(--panel)" stroke="var(--rule-strong)" strokeWidth="1.2" />
          {[0, 1, 2, 3].map((li) => (
            <line key={li} x1={d.x + 8} y1={d.y - 24 + li * 12} x2={d.x + 40} y2={d.y - 24 + li * 12}
              stroke="var(--rule)" strokeWidth="1" />
          ))}
        </g>
      ))}

      {/* Chunk rects */}
      {chunks.map((c, i) => (
        <rect key={i} x={c.x - 18} y={c.y - 10} width={36} height={20} rx="3"
          fill="var(--panel-2)" stroke="var(--rule-strong)" strokeWidth="1"
          opacity={chunkOpacity} />
      ))}

      {/* Chunk to dot lines */}
      {phase >= 2 && chunks.slice(0, 6).map((c, ci) =>
        dots.slice(ci * 3, ci * 3 + 3).map((d, di) => (
          <line
            key={`cd-${ci}-${di}`}
            x1={c.x + 18} y1={c.y} x2={d.x} y2={d.y}
            stroke="var(--rule-strong)" strokeWidth="0.6"
            opacity={dotOpacity * 0.5}
          />
        ))
      )}

      {/* Concept dots */}
      {dots.map((d, i) => (
        <circle key={i} cx={d.x} cy={d.y} r={4 + (i % 3)} fill="var(--accent)"
          opacity={dotOpacity * 0.75} />
      ))}

      {/* Edges between dots */}
      {phase >= 3 && dots.map((d, i) => {
        const next = dots[(i + 3) % dots.length];
        return (
          <line key={`e-${i}`} x1={d.x} y1={d.y} x2={next.x} y2={next.y}
            stroke="var(--accent)" strokeWidth="0.9"
            opacity={edgeOpacity * 0.4} />
        );
      })}
    </svg>
  );
}

// ── Log lines ─────────────────────────────────────────────────────────────────
interface LogLine { ts: string; text: string; cls: string; }

function makeLogLines(status: SessionStatus): LogLine[] {
  const now = () => new Date().toLocaleTimeString("zh-CN", { hour12: false });
  const lines: LogLine[] = [];
  if (status === "uploaded") {
    lines.push({ ts: now(), text: "文件已上传，等待解析…", cls: "log-info" });
  } else if (status === "ingesting") {
    lines.push({ ts: now(), text: "正在读取文档内容…", cls: "log-info" });
    lines.push({ ts: now(), text: "切分文本片段中…", cls: "log-info" });
    lines.push({ ts: now(), text: "抽取知识点…", cls: "log-info" });
  } else if (status === "graph_ready" || status === "notes_ready") {
    lines.push({ ts: now(), text: "文档解析完成", cls: "log-ok" });
    lines.push({ ts: now(), text: "概念图谱构建完成", cls: "log-ok" });
  } else if (status === "failed") {
    lines.push({ ts: now(), text: "处理失败，请检查文件格式", cls: "log-warn" });
  }
  return lines;
}

// ── PipelinePage ──────────────────────────────────────────────────────────────
const STAGES = [
  { label: "解析文档",  detail: "提取文本内容" },
  { label: "切分片段",  detail: "语义分块" },
  { label: "抽取概念",  detail: "识别知识点" },
  { label: "构建图谱",  detail: "建立关系网络" },
];

function statusToPhase(status: SessionStatus): number {
  if (status === "uploaded") return 0;
  if (status === "ingesting") return 2;
  if (status === "graph_ready" || status === "notes_ready") return 4;
  return 0;
}

export function PipelinePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const [session, setSession] = useState<CourseSession | null>(null);
  const triggered = useRef(false);
  const [tick, setTick] = useState(0);

  const { data: statusData } = useSessionStatus(id ?? null, true);
  const currentStatus = (statusData?.status ?? session?.status ?? "uploaded") as SessionStatus;
  const phase = statusToPhase(currentStatus);
  const progress = Math.min(100, (tick % 100));

  // Animate progress tick
  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), 200);
    return () => clearInterval(interval);
  }, []);

  // Load session info
  useEffect(() => {
    if (!id) return;
    getSession(id).then((s) => setSession(s as CourseSession)).catch(() => {});
  }, [id]);

  // Trigger pipeline
  useEffect(() => {
    if (!id || triggered.current) return;
    triggered.current = true;

    async function run() {
      const sess = await getSession(id!) as CourseSession;
      setSession(sess);

      const pdfs = sess.source_files.filter((f) => f.kind === "pdf" && !f.ingested);
      for (const f of pdfs) {
        try { await ingestPdf({ session_id: id!, source_id: f.source_id }); }
        catch (e) { toast(`PDF 解析失败: ${String(e)}`, "error"); }
      }

      const audios = sess.source_files.filter((f) => f.kind === "audio" && !f.ingested);
      for (const f of audios) {
        try { await ingestAudio({ session_id: id!, source_id: f.source_id }); }
        catch (e) { toast(`音频解析失败: ${String(e)}`, "error"); }
      }

      try { await buildGraph({ session_id: id! }); }
      catch (e) { toast(`图谱构建失败: ${String(e)}`, "error"); }
    }

    void run();
  }, [id, toast]);

  // Auto-navigate when ready
  useEffect(() => {
    if (currentStatus === "graph_ready" || currentStatus === "notes_ready") {
      navigate(`/session/${id}`);
    }
  }, [currentStatus, id, navigate]);

  const logLines = useMemo(() => makeLogLines(currentStatus), [currentStatus]);
  const isDone = currentStatus === "graph_ready" || currentStatus === "notes_ready";

  return (
    <div className="pipeline-page">
      {/* Hero */}
      <div className="pipeline-hero">
        <div>
          <h1 className="pipeline-h">{session?.lecture_title ?? "处理中…"}</h1>
          <p className="pipeline-hsub">{session?.course_title ?? ""}</p>
        </div>
        {!isDone && currentStatus !== "failed" && (
          <div className="pipeline-live-badge">
            <span className="pipeline-live-dot" />
            正在解析
          </div>
        )}
      </div>

      {/* Stage track */}
      <div className="stage-track">
        {STAGES.map((s, i) => {
          const active = phase === i || (phase > i && i === phase - 1);
          const done = phase > i;
          return (
            <div key={i} className={clsx("stage", { active, done })}>
              <div className="stage-num">
                {done
                  ? <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{ display: "inline-block" }}><polyline points="20 6 9 17 4 12" /></svg>
                  : `0${i + 1}`
                }
              </div>
              <div className="stage-name">{s.label}</div>
              <div className="stage-detail">{active ? s.detail : done ? "完成" : ""}</div>
            </div>
          );
        })}
      </div>

      {/* Viz canvas */}
      <div className="pipeline-viz">
        <PipelineCanvas phase={phase} progress={progress} />
        <div className="viz-counters">
          <span>文档 <b>{session?.stats?.document_count ?? "—"}</b></span>
          <span>片段 <b>{session?.stats?.chunk_count ?? "—"}</b></span>
          <span>概念 <b>{session?.stats?.concept_count ?? "—"}</b></span>
        </div>
        <div className="viz-label">PIPELINE · LIVE</div>
      </div>

      {/* Log strip */}
      <div className="log-strip">
        {logLines.map((line, i) => (
          <div key={i} className="log-row">
            <span className="log-ts">{line.ts}</span>
            <span className={line.cls}>{line.text}</span>
          </div>
        ))}
      </div>

      {/* Error */}
      {currentStatus === "failed" && (
        <div className="pipeline-error">
          {statusData?.error_message ?? "处理失败，请重试。"}
        </div>
      )}

      {/* Actions */}
      <div className="pipeline-actions">
        <button className="btn btn-ghost" onClick={() => navigate("/")} type="button">
          返回列表
        </button>
        {currentStatus === "failed" && (
          <button
            className="btn btn-accent"
            onClick={() => { triggered.current = false; window.location.reload(); }}
            type="button"
          >
            重试
          </button>
        )}
      </div>
    </div>
  );
}
