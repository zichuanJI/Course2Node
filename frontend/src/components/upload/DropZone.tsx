import { useRef, useState, type DragEvent, type ChangeEvent } from "react";
import clsx from "clsx";
import "./DropZone.css";

const ACCEPT = ".pdf,audio/*,.mp3,.mp4,.wav,.m4a,.ogg,.webm";

export function DropZone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const files = Array.from(e.dataTransfer.files).filter((f) => isSupported(f));
    if (files.length) onFiles(files);
  }

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (files.length) onFiles(files);
    e.target.value = "";
  }

  return (
    <div
      className={clsx("dropzone", dragOver && "dropzone-drag-over")}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
    >
      <div className="dropzone-icon">📂</div>
      <p className="dropzone-title">拖放文件到此处，或点击选择</p>
      <p className="dropzone-hint">支持 PDF 课件和 MP3 / MP4 / WAV / M4A 录音</p>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT}
        className="dropzone-input"
        onChange={handleChange}
        aria-label="选择文件"
      />
    </div>
  );
}

function isSupported(file: File): boolean {
  if (file.type === "application/pdf") return true;
  if (file.type.startsWith("audio/")) return true;
  if (file.type.startsWith("video/mp4")) return true;
  const name = file.name.toLowerCase();
  return [".pdf", ".mp3", ".mp4", ".wav", ".m4a", ".ogg", ".webm"].some((ext) => name.endsWith(ext));
}
