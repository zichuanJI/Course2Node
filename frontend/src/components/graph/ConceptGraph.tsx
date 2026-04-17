import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  useNodesState,
  useEdgesState,
  addEdge,
  type Connection,
} from "reactflow";
import dagre from "dagre";
import "reactflow/dist/style.css";

import { getGraph, fetchSubgraph } from "../../api/client";
import type { GraphArtifact, SubgraphResponse } from "../../types";
import "./ConceptGraph.css";

interface GraphProps {
  sessionId: string;
}

const EDGE_COLORS: Record<string, string> = {
  RELATES_TO:      "var(--accent-color)",
  CO_OCCURS_WITH:  "var(--border-color)",
  CONTAINS:        "var(--color-success)",
  MENTIONS:        "var(--control-text-color)",
};

function layoutWithDagre(nodes: Node[], edges: Edge[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", nodesep: 60, ranksep: 80 });

  nodes.forEach((node) => {
    g.setNode(node.id, { width: 140, height: 36 });
  });

  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target);
  });

  dagre.layout(g);

  return {
    nodes: nodes.map((node) => {
      const n = g.node(node.id);
      return { ...node, position: { x: n.x - 70, y: n.y - 18 } };
    }),
    edges,
  };
}

function artifactToFlow(artifact: GraphArtifact): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [
    ...artifact.concepts.map((c) => ({
      id: c.concept_id,
      type: "default",
      data: { label: c.name },
      position: { x: 0, y: 0 },
      style: {
        background: "var(--bg-color)",
        border: "1.5px solid var(--border-color)",
        borderRadius: "999px",
        fontFamily: "var(--font-ui)",
        fontSize: "12px",
        padding: "6px 14px",
        cursor: "pointer",
      },
    })),
    ...artifact.topic_clusters.map((cl) => ({
      id: cl.cluster_id,
      type: "default",
      data: { label: cl.title },
      position: { x: 0, y: 0 },
      style: {
        background: "var(--side-bar-bg-color)",
        border: "1.5px solid var(--border-color)",
        borderRadius: "var(--radius-md)",
        fontFamily: "var(--font-ui)",
        fontSize: "12px",
        fontWeight: "600",
        padding: "6px 14px",
      },
    })),
  ];

  const edges: Edge[] = artifact.edges.map((e) => ({
    id: e.edge_id,
    source: e.source,
    target: e.target,
    style: { stroke: EDGE_COLORS[e.edge_type] ?? "var(--border-color)", strokeWidth: 1.5 },
    type: "default",
    animated: false,
  }));

  return layoutWithDagre(nodes, edges);
}

function subgraphToFlow(sub: SubgraphResponse): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = sub.nodes.map((n) => ({
    id: n.id,
    type: "default",
    data: { label: n.label },
    position: { x: 0, y: 0 },
    style: {
      background: n.id === sub.center_concept_id ? "var(--accent-strong)" : "var(--bg-color)",
      border: n.id === sub.center_concept_id
        ? "2px solid var(--accent-color)"
        : "1.5px solid var(--border-color)",
      borderRadius: n.node_type === "concept" ? "999px" : "var(--radius-md)",
      fontFamily: "var(--font-ui)",
      fontSize: "12px",
      padding: "6px 14px",
      cursor: "pointer",
    },
  }));

  const edges: Edge[] = sub.edges.map((e, i) => ({
    id: `e${i}`,
    source: e.source,
    target: e.target,
    style: { stroke: EDGE_COLORS[e.edge_type] ?? "var(--border-color)", strokeWidth: 1.5 },
  }));

  return layoutWithDagre(nodes, edges);
}

export function ConceptGraph({ sessionId }: GraphProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const conceptId = searchParams.get("concept");
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState([]);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState([]);
  const [loading, setLoading] = useState(true);
  const [empty, setEmpty] = useState(false);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        if (conceptId) {
          const sub = await fetchSubgraph(sessionId, conceptId, 2);
          const { nodes, edges } = subgraphToFlow(sub);
          setRfNodes(nodes);
          setRfEdges(edges);
          setEmpty(nodes.length === 0);
        } else {
          const artifact = await getGraph(sessionId);
          if (artifact.concepts.length === 0) { setEmpty(true); setLoading(false); return; }
          const { nodes, edges } = artifactToFlow(artifact);
          setRfNodes(nodes);
          setRfEdges(edges);
          setEmpty(false);
        }
      } catch {
        setEmpty(true);
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [sessionId, conceptId, setRfNodes, setRfEdges]);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      setSearchParams({ concept: node.id });
    },
    [setSearchParams],
  );

  if (loading) {
    return (
      <div className="concept-graph-wrap">
        <div className="graph-empty">加载图谱中…</div>
      </div>
    );
  }

  if (empty) {
    return (
      <div className="concept-graph-wrap">
        <div className="graph-empty">暂无图谱数据</div>
      </div>
    );
  }

  return (
    <div className="concept-graph-wrap">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="var(--border-color)" gap={20} />
        <Controls />
        <MiniMap
          nodeColor={() => "var(--accent-soft)"}
          maskColor="rgba(250,249,245,0.6)"
        />
      </ReactFlow>
    </div>
  );
}
