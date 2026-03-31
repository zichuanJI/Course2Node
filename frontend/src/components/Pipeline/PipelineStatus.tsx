import { useEffect, useState } from "react";
import { getSessionStatus } from "../../api/client";
import type { SessionStatus } from "../../types";

const STAGES: SessionStatus[] = [
  "ingesting", "extracting", "aligning", "retrieving", "synthesizing", "review", "done",
];

interface Props {
  sessionId: string;
  onReady: () => void;
}

export function PipelineStatus({ sessionId, onReady }: Props) {
  const [status, setStatus] = useState<SessionStatus>("pending");

  useEffect(() => {
    if (status === "done" || status === "review") {
      onReady();
      return;
    }
    if (status === "failed") return;
    const interval = setInterval(async () => {
      try {
        const data = await getSessionStatus(sessionId);
        setStatus(data.status);
      } catch {
        // transient error – keep polling
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [status, sessionId, onReady]);

  return (
    <div>
      <h3>Processing…</h3>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {STAGES.map(stage => {
          const idx = STAGES.indexOf(stage);
          const currentIdx = STAGES.indexOf(status);
          const state =
            idx < currentIdx ? "done" :
            idx === currentIdx ? "active" :
            "pending";
          return (
            <span
              key={stage}
              style={{
                padding: "4px 10px",
                borderRadius: 4,
                background: state === "done" ? "#b8e0b8" : state === "active" ? "#ffe0a0" : "#eee",
                fontWeight: state === "active" ? 700 : 400,
              }}
            >
              {stage}
            </span>
          );
        })}
      </div>
      {status === "failed" && <p style={{ color: "red" }}>Pipeline failed. Check logs.</p>}
    </div>
  );
}
