export type SessionStatus =
  | "pending" | "ingesting" | "extracting" | "aligning"
  | "retrieving" | "synthesizing" | "review" | "done" | "failed";

export interface LectureSession {
  id: string;
  course_title: string;
  lecture_title: string;
  language: string;
  status: SessionStatus;
  created_at: string;
  updated_at?: string;
  error_message?: string;
}

export type NoteBlockKind = "summary" | "section" | "supplement" | "term" | "warning" | "question";
export type GroundingLevel = "lecture" | "supplemental" | "mixed";

export interface EvidenceRef {
  source_type: "audio" | "slides" | "context_docs" | "web" | "human_edit";
  source_id: string;
  locator: string;
  url?: string;
}

export interface NoteBlock {
  id: string;
  kind: NoteBlockKind;
  title: string;
  content_md: string;
  provenance: EvidenceRef[];
  citations: EvidenceRef[];
  grounding_level: GroundingLevel;
}

export interface NoteSection {
  section_id: string;
  title: string;
  blocks: NoteBlock[];
  slide_range?: [number, number];
}

export interface NoteDocument {
  metadata: {
    session_id: string;
    course_title: string;
    lecture_title: string;
    language: string;
    generated_at: string;
  };
  one_paragraph_summary: string;
  sections: NoteSection[];
  supplemental_context: NoteBlock[];
  key_terms: NoteBlock[];
  open_questions: NoteBlock[];
}
