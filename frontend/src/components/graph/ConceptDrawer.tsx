import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getGraph } from "../../api/client";
import type { ConceptNode } from "../../types";
import { Drawer } from "../primitives/Drawer";

export function ConceptDrawer({ sessionId }: { sessionId: string }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const conceptId = searchParams.get("concept");
  const [concept, setConcept] = useState<ConceptNode | null>(null);

  useEffect(() => {
    if (!conceptId) { setConcept(null); return; }
    getGraph(sessionId).then((artifact) => {
      const c = artifact.concepts.find((c) => c.concept_id === conceptId);
      setConcept(c ?? null);
    }).catch(() => setConcept(null));
  }, [sessionId, conceptId]);

  function close() {
    setSearchParams({});
  }

  return (
    <Drawer
      open={!!conceptId}
      title={concept?.name ?? "知识点详情"}
      onClose={close}
    >
      {concept ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)", fontFamily: "var(--font-ui)", fontSize: 14 }}>
          <div>
            <div style={{ fontSize: 12, color: "var(--control-text-color)", marginBottom: 4 }}>规范名称</div>
            <div style={{ fontWeight: 600, color: "var(--heading-color)" }}>{concept.canonical_name}</div>
          </div>

          {concept.aliases.length > 0 && (
            <div>
              <div style={{ fontSize: 12, color: "var(--control-text-color)", marginBottom: 4 }}>别名</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {concept.aliases.map((a) => (
                  <span key={a} style={{
                    background: "var(--side-bar-bg-color)",
                    border: "1px solid var(--border-color)",
                    borderRadius: "var(--radius-pill)",
                    padding: "2px 10px",
                    fontSize: 12,
                    color: "var(--text-color)",
                  }}>{a}</span>
                ))}
              </div>
            </div>
          )}

          <div>
            <div style={{ fontSize: 12, color: "var(--control-text-color)", marginBottom: 6 }}>重要性</div>
            <div style={{ height: 6, background: "var(--side-bar-bg-color)", borderRadius: "var(--radius-pill)", overflow: "hidden" }}>
              <div style={{
                height: "100%",
                width: `${Math.min(100, concept.importance_score * 100).toFixed(1)}%`,
                background: "var(--accent-color)",
                borderRadius: "var(--radius-pill)",
                transition: "width 0.4s var(--ease)",
              }} />
            </div>
          </div>

          {concept.definition && (
            <div>
              <div style={{ fontSize: 12, color: "var(--control-text-color)", marginBottom: 4 }}>定义</div>
              <p style={{ margin: 0, lineHeight: 1.6, color: "var(--text-color)" }}>{concept.definition}</p>
            </div>
          )}

          {concept.evidence_refs.length > 0 && (
            <div>
              <div style={{ fontSize: 12, color: "var(--control-text-color)", marginBottom: 8 }}>
                证据来源 ({concept.evidence_refs.length})
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {concept.evidence_refs.slice(0, 5).map((ref) => (
                  <div key={ref.chunk_id} style={{
                    background: "var(--window-bg-color)",
                    border: "1px solid var(--border-color)",
                    borderRadius: "var(--radius-sm)",
                    padding: "8px 12px",
                  }}>
                    <div style={{ fontSize: 12, color: "var(--control-text-color)", marginBottom: 4 }}>
                      {ref.source_type === "pdf" ? `PDF · ${ref.locator}` : `音频 · ${ref.locator}`}
                    </div>
                    <div style={{ fontSize: 13, color: "var(--text-color)", lineHeight: 1.5 }}>
                      {ref.snippet}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <p style={{ fontFamily: "var(--font-ui)", color: "var(--control-text-color)", fontSize: 14 }}>加载中…</p>
      )}
    </Drawer>
  );
}
