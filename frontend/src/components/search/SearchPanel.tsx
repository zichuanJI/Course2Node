import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getGraph, searchGraph } from "../../api/client";
import { Input } from "../primitives/Input";
import { Pill } from "../primitives/Pill";
import { useDebouncedCallback } from "../../hooks/useDebouncedCallback";
import { useLocalStorage } from "../../hooks/useLocalStorage";
import type { ConceptNode, SearchResponse } from "../../types";
import "./SearchPanel.css";

type FilterKind = "all" | "concepts" | "chunks";
type SourceFilter = "all" | "pdf" | "audio";

interface EvidenceListItem {
  key: string;
  conceptId: string;
  conceptName: string;
  sourceType: "pdf" | "audio";
  locator: string;
  snippet: string;
}

function conceptMatchesSource(concept: ConceptNode, source: SourceFilter) {
  return source === "all" || concept.evidence_refs.some((ref) => ref.source_type === source);
}

function conceptEvidenceCount(concept: ConceptNode, source: SourceFilter) {
  return source === "all"
    ? concept.evidence_refs.length
    : concept.evidence_refs.filter((ref) => ref.source_type === source).length;
}

function conceptSourceLabel(concept: ConceptNode) {
  const sources = new Set(concept.evidence_refs.map((ref) => ref.source_type));
  if (sources.has("pdf") && sources.has("audio")) return "PDF+音频";
  if (sources.has("pdf")) return "PDF";
  if (sources.has("audio")) return "音频";
  return "无来源";
}

function sourceLabel(sourceType: "pdf" | "audio") {
  return sourceType === "pdf" ? "PDF" : "音频";
}

