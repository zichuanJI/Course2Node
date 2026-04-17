export type SessionStatus =
  | "draft"
  | "uploaded"
  | "ingesting"
  | "graph_ready"
  | "notes_ready"
  | "failed";

export type SourceKind = "pdf" | "audio";

export interface SourceFile {
  source_id: string;
  kind: SourceKind;
  filename: string;
  content_type: string;
  storage_path: string;
  size_bytes: number;
  uploaded_at: string;
  ingested: boolean;
  ingest_artifact_path?: string | null;
}

export interface SessionStats {
  document_count: number;
  audio_count: number;
  chunk_count: number;
  concept_count: number;
  relation_count: number;
  cluster_count: number;
}

export interface CourseSession {
  session_id: string;
  course_title: string;
  lecture_title: string;
  status: SessionStatus;
  source_files: SourceFile[];
  stats: SessionStats;
  created_at: string;
  updated_at: string;
  error_message?: string | null;
}

export interface EvidenceRef {
  chunk_id: string;
  source_id: string;
  source_type: SourceKind;
  locator: string;
  snippet: string;
  score: number;
}

export interface ConceptNode {
  concept_id: string;
  name: string;
  canonical_name: string;
  aliases: string[];
  definition: string;
  embedding: number[];
  importance_score: number;
  source_count: number;
  evidence_refs: EvidenceRef[];
}

export interface TopicClusterNode {
  cluster_id: string;
  title: string;
  summary: string;
  concept_ids: string[];
}

export interface GraphEdge {
  edge_id: string;
  source: string;
  target: string;
  edge_type: "MENTIONS" | "RELATES_TO" | "CO_OCCURS_WITH" | "CONTAINS";
  properties: Record<string, unknown>;
}

export interface GraphArtifact {
  session_id: string;
  concepts: ConceptNode[];
  topic_clusters: TopicClusterNode[];
  edges: GraphEdge[];
  built_at: string;
}

export interface SearchConceptHit {
  concept_id: string;
  name: string;
  canonical_name: string;
  score: number;
  source_count: number;
  evidence_chunk_ids: string[];
}

export interface SearchChunkHit {
  chunk_id: string;
  source_id: string;
  source_type: SourceKind;
  score: number;
  text: string;
  page_start?: number | null;
  page_end?: number | null;
  time_start?: number | null;
  time_end?: number | null;
}

export interface SearchResponse {
  session_id: string;
  query: string;
  concepts: SearchConceptHit[];
  chunks: SearchChunkHit[];
}

export interface SubgraphNode {
  id: string;
  label: string;
  node_type: "concept" | "topic_cluster";
  metadata: Record<string, unknown>;
}

export interface SubgraphEdge {
  source: string;
  target: string;
  edge_type: string;
  properties: Record<string, unknown>;
}

export interface SubgraphResponse {
  session_id: string;
  center_concept_id: string;
  nodes: SubgraphNode[];
  edges: SubgraphEdge[];
}

export interface NoteReference {
  source_type: SourceKind;
  source_id: string;
  locator: string;
  snippet: string;
}

export interface NoteSection {
  section_id: string;
  title: string;
  content_md: string;
  concept_ids: string[];
  references: NoteReference[];
}

export interface NoteDocument {
  note_id: string;
  session_id: string;
  title: string;
  topic: string;
  summary: string;
  sections: NoteSection[];
  generated_at: string;
}
