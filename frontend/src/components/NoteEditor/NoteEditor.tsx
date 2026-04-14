import { useEffect, useState } from "react";
import { exportNote, fetchSubgraph, generateNotes, getSession, searchGraph } from "../../api/client";
import type { CourseSession, NoteDocument, SearchResponse, SubgraphResponse } from "../../types";

interface Props {
  sessionId: string;
}

export function NoteEditor({ sessionId }: Props) {
  const [session, setSession] = useState<CourseSession | null>(null);
  const [query, setQuery] = useState("");
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [subgraph, setSubgraph] = useState<SubgraphResponse | null>(null);
  const [note, setNote] = useState<NoteDocument | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadSession() {
      try {
        const data = await getSession(sessionId) as CourseSession;
        setSession(data);
      } catch (unknownError) {
        setError(String(unknownError));
      }
    }
    void loadSession();
  }, [sessionId]);

  async function handleSearch(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await searchGraph({ session_id: sessionId, query, limit: 8 });
      setSearchResult(result);
      if (result.concepts.length > 0) {
        const graphResult = await fetchSubgraph(sessionId, result.concepts[0].concept_id, 2);
        setSubgraph(graphResult);
      } else {
        setSubgraph(null);
      }
    } catch (unknownError) {
      setError(String(unknownError));
    } finally {
      setLoading(false);
    }
  }

  async function focusConcept(conceptId: string) {
    setError(null);
    try {
      const graphResult = await fetchSubgraph(sessionId, conceptId, 2);
      setSubgraph(graphResult);
    } catch (unknownError) {
      setError(String(unknownError));
    }
  }

  async function handleGenerateNotes() {
    if (!query.trim()) {
      setError("先输入一个主题或问题。");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const selectedConceptId = subgraph?.center_concept_id;
      const result = await generateNotes({
        session_id: sessionId,
        topic: query,
        concept_ids: selectedConceptId ? [selectedConceptId] : [],
      });
      setNote(result);
    } catch (unknownError) {
      setError(String(unknownError));
    } finally {
      setLoading(false);
    }
  }

  async function handleExport(fmt: "markdown" | "tex" | "txt") {
    try {
      const content = await exportNote(sessionId, fmt);
      const blob = new Blob([content], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${session?.lecture_title ?? "course2node"}.${fmt === "markdown" ? "md" : fmt}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (unknownError) {
      setError(String(unknownError));
    }
  }

  return (
    <div style={{ display: "grid", gap: 24 }}>
      <header style={{ display: "grid", gap: 8 }}>
        <h1 style={{ margin: 0, fontSize: 34 }}>{session?.lecture_title ?? "Course2Node"}</h1>
        <p style={{ margin: 0, color: "#6e5847" }}>
          {session?.course_title ?? ""} · {session?.stats.concept_count ?? 0} 个知识点 · {session?.stats.relation_count ?? 0} 条关系
        </p>
      </header>

      <form onSubmit={handleSearch} style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索一个知识点，例如：梯度下降 / 贝叶斯 / 监督学习"
          style={{
            flex: "1 1 360px",
            minWidth: 280,
            padding: "14px 16px",
            borderRadius: 999,
            border: "1px solid #d8c8b7",
            background: "#fffdf8",
            fontSize: 15,
          }}
        />
        <button
          type="submit"
          disabled={loading}
          style={{
            padding: "12px 18px",
            borderRadius: 999,
            border: "none",
            background: "#1f5f4a",
            color: "#fff",
            cursor: "pointer",
          }}
        >
          {loading ? "处理中…" : "搜索图谱"}
        </button>
        <button
          type="button"
          onClick={handleGenerateNotes}
          disabled={loading}
          style={{
            padding: "12px 18px",
            borderRadius: 999,
            border: "1px solid #1f5f4a",
            background: "#f3fbf7",
            color: "#1f5f4a",
            cursor: "pointer",
          }}
        >
          生成笔记
        </button>
      </form>

      {error ? <p style={{ margin: 0, color: "#9d2c2c" }}>{error}</p> : null}

      <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 360px) 1fr", gap: 20 }}>
        <section
          style={{
            padding: 20,
            borderRadius: 20,
            background: "#fff9f1",
            border: "1px solid #e8d9c9",
            minHeight: 420,
          }}
        >
          <h2 style={{ marginTop: 0 }}>搜索结果</h2>
          {searchResult?.concepts.length ? (
            <div style={{ display: "grid", gap: 12 }}>
              {searchResult.concepts.map((concept) => (
                <button
                  key={concept.concept_id}
                  type="button"
                  onClick={() => void focusConcept(concept.concept_id)}
                  style={{
                    textAlign: "left",
                    borderRadius: 14,
                    border: "1px solid #d7c6b5",
                    background: "#fff",
                    padding: 14,
                    cursor: "pointer",
                  }}
                >
                  <strong>{concept.name}</strong>
                  <div style={{ marginTop: 6, fontSize: 13, color: "#6e5847" }}>
                    score {concept.score.toFixed(3)} · {concept.source_count} 个来源
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <p style={{ color: "#6e5847" }}>先搜索一个主题，左侧会列出最相关的知识点。</p>
          )}

          {searchResult?.chunks.length ? (
            <div style={{ marginTop: 20, display: "grid", gap: 10 }}>
              <h3 style={{ margin: 0 }}>证据片段</h3>
              {searchResult.chunks.slice(0, 4).map((chunk) => (
                <div
                  key={chunk.chunk_id}
                  style={{
                    padding: 12,
                    borderRadius: 12,
                    background: "#fff",
                    border: "1px solid #e9ddd1",
                    fontSize: 13,
                    lineHeight: 1.6,
                  }}
                >
                  <div style={{ color: "#876b57", marginBottom: 6 }}>
                    {chunk.source_type === "pdf"
                      ? `PDF p.${chunk.page_start ?? "?"}`
                      : `Audio ${formatTime(chunk.time_start)}-${formatTime(chunk.time_end)}`}
                  </div>
                  <div>{chunk.text}</div>
                </div>
              ))}
            </div>
          ) : null}
        </section>

        <section
          style={{
            padding: 20,
            borderRadius: 20,
            background: "#f5fbff",
            border: "1px solid #d0dfe8",
            minHeight: 420,
          }}
        >
          <h2 style={{ marginTop: 0 }}>知识点关系图</h2>
          {subgraph ? (
            <div style={{ display: "grid", gap: 16 }}>
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                {subgraph.nodes.map((node) => (
                  <div
                    key={node.id}
                    style={{
                      padding: "10px 14px",
                      borderRadius: 999,
                      background: node.id === subgraph.center_concept_id ? "#1f5f4a" : "#fff",
                      color: node.id === subgraph.center_concept_id ? "#fff" : "#28424e",
                      border: "1px solid #b8ced8",
                    }}
                  >
                    {node.label}
                  </div>
                ))}
              </div>

              <div style={{ display: "grid", gap: 10 }}>
                {subgraph.edges.map((edge, index) => (
                  <div
                    key={`${edge.source}-${edge.target}-${index}`}
                    style={{
                      padding: 12,
                      borderRadius: 12,
                      background: "#fff",
                      border: "1px solid #dae8ef",
                      fontSize: 14,
                    }}
                  >
                    <strong>{labelOf(subgraph, edge.source)}</strong> → <strong>{labelOf(subgraph, edge.target)}</strong>
                    <div style={{ marginTop: 4, color: "#557280" }}>
                      {edge.edge_type}
                      {edge.properties.relation_type ? ` · ${String(edge.properties.relation_type)}` : ""}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p style={{ color: "#6e5847" }}>点击左侧知识点后，这里会展开它的局部关系图。</p>
          )}
        </section>
      </div>

      <section
        style={{
          padding: 20,
          borderRadius: 20,
          background: "#fff",
          border: "1px solid #e7dccf",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div>
            <h2 style={{ margin: 0 }}>结构化笔记</h2>
            <p style={{ margin: "6px 0 0", color: "#6e5847" }}>基于当前主题和知识点，生成带来源证据的课程笔记。</p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" onClick={() => void handleExport("markdown")} disabled={!note}>导出 Markdown</button>
            <button type="button" onClick={() => void handleExport("txt")} disabled={!note}>导出 TXT</button>
            <button type="button" onClick={() => void handleExport("tex")} disabled={!note}>导出 TeX</button>
          </div>
        </div>

        {note ? (
          <div style={{ marginTop: 20, display: "grid", gap: 18 }}>
            <blockquote
              style={{
                margin: 0,
                padding: "14px 18px",
                borderLeft: "4px solid #1f5f4a",
                background: "#f5fbf7",
              }}
            >
              {note.summary}
            </blockquote>
            {note.sections.map((section) => (
              <article key={section.section_id} style={{ display: "grid", gap: 10 }}>
                <h3 style={{ margin: 0 }}>{section.title}</h3>
                <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>{section.content_md}</div>
                {section.references.length ? (
                  <div style={{ display: "grid", gap: 6, color: "#6e5847", fontSize: 13 }}>
                    {section.references.map((reference, index) => (
                      <div key={`${reference.source_id}-${index}`}>
                        {reference.source_type === "pdf" ? "PDF" : "Audio"} · {reference.locator} · {reference.snippet}
                      </div>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <p style={{ marginTop: 20, color: "#6e5847" }}>先搜索一个主题，再点击“生成笔记”。</p>
        )}
      </section>
    </div>
  );
}

function labelOf(subgraph: SubgraphResponse, id: string) {
  return subgraph.nodes.find((node) => node.id === id)?.label ?? id;
}

function formatTime(value?: number | null) {
  if (value == null) {
    return "00:00";
  }
  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}
