import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import clsx from "clsx";
import { buildCourseGraph, deleteSession, getCourseSession, getRuntimeSettings, listSessions, updateRuntimeSettings } from "../api/client";
import type { CourseSession, RuntimeSettingField, RuntimeSettingsResponse, SessionStatus } from "../types";
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

function TrashIcon() {
  return <span className="trash-icon" aria-hidden="true" />;
}

// ── StatusChip ────────────────────────────────────────────────────────────────
const STATUS_MAP: Record<SessionStatus, { cls: string; label: string }> = {
  draft:       { cls: "chip",       label: "草稿" },
  uploaded:    { cls: "chip chip-info",  label: "已上传" },
  ingesting:   { cls: "chip chip-live",  label: "解析中" },
  building_graph: { cls: "chip chip-live", label: "构建图谱中" },
  merging_graph:  { cls: "chip chip-live", label: "合并图谱中" },
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

type SettingsGroupDefinition = {
  id: string;
  title: string;
  description: string;
  badge: string;
  defaultOpen: boolean;
  keys: string[];
};

type OrderedSettingsGroup = SettingsGroupDefinition & {
  fields: RuntimeSettingField[];
};

const SETTINGS_GROUP_DEFINITIONS: SettingsGroupDefinition[] = [
  {
    id: "kimi-pdf",
    title: "解析",
    description: "PDF 解析链路使用，影响课件上传后的文本提取质量。",
    badge: "核心",
    defaultOpen: false,
    keys: ["KIMI_BASE_URL", "KIMI_API_KEY", "KIMI_MODEL"],
  },
  {
    id: "embedding",
    title: "Embedding",
    description: "检索和概念匹配使用；本地模型优先，云端参数按需填写。",
    badge: "核心",
    defaultOpen: false,
    keys: [
      "EMBED_PROVIDER",
      "EMBEDDING_LOCAL_MODEL_NAME",
      "EMBEDDING_BASE_URL",
      "EMBEDDING_API_KEY",
      "EMBEDDING_MODEL",
      "OPENAI_API_KEY",
    ],
  },
  {
    id: "graph-llm",
    title: "图谱/笔记 LLM",
    description: "知识图谱、笔记生成和默认模型回退链路使用。",
    badge: "核心",
    defaultOpen: false,
    keys: ["GRAPH_LLM_BASE_URL", "GRAPH_LLM_API_KEY", "GRAPH_LLM_MODEL"],
  },
  {
    id: "chat-llm",
    title: "对话 LLM",
    description: "额外功能：直接对话和题目追问使用；未单独配置时会回退到图谱/笔记 LLM。",
    badge: "额外功能",
    defaultOpen: false,
    keys: ["CHAT_LLM_BASE_URL", "CHAT_LLM_API_KEY", "CHAT_LLM_MODEL"],
  },
  {
    id: "exam-llm",
    title: "出卷 LLM",
    description: "额外功能：只在需要单独控制出卷模型时填写。",
    badge: "额外功能",
    defaultOpen: false,
    keys: ["EXAM_LLM_BASE_URL", "EXAM_LLM_API_KEY", "EXAM_LLM_MODEL"],
  },
  {
    id: "audio-asr",
    title: "音频 ASR",
    description: "额外功能：只在解析音频或视频转写时使用。",
    badge: "额外功能",
    defaultOpen: false,
    keys: ["WHISPER_MODEL_SIZE", "WHISPER_LANGUAGE", "FASTER_WHISPER_PYTHON_PATH"],
  },
];

function matchFilter(status: SessionStatus, filter: FilterGroup): boolean {
  if (filter === "all") return true;
  if (filter === "ready") return status === "notes_ready" || status === "graph_ready";
  if (filter === "processing") return status === "ingesting" || status === "building_graph" || status === "merging_graph" || status === "uploaded" || status === "draft";
  if (filter === "failed") return status === "failed";
  return true;
}

function sessionHref(session: CourseSession): string {
  if (session.status === "graph_ready" || session.status === "notes_ready") {
    return `/session/${session.session_id}`;
  }
  return `/session/${session.session_id}/pipeline`;
}

// ── ConfirmModal ──────────────────────────────────────────────────────────────
function ConfirmModal({
  message,
  onConfirm,
  onCancel,
  loading,
}: {
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading: boolean;
}) {
  return (
    <div className="confirm-overlay" onClick={() => !loading && onCancel()}>
      <div className="confirm-dialog" onClick={(e) => e.stopPropagation()}>
        <p className="confirm-message">{message}</p>
        <div className="confirm-actions">
          <button className="btn btn-outline btn-sm" onClick={onCancel} disabled={loading} type="button">
            取消
          </button>
          <button className="btn btn-danger btn-sm" onClick={onConfirm} disabled={loading} type="button">
            {loading ? "删除中…" : "确认删除"}
          </button>
        </div>
      </div>
    </div>
  );
}

function DeploymentSettingsModal({
  onClose,
}: {
  onClose: () => void;
}) {
  const [settingsPayload, setSettingsPayload] = useState<RuntimeSettingsResponse | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const toast = useToast();

  useEffect(() => {
    getRuntimeSettings()
      .then((payload) => {
        setSettingsPayload(payload);
        setDraft(Object.fromEntries(payload.fields.map((field) => [field.key, field.value])));
      })
      .catch(() => toast("加载部署设置失败", "error"))
      .finally(() => setLoading(false));
  }, [toast]);

  async function handleSave() {
    if (!settingsPayload) return;
    setSaving(true);
    try {
      const values = Object.fromEntries(
        settingsPayload.fields.map((field) => [field.key, draft[field.key] ?? ""]),
      );
      const updated = await updateRuntimeSettings(values);
      setSettingsPayload(updated);
      setDraft(Object.fromEntries(updated.fields.map((field) => [field.key, field.value])));
      toast("部署设置已保存到后端 .env", "success");
    } catch (error) {
      toast(error instanceof Error ? `保存失败：${error.message}` : "保存失败", "error");
    } finally {
      setSaving(false);
    }
  }

  async function copyCommand(command: string) {
    try {
      await navigator.clipboard.writeText(command);
      toast("命令已复制", "success");
    } catch {
      toast("复制失败", "error");
    }
  }

  const groups = useMemo(() => buildSettingsGroups(settingsPayload?.fields ?? []), [settingsPayload]);

  useEffect(() => {
    if (groups.length === 0) return;
    setOpenGroups((current) => {
      let changed = false;
      const next = { ...current };
      for (const group of groups) {
        if (!(group.id in next)) {
          next[group.id] = group.defaultOpen;
          changed = true;
        }
      }
      return changed ? next : current;
    });
  }, [groups]);

  const whisperModel = draft.WHISPER_MODEL_SIZE || "base";
  const whisperCommand = `python -c "import whisper; whisper.load_model('${whisperModel}')"`;
  const fasterWhisperCommand = `python -c "from faster_whisper import WhisperModel; WhisperModel('${whisperModel}')"`;

  return (
    <div className="settings-overlay" onClick={() => !saving && onClose()}>
      <div className="settings-dialog" onClick={(event) => event.stopPropagation()}>
        <div className="settings-head">
          <div>
            <p className="settings-kicker">DEPLOYMENT</p>
            <h2>部署设置</h2>
            <p>写入后端本地 .env，用于迁移部署时快速配置 API Key 与模型参数。</p>
          </div>
          <button className="settings-close" type="button" onClick={onClose} disabled={saving} aria-label="关闭设置">
            ×
          </button>
        </div>

        {loading ? (
          <div className="settings-loading">加载设置中…</div>
        ) : (
          <>
            {settingsPayload?.warnings.map((warning) => (
              <div className="settings-warning" key={warning}>{warning}</div>
            ))}

            <div className="settings-list">
              {groups.map((group) => {
                const isOpen = openGroups[group.id] ?? group.defaultOpen;
                const contentId = `settings-group-${group.id}`;

                return (
                  <section className={clsx("settings-group", isOpen && "is-open")} key={group.id}>
                    <button
                      className="settings-group-toggle"
                      type="button"
                      onClick={() => setOpenGroups((current) => ({ ...current, [group.id]: !isOpen }))}
                      aria-expanded={isOpen}
                      aria-controls={contentId}
                    >
                      <span className="settings-group-caret" aria-hidden="true" />
                      <span className="settings-group-copy">
                        <span className="settings-group-title">
                          {group.title}
                          <em>{group.badge}</em>
                        </span>
                        <span className="settings-group-description">{group.description}</span>
                      </span>
                      <span className="settings-group-count">{group.fields.length} 项</span>
                    </button>

                    {isOpen && (
                      <div className="settings-row-list" id={contentId}>
                        {group.fields.map((field) => (
                          <label className="settings-row" key={field.key}>
                            <span className="settings-row-copy">
                              <span className="settings-row-title">
                                {field.label}
                                {field.secret && field.configured && <em>已配置</em>}
                                {field.help_url && (
                                  <a href={field.help_url} target="_blank" rel="noreferrer">
                                    文档
                                  </a>
                                )}
                              </span>
                              <span className="settings-row-key">{field.key}</span>
                            </span>
                            <input
                              type={field.secret ? "password" : "text"}
                              value={draft[field.key] ?? ""}
                              placeholder={field.secret && field.configured ? "留空则不修改当前密钥" : field.placeholder}
                              onChange={(event) => setDraft((current) => ({ ...current, [field.key]: event.target.value }))}
                              autoComplete="off"
                            />
                          </label>
                        ))}

                        {group.id === "audio-asr" && (
                          <div className="settings-extra-tools">
                            <div className="settings-link-row">
                              <a href="https://huggingface.co/openai/whisper-base" target="_blank" rel="noreferrer">OpenAI Whisper 模型</a>
                              <a href="https://huggingface.co/collections/Systran/faster-whisper" target="_blank" rel="noreferrer">Systran faster-whisper 模型</a>
                            </div>
                            <div className="settings-command-list">
                              <button type="button" onClick={() => copyCommand(whisperCommand)}>
                                <code>{whisperCommand}</code>
                              </button>
                              <button type="button" onClick={() => copyCommand(fasterWhisperCommand)}>
                                <code>{fasterWhisperCommand}</code>
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </section>
                );
              })}
            </div>

            <div className="settings-actions">
              <button className="btn btn-outline btn-sm" type="button" onClick={onClose} disabled={saving}>
                取消
              </button>
              <button className="btn btn-accent btn-sm" type="button" onClick={handleSave} disabled={saving}>
                {saving ? "保存中…" : "保存设置"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function buildSettingsGroups(fields: RuntimeSettingField[]): OrderedSettingsGroup[] {
  const fieldsByKey = new Map(fields.map((field) => [field.key, field]));
  const usedKeys = new Set<string>();
  const orderedGroups = SETTINGS_GROUP_DEFINITIONS.map((definition) => {
    const groupFields = definition.keys.flatMap((key) => {
      const field = fieldsByKey.get(key);
      if (!field) return [];
      usedKeys.add(key);
      return [field];
    });
    return { ...definition, fields: groupFields };
  }).filter((group) => group.fields.length > 0);

  const leftoverGroups = new Map<string, RuntimeSettingField[]>();
  for (const field of fields) {
    if (usedKeys.has(field.key)) continue;
    const group = leftoverGroups.get(field.group) ?? [];
    group.push(field);
    leftoverGroups.set(field.group, group);
  }

  for (const [groupName, groupFields] of leftoverGroups) {
    orderedGroups.push({
      id: `other-${groupName}`,
      title: groupName,
      description: "补充配置项。",
      badge: "补充",
      defaultOpen: false,
      keys: groupFields.map((field) => field.key),
      fields: groupFields,
    });
  }

  return orderedGroups;
}

// ── CourseGraphButtons ────────────────────────────────────────────────────────
function CourseGraphButtons({ course, sessions }: { course: string; sessions: CourseSession[] }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [courseSessionId, setCourseSessionId] = useState<string | null>(null);
  const [courseSessionStatus, setCourseSessionStatus] = useState<SessionStatus | null>(null);
  const [loading, setLoading] = useState(false);

  const hasGraphReady = sessions.some(
    (s) => s.status === "graph_ready" || s.status === "notes_ready",
  );

  useEffect(() => {
    if (!hasGraphReady) return;
    getCourseSession(course)
      .then((s) => {
        setCourseSessionId(s.session_id);
        setCourseSessionStatus(s.status);
      })
      .catch(() => {
        setCourseSessionId(null);
        setCourseSessionStatus(null);
      });
  }, [course, hasGraphReady]);

  const courseGraphReady =
    courseSessionStatus === "graph_ready" || courseSessionStatus === "notes_ready";

  function handleGraphClick(e: React.MouseEvent) {
    e.stopPropagation();
    if (loading) return;
    if (courseGraphReady && courseSessionId) {
      navigate(`/session/${courseSessionId}`);
    } else {
      navigate(`/course/${encodeURIComponent(course)}/pipeline`);
    }
  }

  async function handleRebuildClick(e: React.MouseEvent) {
    e.stopPropagation();
    if (loading) return;
    setLoading(true);
    try {
      const result = await buildCourseGraph({ course_title: course });
      setCourseSessionId(result.session_id);
      setCourseSessionStatus("graph_ready");
      toast(`总图谱已重新生成：${result.concept_count} 概念，${result.edge_count} 关系`, "success");
    } catch (err) {
      toast(`重新生成失败：${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setLoading(false);
    }
  }

  function handleNotesClick(e: React.MouseEvent) {
    e.stopPropagation();
    if (!courseGraphReady || !courseSessionId) {
      toast("请先生成总图谱", "error");
      return;
    }
    navigate(`/session/${courseSessionId}`);
  }

  return (
    <div className="course-graph-buttons">
      <button
        className={clsx("btn btn-icon course-action-btn", {
          "course-action-btn-ready": courseGraphReady,
        })}
        onClick={handleGraphClick}
        disabled={!hasGraphReady || loading}
        title={courseGraphReady ? "查看总图谱" : "生成总图谱"}
        type="button"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <circle cx="5" cy="5" r="2" />
          <circle cx="19" cy="5" r="2" />
          <circle cx="5" cy="19" r="2" />
          <circle cx="19" cy="19" r="2" />
          <path d="m7 7 3 3m4 0 3-3m0 10-3-3m-4 0-3 3" />
        </svg>
      </button>
      {courseGraphReady && (
        <button
          className="btn btn-icon course-action-btn"
          onClick={handleRebuildClick}
          disabled={loading}
          title={loading ? "重新生成中…" : "重新生成总图谱"}
          type="button"
        >
          <svg
            width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            className={loading ? "spin-icon" : ""}
          >
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
        </button>
      )}
      <button
        className={clsx("btn btn-icon course-action-btn", {
          "course-action-btn-ready": courseGraphReady,
        })}
        onClick={handleNotesClick}
        disabled={!courseGraphReady}
        title={courseGraphReady ? "查看总笔记" : "需先生成总图谱"}
        type="button"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14,2 14,8 20,8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
        </svg>
      </button>
    </div>
  );
}

// ── HomePage ──────────────────────────────────────────────────────────────────
export function HomePage() {
  const [sessions, setSessions] = useState<CourseSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<FilterGroup>("all");
  const [courseFilter, setCourseFilter] = useState<string>("all");
  const [pending, setPending] = useState<{ label: string; onConfirm: () => Promise<void> } | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const toast = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    listSessions()
      .then((data) => setSessions(data.sort((a, b) => b.updated_at.localeCompare(a.updated_at))))
      .catch(() => toast("加载会话列表失败", "error"))
      .finally(() => setLoading(false));
  }, [toast]);

  const handleDeleteSession = (session: CourseSession) => {
    setPending({
      label: `确认删除「${session.lecture_title}」？此操作不可撤销。`,
      onConfirm: async () => {
        await deleteSession(session.session_id);
        setSessions((prev) => prev.filter((s) => s.session_id !== session.session_id));
        toast("已删除", "success");
      },
    });
  };

  const handleDeleteCourse = (courseTitle: string) => {
    const count = sessions.filter((s) => s.course_title === courseTitle).length;
    setPending({
      label: `确认删除课程「${courseTitle}」中的全部 ${count} 讲？此操作不可撤销。`,
      onConfirm: async () => {
        const toDelete = sessions.filter((s) => s.course_title === courseTitle);
        await Promise.all(toDelete.map((s) => deleteSession(s.session_id)));
        setSessions((prev) => prev.filter((s) => s.course_title !== courseTitle));
        toast("课程已删除", "success");
      },
    });
  };

  const confirmDelete = async () => {
    if (!pending) return;
    setDeleting(true);
    try {
      await pending.onConfirm();
      setPending(null);
    } catch {
      toast("删除失败，请重试", "error");
    } finally {
      setDeleting(false);
    }
  };

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
      // Hide virtual course-graph sessions from the normal list
      if (s.lecture_title.startsWith("[总图谱] ")) return false;
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
        <div className="home-head-actions">
          <button
            className="btn btn-outline"
            onClick={() => setSettingsOpen(true)}
            type="button"
          >
            部署设置
          </button>
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
                <CourseGraphButtons course={course} sessions={rows} />
                <button
                  className="btn btn-icon group-delete-btn"
                  onClick={(e) => { e.stopPropagation(); handleDeleteCourse(course); }}
                  aria-label={`删除课程 ${course}`}
                  title="删除整个课程"
                  type="button"
                >
                  <TrashIcon />
                </button>
              </div>
              {rows.map((s) => (
                <SessionRow
                  key={s.session_id}
                  session={s}
                  onClick={() => navigate(sessionHref(s))}
                  onDelete={() => handleDeleteSession(s)}
                />
              ))}
            </div>
          ))}
        </div>
      )}

      {pending && (
        <ConfirmModal
          message={pending.label}
          onConfirm={confirmDelete}
          onCancel={() => !deleting && setPending(null)}
          loading={deleting}
        />
      )}

      {settingsOpen && <DeploymentSettingsModal onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}

function SessionRow({ session: s, onClick, onDelete }: { session: CourseSession; onClick: () => void; onDelete: () => void }) {
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

      <button
        className="btn btn-icon row-delete-btn"
        onClick={(e) => { e.stopPropagation(); onDelete(); }}
        aria-label="删除此讲"
        title="删除此讲"
        type="button"
      >
        <TrashIcon />
      </button>

      <svg className="session-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="m9 18 6-6-6-6" />
      </svg>
    </div>
  );
}
