import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listSessions } from "../api/client";
import type { CourseSession } from "../types";
import { SessionCard } from "../components/sessions/SessionCard";
import { EmptyState } from "../components/primitives/EmptyState";
import { Skeleton } from "../components/primitives/Skeleton";
import { Button } from "../components/primitives/Button";
import { useToast } from "../components/primitives/Toast";
import "./HomePage.css";

export function HomePage() {
  const [sessions, setSessions] = useState<CourseSession[]>([]);
  const [loading, setLoading] = useState(true);
  const toast = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    listSessions()
      .then((data) => setSessions(data.sort((a, b) => b.updated_at.localeCompare(a.updated_at))))
      .catch(() => toast("加载会话列表失败", "error"))
      .finally(() => setLoading(false));
  }, [toast]);

  return (
    <div className="home-page">
      <div className="home-page-header">
        <h1 className="home-page-heading">我的课程</h1>
        <Button onClick={() => navigate("/new")}>新建课程</Button>
      </div>

      {loading ? (
        <div className="session-grid">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} height={160} />
          ))}
        </div>
      ) : sessions.length === 0 ? (
        <EmptyState
          icon="📚"
          title="还没有任何课程"
          description="上传你的第一节课 PDF 或录音，开始构建知识点图谱。"
          action={<Button onClick={() => navigate("/new")}>上传第一节课</Button>}
        />
      ) : (
        <div className="session-grid">
          {sessions.map((s) => (
            <SessionCard key={s.session_id} session={s} />
          ))}
        </div>
      )}
    </div>
  );
}
