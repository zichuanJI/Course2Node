import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getSession, ingestPdf, ingestAudio, buildGraph } from "../api/client";
import { useSessionStatus } from "../hooks/useSessionStatus";
import { PipelineSteps } from "../components/pipeline/PipelineSteps";
import { Button } from "../components/primitives/Button";
import { useToast } from "../components/primitives/Toast";
import type { CourseSession } from "../types";
import "./PipelinePage.css";

export function PipelinePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const [session, setSession] = useState<CourseSession | null>(null);
  const triggered = useRef(false);

  const { data: statusData } = useSessionStatus(id ?? null, true);
  const currentStatus = statusData?.status ?? session?.status ?? "uploaded";

  // Load session info once
  useEffect(() => {
    if (!id) return;
    getSession(id).then((s) => setSession(s as CourseSession)).catch(() => {});
  }, [id]);

  // Trigger pipeline once
  useEffect(() => {
    if (!id || triggered.current) return;
    triggered.current = true;

    async function run() {
      const sess = await getSession(id!) as CourseSession;
      setSession(sess);

      // Ingest PDFs
      const pdfs = sess.source_files.filter((f) => f.kind === "pdf" && !f.ingested);
      for (const f of pdfs) {
        try {
          await ingestPdf({ session_id: id!, source_id: f.source_id });
        } catch (e) {
          toast(`PDF 解析失败: ${String(e)}`, "error");
        }
      }

      // Ingest audio
      const audios = sess.source_files.filter((f) => f.kind === "audio" && !f.ingested);
      for (const f of audios) {
        try {
          await ingestAudio({ session_id: id!, source_id: f.source_id });
        } catch (e) {
          toast(`音频解析失败: ${String(e)}`, "error");
        }
      }

      // Build graph
      try {
        await buildGraph({ session_id: id! });
      } catch (e) {
        toast(`图谱构建失败: ${String(e)}`, "error");
      }
    }

    void run();
  }, [id, toast]);

  // Auto-navigate when ready
  useEffect(() => {
    if (currentStatus === "graph_ready" || currentStatus === "notes_ready") {
      navigate(`/session/${id}`);
    }
  }, [currentStatus, id, navigate]);

  return (
    <div className="pipeline-page">
      <div>
        <h1 className="pipeline-heading">{session?.lecture_title ?? "处理中…"}</h1>
        <p className="pipeline-sub">{session?.course_title ?? ""}</p>
      </div>

      <div className="pipeline-card">
        <PipelineSteps status={currentStatus} />
      </div>

      {currentStatus === "failed" && (
        <div className="pipeline-error">
          {statusData?.error_message ?? "处理失败，请重试。"}
        </div>
      )}

      <div className="pipeline-actions">
        <Button variant="ghost" onClick={() => navigate("/")}>返回列表</Button>
        {currentStatus === "failed" && (
          <Button onClick={() => { triggered.current = false; window.location.reload(); }}>
            重试
          </Button>
        )}
      </div>
    </div>
  );
}
