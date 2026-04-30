import type {
  CourseSession,
  ExamDocument,
  NoteDocument,
  GraphArtifact,
  RuntimeSettingsResponse,
  SearchResponse,
  SubgraphResponse,
} from "../types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(response.status, text || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function listSessions(): Promise<CourseSession[]> {
  const response = await fetch(`${BASE}/sessions/`);
  return readJson<CourseSession[]>(response);
}

export async function getSession(id: string): Promise<CourseSession> {
  const response = await fetch(`${BASE}/sessions/${id}`);
  return readJson<CourseSession>(response);
}

export async function getSessionStatus(id: string) {
  const response = await fetch(`${BASE}/sessions/${id}/status`);
  return readJson(response);
}

export async function uploadPdf(form: FormData) {
  const response = await fetch(`${BASE}/upload/pdf`, { method: "POST", body: form });
  return readJson<{ session_id: string; source_id: string }>(response);
}

export async function uploadAudio(form: FormData) {
  const response = await fetch(`${BASE}/upload/audio`, { method: "POST", body: form });
  return readJson<{ session_id: string; source_id: string }>(response);
}

export function uploadWithProgress(
  url: string,
  form: FormData,
  onProgress: (pct: number) => void,
): Promise<{ session_id: string; source_id: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as { session_id: string; source_id: string });
        } catch {
          reject(new ApiError(xhr.status, "Invalid JSON response"));
        }
      } else {
        reject(new ApiError(xhr.status, xhr.responseText || `HTTP ${xhr.status}`));
      }
    });
    xhr.addEventListener("error", () => reject(new ApiError(0, "Network error")));
    xhr.send(form);
  });
}

export function uploadPdfWithProgress(form: FormData, onProgress: (pct: number) => void) {
  return uploadWithProgress(`${BASE}/upload/pdf`, form, onProgress);
}

export function uploadAudioWithProgress(form: FormData, onProgress: (pct: number) => void) {
  return uploadWithProgress(`${BASE}/upload/audio`, form, onProgress);
}

export async function ingestPdf(payload: { session_id: string; source_id: string }) {
  const response = await fetch(`${BASE}/ingest/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readJson(response);
}

export async function ingestAudio(payload: { session_id: string; source_id: string }) {
  const response = await fetch(`${BASE}/ingest/audio`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readJson(response);
}

export async function buildGraph(payload: { session_id: string }) {
  const response = await fetch(`${BASE}/build_graph`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readJson(response);
}

export async function getGraph(sessionId: string): Promise<GraphArtifact> {
  const response = await fetch(`${BASE}/graph/${sessionId}`);
  return readJson<GraphArtifact>(response);
}

export async function searchGraph(payload: { session_id: string; query: string; limit?: number }) {
  const response = await fetch(`${BASE}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readJson<SearchResponse>(response);
}

export async function fetchSubgraph(sessionId: string, conceptId: string, depth = 2) {
  const url = new URL(`${BASE}/graph/subgraph`);
  url.searchParams.set("session_id", sessionId);
  url.searchParams.set("concept_id", conceptId);
  url.searchParams.set("depth", String(depth));
  const response = await fetch(url.toString());
  return readJson<SubgraphResponse>(response);
}

export async function generateNotes(payload: { session_id: string; topic?: string; concept_ids?: string[] }) {
  const response = await fetch(`${BASE}/generate_notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readJson<NoteDocument>(response);
}

export async function getNote(sessionId: string): Promise<NoteDocument> {
  const response = await fetch(`${BASE}/notes/${sessionId}`);
  return readJson<NoteDocument>(response);
}

export async function generateExam(payload: { session_id: string; question_count?: number; question_types?: string[] }) {
  const response = await fetch(`${BASE}/generate_exam`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readJson<ExamDocument>(response);
}

export async function getExam(sessionId: string): Promise<ExamDocument> {
  const response = await fetch(`${BASE}/exam/${sessionId}`);
  return readJson<ExamDocument>(response);
}

export async function deleteSession(id: string): Promise<void> {
  const response = await fetch(`${BASE}/sessions/${id}`, { method: "DELETE" });
  await readJson<{ ok: boolean }>(response);
}

export async function exportNote(sessionId: string, fmt: "markdown" | "tex" | "txt"): Promise<string> {
  const response = await fetch(`${BASE}/export/${sessionId}/${fmt}`);
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  return response.text();
}

export async function exportExam(sessionId: string, fmt: "markdown" | "tex" | "txt"): Promise<string> {
  const response = await fetch(`${BASE}/export/${sessionId}/exam/${fmt}`);
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  return response.text();
}

export async function getRuntimeSettings(): Promise<RuntimeSettingsResponse> {
  const response = await fetch(`${BASE}/settings/runtime`);
  return readJson<RuntimeSettingsResponse>(response);
}

export async function updateRuntimeSettings(values: Record<string, string>): Promise<RuntimeSettingsResponse> {
  const response = await fetch(`${BASE}/settings/runtime`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ values }),
  });
  return readJson<RuntimeSettingsResponse>(response);
}
