import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import clsx from "clsx";
import { buildCourseGraph, getCourseSession } from "../api/client";
import { useToast } from "../components/primitives/Toast";
import type { SessionStatus } from "../types";
import "./PipelinePage.css";
import "./CoursePipelinePage.css";

const courseRunsInFlight = new Set<string>();

// ── MergeCanvas ───────────────────────────────────────────────────────────────
function MergeCanvas({ phase, progress }: { phase: number; progress: number }) {
  const WIDTH = 900;
  const HEIGHT = 540;
  const tick = (progress / 100) * Math.min(1, (phase + 1) / 4);

  const subGraphs = useMemo(
    () =>
      Array.from({ length: 4 }, (_, i) => ({
        cx: 120 + i * 180,
        cy: 200,
      })),
    [],
  );

  const mergedDots = useMemo(
    () =>
      Array.from({ length: 20 }, (_, i) => {
        const angle = (i / 20) * Math.PI * 2;
        const r = 70 + ((i * 17) % 50);
        return {
          x: 700 + Math.cos(angle) * r * 0.5,
          y: 270 + Math.sin(angle) * r,
        };
      }),
    [],
  );

  const subOpacity = phase >= 0 ? Math.min(1, tick * 5) : 0;
  const flowOpacity = phase >= 1 ? Math.min(1, (tick - 0.15) * 4) : 0;
  const mergedOpacity = phase >= 2 ? Math.min(1, (tick - 0.4) * 3) : 0;
  const hierarchyOpacity = phase >= 3 ? Math.min(1, (tick - 0.7) * 4) : 0;

  return (
    <svg
      className="viz-canvas"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      preserveAspectRatio="xMidYMid meet"
    >
      {/* Sub-graphs */}
      {subGraphs.map((g, gi) => (
        <g key={gi} opacity={subOpacity}>
          <circle
            cx={g.cx}
            cy={g.cy}
            r={40}
            fill="none"
            stroke="var(--rule-strong)"
            strokeWidth="1.2"
            strokeDasharray="4,3"
          />
          {[0, 1, 2, 3, 4].map((di) => {
            const a = (di / 5) * Math.PI * 2;
            return (
              <circle
                key={di}
                cx={g.cx + Math.cos(a) * 22}
                cy={g.cy + Math.sin(a) * 22}
                r={3 + (di % 2)}
                fill="var(--accent)"
                opacity={0.6}
              />
            );
          })}
        </g>
      ))}

      {/* Flow arrows */}
      {phase >= 1 &&
        subGraphs.map((g, gi) => (
          <line
            key={`flow-${gi}`}
            x1={g.cx + 45}
            y1={g.cy}
            x2={620}
            y2={270}
            stroke="var(--accent)"
            strokeWidth="0.8"
            opacity={flowOpacity * 0.4}
            strokeDasharray="6,4"
          />
        ))}

      {/* Merged dots */}
      {mergedDots.map((d, i) => (
        <circle
          key={i}
          cx={d.x}
          cy={d.y}
          r={4 + (i % 3)}
          fill="var(--accent)"
          opacity={mergedOpacity * 0.7}
        />
      ))}

      {/* Hierarchy edges */}
      {phase >= 3 &&
        mergedDots.slice(0, 5).map((core, ci) =>
          mergedDots.slice(5 + ci * 3, 5 + ci * 3 + 3).map((child, chi) => (
            <line
              key={`h-${ci}-${chi}`}
              x1={core.x}
              y1={core.y}
              x2={child.x}
              y2={child.y}
              stroke="var(--accent)"
              strokeWidth="1"
              opacity={hierarchyOpacity * 0.5}
            />
          )),
        )}

      {/* Core highlights */}
      {phase >= 3 &&
        mergedDots.slice(0, 5).map((d, i) => (
          <circle
            key={`core-${i}`}
            cx={d.x}
            cy={d.y}
            r={7}
            fill="none"
            stroke="var(--accent)"
            strokeWidth="1.5"
            opacity={hierarchyOpacity}
          />
        ))}
    </svg>
  );
}

