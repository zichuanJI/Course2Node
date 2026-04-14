import type { NoteDocument, SearchResponse, SubgraphResponse } from "../types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

export async function getSession(id: string) {
  const response = await fetch(`${BASE}/sessions/${id}`);
  return readJson(response);
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

export async function searchGraph(payload: { session_id: string; query: string; limit?: number }) {
  const response = await fetch(`${BASE}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readJson<SearchResponse>(response);
}

export async function fetchSubgraph(sessionId: string, conceptId: string, depth = 1) {
  const url = new URL(`${BASE}/graph/subgraph`);
  url.searchParams.set("session_id", sessionId);
  url.searchParams.set("concept_id", conceptId);
  url.searchParams.set("depth", String(depth));
  const response = await fetch(url.toString());
  return readJson<SubgraphResponse>(response);
}

export async function generateNotes(payload: { session_id: string; topic: string; concept_ids?: string[] }) {
  const response = await fetch(`${BASE}/generate_notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readJson<NoteDocument>(response);
}

export async function getNote(sessionId: string) {
  const response = await fetch(`${BASE}/notes/${sessionId}`);
  return readJson<NoteDocument>(response);
}

export async function exportNote(sessionId: string, fmt: "markdown" | "tex" | "txt") {
  const response = await fetch(`${BASE}/export/${sessionId}/${fmt}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.text();
}