export function SearchPanel({ sessionId }: { sessionId: string }) {
  const [, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [filterKind, setFilterKind] = useState<FilterKind>("all");
  const [filterSource, setFilterSource] = useState<SourceFilter>("all");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [conceptsList, setConceptsList] = useState<ConceptNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [recentQueries, setRecentQueries] = useLocalStorage<string[]>(
    `c2n:recent:${sessionId}`,
    [],
  );
  const latestQuery = useRef("");

  const conceptById = useMemo(
    () => new Map(conceptsList.map((concept) => [concept.concept_id, concept])),
    [conceptsList],
  );

  const filteredConceptsList = useMemo(
    () => conceptsList.filter((concept) => conceptMatchesSource(concept, filterSource)),
    [conceptsList, filterSource],
  );

  const evidenceList = useMemo(() => {
    const items: EvidenceListItem[] = [];
    const seen = new Set<string>();

    for (const concept of conceptsList) {
      for (const ref of concept.evidence_refs) {
        if (filterSource !== "all" && ref.source_type !== filterSource) continue;
        const key = ref.chunk_id || `${concept.concept_id}:${ref.locator}`;
        if (seen.has(key)) continue;
        seen.add(key);
        items.push({
          key,
          conceptId: concept.concept_id,
          conceptName: concept.name,
          sourceType: ref.source_type,
          locator: ref.locator,
          snippet: ref.snippet || concept.summary || concept.definition,
        });
      }
    }

    return items;
  }, [conceptsList, filterSource]);

  useEffect(() => {
    getGraph(sessionId)
      .then((graph) => {
        setConceptsList(
          [...graph.concepts].sort((a, b) => b.importance_score - a.importance_score),
        );
      })
      .catch(() => setConceptsList([]));
  }, [sessionId]);

  const doSearch = useCallback(
    async (q: string) => {
      if (!q.trim()) { setResults(null); return; }
      setLoading(true);
      try {
        const res = await searchGraph({ session_id: sessionId, query: q, limit: 12 });
        if (q === latestQuery.current) setResults(res);
      } catch {
        // silent
      } finally {
        setLoading(false);
      }
    },
    [sessionId],
  );

  const debouncedSearch = useDebouncedCallback(doSearch, 300);

  function handleInput(value: string) {
    setQuery(value);
    latestQuery.current = value;
    debouncedSearch(value);
  }

  function handleSubmit() {
    if (!query.trim()) return;
    doSearch(query);
    setRecentQueries([query, ...recentQueries.filter((q) => q !== query)].slice(0, 8));
  }

  const concepts = results?.concepts.filter((c) => {
    if (filterSource === "all") return true;
    const concept = conceptById.get(c.concept_id);
    return concept ? conceptMatchesSource(concept, filterSource) : false;
  }) ?? [];

  const chunks = results?.chunks.filter((c) => {
    if (filterSource === "pdf") return c.source_type === "pdf";
    if (filterSource === "audio") return c.source_type === "audio";
    return true;
  }) ?? [];

  const showConceptResults = filterKind !== "chunks";
  const showChunkResults = filterKind !== "concepts";
  const visibleSearchResultCount =
    (showConceptResults ? concepts.length : 0) + (showChunkResults ? chunks.length : 0);

  return (
    <div className="search-panel">
      <div className="search-input-row">
        <Input
          placeholder="搜索知识点、内容…"
          value={query}
          onChange={(e) => handleInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
        />
      </div>

      <div className="search-filters">
        {(["all", "concepts", "chunks"] as FilterKind[]).map((k) => (
          <Pill key={k} active={filterKind === k} onClick={() => setFilterKind(k)}>
            {{ all: "全部", concepts: "知识点", chunks: "内容片段" }[k]}
          </Pill>
        ))}
        <span style={{ flexBasis: "100%", height: 0 }} />
        {(["all", "pdf", "audio"] as SourceFilter[]).map((s) => (
          <Pill key={s} active={filterSource === s} onClick={() => setFilterSource(s)}>
            {{ all: "全部来源", pdf: "PDF", audio: "音频" }[s]}
          </Pill>
        ))}
      </div>

      {!query && filterKind !== "chunks" && (
        <div className="concept-list">
          <div className="search-section-label">知识点列表 ({filteredConceptsList.length})</div>
          {filteredConceptsList.map((concept) => (
            <button
              key={concept.concept_id}
              className="concept-list-row"
              onClick={() => setSearchParams({ concept: concept.concept_id })}
              type="button"
            >
              <span className="concept-list-name">{concept.name}</span>
              <span className="concept-list-meta">
                {Math.round(concept.importance_score * 100)} · {conceptEvidenceCount(concept, filterSource)} 证据 · {conceptSourceLabel(concept)}
              </span>
            </button>
          ))}
          {filteredConceptsList.length === 0 && (
            <p style={{ fontFamily: "var(--font-ui)", fontSize: 13, color: "var(--control-text-color)" }}>
              没有符合筛选条件的知识点
            </p>
          )}
        </div>
      )}

      {!query && filterKind !== "concepts" && (
        <div className="concept-list">
          <div className="search-section-label">内容片段 ({evidenceList.length})</div>
          {evidenceList.map((item) => (
            <button
              key={item.key}
              className="concept-list-row concept-list-row-chunk"
              onClick={() => setSearchParams({ concept: item.conceptId })}
              type="button"
            >
              <span className="concept-list-name">{item.snippet || "无可显示片段"}</span>
              <span className="concept-list-meta">
                {sourceLabel(item.sourceType)}{item.locator ? ` · ${item.locator}` : ""} · {item.conceptName}
              </span>
            </button>
          ))}
          {evidenceList.length === 0 && (
            <p style={{ fontFamily: "var(--font-ui)", fontSize: 13, color: "var(--control-text-color)" }}>
              没有符合筛选条件的内容片段
            </p>
          )}
        </div>
      )}

      {!query && recentQueries.length > 0 && (
        <div className="search-recent">
          <span className="search-recent-label">最近搜索</span>
          {recentQueries.map((q) => (
            <Pill key={q} onClick={() => { setQuery(q); latestQuery.current = q; doSearch(q); }}>
              {q}
            </Pill>
          ))}
        </div>
      )}

      {loading && <p style={{ fontFamily: "var(--font-ui)", fontSize: 13, color: "var(--control-text-color)" }}>搜索中…</p>}

      {results && (
        <div className="search-results">
          {showConceptResults && concepts.length > 0 && (
            <div>
              <div className="search-section-label">知识点 ({concepts.length})</div>
              {concepts.map((c) => (
                <div
                  key={c.concept_id}
                  className="search-concept-hit"
                  onClick={() => setSearchParams({ concept: c.concept_id })}
                >
                  <div className="search-concept-name">{c.name}</div>
                  <div className="search-concept-meta">
                    {c.canonical_name !== c.name && `规范名：${c.canonical_name} · `}
                    来源数 {c.source_count}
                    {conceptById.get(c.concept_id) ? ` · ${conceptSourceLabel(conceptById.get(c.concept_id)!)} ` : ""}
                  </div>
                </div>
              ))}
            </div>
          )}

          {showChunkResults && chunks.length > 0 && (
            <div>
              <div className="search-section-label">内容片段 ({chunks.length})</div>
              {chunks.map((c) => (
                <div key={c.chunk_id} className="search-chunk-hit">
                  <div className="search-chunk-text">{c.text}</div>
                  <div className="search-chunk-meta">
                    {c.source_type === "pdf"
                      ? `PDF${c.page_start == null ? "" : ` · 第 ${c.page_start} 页`}`
                      : `音频 · ${c.time_start?.toFixed(1)}s`}
                    {" · "}相关度 {(c.score * 100).toFixed(0)}%
                  </div>
                </div>
              ))}
            </div>
          )}

          {visibleSearchResultCount === 0 && (
            <p style={{ fontFamily: "var(--font-ui)", fontSize: 13, color: "var(--control-text-color)" }}>
              未找到相关内容
            </p>
          )}
        </div>
      )}
    </div>
  );
}
