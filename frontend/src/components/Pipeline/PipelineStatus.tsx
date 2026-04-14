import { useEffect, useRef, useState } from "react";
import { buildGraph, getSession, ingestAudio, ingestPdf } from "../../api/client";
import type { CourseSession } from "../../types";

interface Props {
  sessionId: string;
  onReady: () => void;
}

type StepState = "pending" | "active" | "done" | "failed";

const STEPS = [
  { key: "inspect", label: "读取上传内容" },
  { key: "ingestPdf", label: "摄取 PDF" },
  { key: "ingestAudio", label: "转写音频" },
  { key: "buildGraph", label: "构建知识点图谱" },
];

export function PipelineStatus({ sessionId, onReady }: Props) {
  const [states, setStates] = useState<Record<string, StepState>>({
    inspect: "pending",
    ingestPdf: "pending",
    ingestAudio: "pending",
    buildGraph: "pending",
  });
  const [message, setMessage] = useState("准备开始处理上传内容。");
  const [error, setError] = useState<string | null>(null);
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) {
      return;
    }
    startedRef.current = true;

    async function run() {
      try {
        setStates((prev) => ({ ...prev, inspect: "active" }));
        const session = await getSession(sessionId) as CourseSession;
        setStates((prev) => ({ ...prev, inspect: "done" }));

        const pdfSources = session.source_files.filter((source) => source.kind === "pdf");
        const audioSources = session.source_files.filter((source) => source.kind === "audio");

        if (pdfSources.length > 0) {
          setStates((prev) => ({ ...prev, ingestPdf: "active" }));
          setMessage("正在解析 PDF 并切分证据块。");
          for (const source of pdfSources) {
            await ingestPdf({ session_id: sessionId, source_id: source.source_id });
          }
          setStates((prev) => ({ ...prev, ingestPdf: "done" }));
        } else {
          setStates((prev) => ({ ...prev, ingestPdf: "done" }));
        }

        if (audioSources.length > 0) {
          setStates((prev) => ({ ...prev, ingestAudio: "active" }));
          setMessage("正在执行音频转写并抽取文本块。");
          for (const source of audioSources) {
            await ingestAudio({ session_id: sessionId, source_id: source.source_id });
          }
          setStates((prev) => ({ ...prev, ingestAudio: "done" }));
        } else {
          setStates((prev) => ({ ...prev, ingestAudio: "done" }));
        }

        setStates((prev) => ({ ...prev, buildGraph: "active" }));
        setMessage("正在抽取知识点、建立关系边并聚类主题。");
        await buildGraph({ session_id: sessionId });
        setStates((prev) => ({ ...prev, buildGraph: "done" }));
        setMessage("图谱构建完成，进入工作台。");
        onReady();
      } catch (unknownError) {
        const text = String(unknownError);
        setError(text);
        setMessage("处理失败。");
        setStates((prev) => {
          const current = { ...prev };
          for (const key of Object.keys(current)) {
            if (current[key] === "active") {
              current[key] = "failed";
            }
          }
          return current;
        });
      }
    }

    void run();
  }, [onReady, sessionId]);

  return (
    <div style={{ display: "grid", gap: 20, maxWidth: 760 }}>
      <div>
        <h2 style={{ margin: "0 0 8px", fontSize: 26 }}>正在构建知识点图谱</h2>
        <p style={{ margin: 0, color: "#6e5847", lineHeight: 1.6 }}>{message}</p>
      </div>

      <div style={{ display: "grid", gap: 12 }}>
        {STEPS.map((step) => {
          const state = states[step.key];
          const palette = {
            pending: "#ede2d3",
            active: "#f7c873",
            done: "#9dd9c3",
            failed: "#ef9a9a",
          } as const;

          return (
            <div
              key={step.key}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "14px 16px",
                borderRadius: 14,
                background: palette[state],
                color: "#2f2419",
              }}
            >
              <span>{step.label}</span>
              <strong style={{ textTransform: "capitalize" }}>{state}</strong>
            </div>
          );
        })}
      </div>

      {error ? <p style={{ margin: 0, color: "#9d2c2c" }}>{error}</p> : null}
    </div>
  );
}
