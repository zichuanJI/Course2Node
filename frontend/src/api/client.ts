const BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

export async function listSessions() {
  const r = await fetch(`${BASE}/sessions/`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getSession(id: string) {
  const r = await fetch(`${BASE}/sessions/${id}`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function getSessionStatus(id: string) {
  const r = await fetch(`${BASE}/sessions/${id}/status`);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function uploadLecture(form: FormData) {
  const r = await fetch(`${BASE}/upload/`, { method: "POST", body: form });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function exportNote(sessionId: string, fmt: "markdown" | "tex" | "txt") {
  const r = await fetch(`${BASE}/export/${sessionId}/${fmt}`);
  if (!r.ok) throw new Error(await r.text());
  return r.text();
}

export async function submitReviewEvent(
  sessionId: string,
  event: {
    note_block_id: string;
    action: "edit" | "accept" | "reject" | "rate";
    before?: string;
    after?: string;
    user_rating?: number;
  }
) {
  const r = await fetch(`${BASE}/review/${sessionId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(event),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