// ── CoursePipelinePage ────────────────────────────────────────────────────────
const STAGES = [
  { label: "加载子图谱", detail: "收集已有图谱" },
  { label: "合并概念", detail: "去重与信息融合" },
  { label: "计算指标", detail: "重新评估重要性" },
  { label: "构建层级", detail: "核心节点分层" },
];

export function CoursePipelinePage() {
  const { title } = useParams<{ title: string }>();
  const courseTitle = title ? decodeURIComponent(title) : "";
  const navigate = useNavigate();
  const toast = useToast();
  const triggered = useRef(false);
  const [tick, setTick] = useState(0);
  const [phase, setPhase] = useState(0);
  const [currentStatus, setCurrentStatus] = useState<SessionStatus | "idle">("idle");
  const [error, setError] = useState<string | null>(null);

  const progress = Math.min(100, tick % 100);

  // Animate progress
  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), 200);
    return () => clearInterval(interval);
  }, []);

  // Trigger merge
  useEffect(() => {
    if (!courseTitle || triggered.current) return;
    if (courseRunsInFlight.has(courseTitle)) return;
    courseRunsInFlight.add(courseTitle);
    triggered.current = true;

    async function run() {
      setPhase(0);
      setCurrentStatus("merging_graph");

      try {
        // Phase 0: loading
        setPhase(0);

        // Phase 1-3: merge
        setTimeout(() => setPhase(1), 2000);
        setTimeout(() => setPhase(2), 5000);
        setTimeout(() => setPhase(3), 8000);

        const result = await buildCourseGraph({ course_title: courseTitle });
        setPhase(4);
        setCurrentStatus("graph_ready");

        // Navigate to the resulting workspace
        setTimeout(() => {
          navigate(`/session/${result.session_id}`);
        }, 1200);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        setCurrentStatus("failed");
        toast(`总图谱构建失败: ${msg}`, "error");
      }
    }

    void run().finally(() => courseRunsInFlight.delete(courseTitle));
  }, [courseTitle, navigate, toast]);

  const isDone = currentStatus === "graph_ready";

  return (
    <div className="pipeline-page">
      {/* Hero */}
      <div className="pipeline-hero">
        <div>
          <h1 className="pipeline-h">{courseTitle} · 总图谱</h1>
          <p className="pipeline-hsub">整合所有讲次的知识图谱</p>
        </div>
        {!isDone && currentStatus !== "failed" && currentStatus !== "idle" && (
          <div className="pipeline-live-badge">
            <span className="pipeline-live-dot" />
            正在合并
          </div>
        )}
      </div>

      {/* Stage track */}
      <div className="stage-track">
        {STAGES.map((s, i) => {
          const active = phase === i;
          const done = phase > i;
          return (
            <div key={i} className={clsx("stage", { active, done })}>
              <div className="stage-num">
                {done ? (
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    style={{ display: "inline-block" }}
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : (
                  `0${i + 1}`
                )}
              </div>
              <div className="stage-name">{s.label}</div>
              <div className="stage-detail">
                {active ? s.detail : done ? "完成" : ""}
              </div>
            </div>
          );
        })}
      </div>

      {/* Viz */}
      <div className="pipeline-viz">
        <MergeCanvas phase={phase} progress={progress} />
        <div className="viz-label">COURSE MERGE · LIVE</div>
      </div>

      {/* Error */}
      {currentStatus === "failed" && (
        <div className="pipeline-error">
          {error ?? "合并失败，请重试。"}
        </div>
      )}

      {/* Actions */}
      <div className="pipeline-actions">
        <button
          className="btn btn-ghost"
          onClick={() => navigate("/")}
          type="button"
        >
          返回列表
        </button>
        {currentStatus === "failed" && (
          <button
            className="btn btn-accent"
            onClick={() => {
              triggered.current = false;
              window.location.reload();
            }}
            type="button"
          >
            重试
          </button>
        )}
      </div>
    </div>
  );
}
