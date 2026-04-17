import { Link } from "react-router-dom";
import type { CourseSession } from "../../types";
import { StatusBadge } from "./StatusBadge";
import { formatRelativeTime } from "../../utils/format";
import "./SessionCard.css";

export function SessionCard({ session }: { session: CourseSession }) {
  const { session_id, course_title, lecture_title, status, stats, updated_at } = session;
  const href = status === "graph_ready" || status === "notes_ready"
    ? `/session/${session_id}`
    : `/session/${session_id}/pipeline`;

  return (
    <Link to={href} className="session-card">
      <div className="session-card-meta">
        <span className="session-card-course">{course_title || "未命名课程"}</span>
        <StatusBadge status={status} />
      </div>
      <p className="session-card-title">{lecture_title || "未命名讲座"}</p>
      <div className="session-card-stats">
        <div className="session-stat">
          <span className="session-stat-value">{stats.concept_count}</span>
          <span className="session-stat-label">知识点</span>
        </div>
        <div className="session-stat">
          <span className="session-stat-value">{stats.relation_count}</span>
          <span className="session-stat-label">关系</span>
        </div>
        <div className="session-stat">
          <span className="session-stat-value">{stats.chunk_count}</span>
          <span className="session-stat-label">证据块</span>
        </div>
      </div>
      <p className="session-card-time">{formatRelativeTime(updated_at)} 更新</p>
    </Link>
  );
}
