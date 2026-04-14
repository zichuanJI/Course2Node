import { useState } from "react";
import { uploadAudio, uploadPdf } from "../../api/client";

interface Props {
  onSessionCreated: (sessionId: string) => void;
}

export function UploadForm({ onSessionCreated }: Props) {
  const [courseTitle, setCourseTitle] = useState("");
  const [lectureTitle, setLectureTitle] = useState("");
  const [pdf, setPdf] = useState<File | null>(null);
  const [audio, setAudio] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!pdf && !audio) {
      setError("请至少上传一个 PDF 或音频文件。");
      return;
    }

    setLoading(true);
    try {
      let currentSessionId: string | null = null;

      if (pdf) {
        const form = new FormData();
        form.append("file", pdf);
        form.append("course_title", courseTitle);
        form.append("lecture_title", lectureTitle);
        const result = await uploadPdf(form);
        currentSessionId = result.session_id;
      }

      if (audio) {
        const form = new FormData();
        form.append("file", audio);
        if (currentSessionId) {
          form.append("session_id", currentSessionId);
        } else {
          form.append("course_title", courseTitle);
          form.append("lecture_title", lectureTitle);
        }
        const result = await uploadAudio(form);
        currentSessionId = result.session_id;
      }

      if (!currentSessionId) {
        throw new Error("上传失败，未创建 session。");
      }
      onSessionCreated(currentSessionId);
    } catch (unknownError) {
      setError(String(unknownError));
    } finally {
      setLoading(false);
    }
  }

  const fieldStyle = {
    display: "grid",
    gap: 6,
    marginBottom: 16,
    fontSize: 14,
    color: "#2f2419",
  } as const;

  const inputStyle = {
    padding: "12px 14px",
    borderRadius: 10,
    border: "1px solid #d8c8b7",
    background: "#fffdf8",
    fontSize: 14,
  } as const;

  return (
    <form onSubmit={handleSubmit} style={{ display: "grid", gap: 20, maxWidth: 620 }}>
      <div>
        <h2 style={{ margin: "0 0 8px", fontSize: 28 }}>创建 Course2Node 会话</h2>
        <p style={{ margin: 0, color: "#6e5847", lineHeight: 1.6 }}>
          上传课程 PDF 和录音音频，系统会先抽取知识点，再构建知识点主图，最后支持搜索和生成结构化笔记。
        </p>
      </div>

      <label style={fieldStyle}>
        课程名
        <input style={inputStyle} value={courseTitle} onChange={(event) => setCourseTitle(event.target.value)} required />
      </label>

      <label style={fieldStyle}>
        讲次标题
        <input style={inputStyle} value={lectureTitle} onChange={(event) => setLectureTitle(event.target.value)} required />
      </label>

      <label style={fieldStyle}>
        PDF 资料
        <input type="file" accept="application/pdf,.pdf" onChange={(event) => setPdf(event.target.files?.[0] ?? null)} />
      </label>

      <label style={fieldStyle}>
        课程录音
        <input type="file" accept="audio/*" onChange={(event) => setAudio(event.target.files?.[0] ?? null)} />
      </label>

      {error ? <p style={{ margin: 0, color: "#9d2c2c" }}>{error}</p> : null}

      <button
        type="submit"
        disabled={loading}
        style={{
          width: "fit-content",
          padding: "12px 18px",
          borderRadius: 999,
          border: "none",
          background: "#1f5f4a",
          color: "#fff",
          fontSize: 15,
          cursor: "pointer",
        }}
      >
        {loading ? "上传中…" : "上传并开始构建"}
      </button>
    </form>
  );
}
