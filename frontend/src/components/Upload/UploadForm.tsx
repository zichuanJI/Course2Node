import { useState } from "react";
import { uploadLecture } from "../../api/client";

interface Props {
  onSessionCreated: (sessionId: string) => void;
}

export function UploadForm({ onSessionCreated }: Props) {
  const [courseTitle, setCourseTitle] = useState("");
  const [lectureTitle, setLectureTitle] = useState("");
  const [audio, setAudio] = useState<File | null>(null);
  const [slides, setSlides] = useState<File | null>(null);
  const [contextDoc, setContextDoc] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!audio && !slides) {
      setError("Please upload at least an audio file or slides.");
      return;
    }
    const form = new FormData();
    form.append("course_title", courseTitle);
    form.append("lecture_title", lectureTitle);
    if (audio) form.append("audio", audio);
    if (slides) form.append("slides", slides);
    if (contextDoc) form.append("context_doc", contextDoc);

    setLoading(true);
    try {
      const result = await uploadLecture(form);
      onSessionCreated(result.session_id);
    } catch (err: unknown) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={{ maxWidth: 560 }}>
      <h2>New Lecture Session</h2>
      <label>
        Course title
        <input value={courseTitle} onChange={e => setCourseTitle(e.target.value)} required />
      </label>
      <label>
        Lecture title
        <input value={lectureTitle} onChange={e => setLectureTitle(e.target.value)} required />
      </label>
      <label>
        Audio (optional)
        <input type="file" accept="audio/*" onChange={e => setAudio(e.target.files?.[0] ?? null)} />
      </label>
      <label>
        Slides – PPTX or PDF (optional)
        <input type="file" accept=".pptx,.pdf,application/pdf" onChange={e => setSlides(e.target.files?.[0] ?? null)} />
      </label>
      <label>
        Context doc – syllabus / chapter (optional)
        <input type="file" accept=".pdf,.txt,text/plain,application/pdf" onChange={e => setContextDoc(e.target.files?.[0] ?? null)} />
      </label>
      {error && <p style={{ color: "red" }}>{error}</p>}
      <button type="submit" disabled={loading}>
        {loading ? "Uploading…" : "Upload & Process"}
      </button>
    </form>
  );
}
