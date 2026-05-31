import { useEffect, useMemo, useState } from "react";
import { clearChat, exportChat, getChat, sendChatMessage } from "../../api/client";
import type { ChatContextItem, ChatDocument, ConceptNode } from "../../types";
import { Markdown } from "../notes/Markdown";
import { Button } from "../primitives/Button";
import { useToast } from "../primitives/Toast";
import "./ChatView.css";

interface ChatViewProps {
  sessionId: string;
  selectedConcept?: ConceptNode | null;
  pendingContext?: ChatContextItem | null;
  onContextConsumed?: () => void;
}

const PROMPTS = [
  "用考试复习的角度解释它",
  "列出容易混淆的概念",
  "给我三道自测题",
];

export function ChatView({
  sessionId,
  selectedConcept,
  pendingContext,
  onContextConsumed,
}: ChatViewProps) {
  const [chat, setChat] = useState<ChatDocument | null>(null);
  const [input, setInput] = useState("");
  const [contexts, setContexts] = useState<ChatContextItem[]>([]);
  const [sending, setSending] = useState(false);
  const [clearing, setClearing] = useState(false);
  const toast = useToast();

  useEffect(() => {
    getChat(sessionId)
      .then(setChat)
      .catch(() => setChat({ chat_id: "", session_id: sessionId, messages: [], updated_at: "" }));
  }, [sessionId]);

  useEffect(() => {
    if (!pendingContext) return;
    addContext(pendingContext);
    if (!input.trim()) {
      setInput(defaultPromptForContext(pendingContext));
    }
    onContextConsumed?.();
    // pendingContext is an event-like prop; addContext intentionally reads latest state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingContext]);

  const conceptContext = useMemo(
    () => (selectedConcept ? contextFromConcept(selectedConcept) : null),
    [selectedConcept],
  );

  function addContext(context: ChatContextItem) {
    setContexts((current) => {
      const key = contextKey(context);
      if (current.some((item) => contextKey(item) === key)) return current;
      return [...current, context];
    });
  }

  function removeContext(index: number) {
    setContexts((current) => current.filter((_, i) => i !== index));
  }

  async function handleSend() {
    const message = input.trim() || (contexts.length ? "请解释当前上下文。" : "");
    if (!message) return;
    setSending(true);
    try {
      const response = await sendChatMessage({
        session_id: sessionId,
        message,
        context_items: contexts,
      });
      setChat(response.chat);
      setInput("");
      setContexts([]);
    } catch (error) {
      toast(error instanceof Error ? `对话失败：${error.message}` : "对话失败", "error");
    } finally {
      setSending(false);
    }
  }

  async function handleClear() {
    setClearing(true);
    try {
      const fresh = await clearChat(sessionId);
      setChat(fresh);
      setContexts([]);
      setInput("");
    } catch {
      toast("清空失败", "error");
    } finally {
      setClearing(false);
    }
  }

  async function handleExport() {
    try {
      const blob = await exportChat(sessionId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "chat.md";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast("导出失败", "error");
    }
  }

  function applyPrompt(prompt: string) {
    setInput(prompt);
    if (conceptContext) {
      addContext(conceptContext);
    }
  }

  const messages = chat?.messages ?? [];

  return (
    <div className="chat-view">
      <div className="chat-header">
        <div>
          <h2 className="chat-title">对话</h2>
          <p className="chat-subtitle">结合图谱、笔记和试卷上下文提问</p>
        </div>
        <div className="chat-actions">
          <Button variant="ghost" size="sm" onClick={handleClear} loading={clearing}>
            清空
          </Button>
          <Button variant="ghost" size="sm" onClick={handleExport}>
            导出 MD
          </Button>
        </div>
      </div>

      {conceptContext && (
        <div className="chat-context-card">
          <div>
            <div className="chat-context-label">当前图谱选中</div>
            <div className="chat-context-title">{selectedConcept?.name}</div>
          </div>
          <button
            className="chat-context-btn"
            type="button"
            onClick={() => {
              addContext(conceptContext);
              if (!input.trim()) setInput("请解释这个知识点，并指出它和相邻概念的关系。");
            }}
          >
            询问这个知识点
          </button>
        </div>
      )}

      {messages.length === 0 ? (
        <div className="chat-empty">
          <p className="chat-empty-title">开始一个和课程图谱有关的问题</p>
          <div className="chat-prompt-list">
            {PROMPTS.map((prompt) => (
              <button key={prompt} type="button" onClick={() => applyPrompt(prompt)}>
                {prompt}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="chat-message-list">
          {messages.map((message) => (
            <div key={message.message_id} className={`chat-message chat-message-${message.role}`}>
              <div className="chat-message-role">{message.role === "user" ? "你" : "助手"}</div>
              <div className="chat-message-body">
                {message.role === "assistant" ? <Markdown>{message.content}</Markdown> : message.content}
              </div>
              {message.context_items.length > 0 && (
                <div className="chat-message-contexts">
                  {message.context_items.map((item, index) => (
                    <span key={`${item.label}-${index}`}>{item.label || contextTypeLabel(item.context_type)}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {contexts.length > 0 && (
        <div className="chat-context-tray">
          {contexts.map((context, index) => (
            <button
              key={`${contextKey(context)}-${index}`}
              type="button"
              className="chat-context-chip"
              onClick={() => removeContext(index)}
              title="点击移除此上下文"
            >
              {context.label || contextTypeLabel(context.context_type)}
              <span>×</span>
            </button>
          ))}
        </div>
      )}

      <div className="chat-composer">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="询问当前课程、选中知识点、笔记选区或试卷题目…"
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
              event.preventDefault();
              void handleSend();
            }
          }}
        />
        <Button onClick={handleSend} loading={sending}>
          发送
        </Button>
      </div>
    </div>
  );
}

function contextFromConcept(concept: ConceptNode): ChatContextItem {
  const parts = [
    concept.definition && `定义：${concept.definition}`,
    concept.summary && `摘要：${concept.summary}`,
    concept.key_points.length > 0 && `要点：${concept.key_points.join("；")}`,
    concept.prerequisites.length > 0 && `前置：${concept.prerequisites.join("；")}`,
    concept.applications.length > 0 && `应用：${concept.applications.join("；")}`,
    `重要性：${Math.round(concept.importance_score * 100)}%`,
  ].filter(Boolean);
  return {
    context_type: "concept",
    label: `知识点：${concept.name}`,
    concept_id: concept.concept_id,
    content: parts.join("\n"),
  };
}

function defaultPromptForContext(context: ChatContextItem): string {
  if (context.context_type === "note_selection") return "请解释这段笔记，并补充我应该如何复习。";
  if (context.context_type === "exam_selection") return "请讲解这道题的考点和解题思路。";
  if (context.context_type === "concept") return "请解释这个知识点。";
  return "请解释这段内容。";
}

function contextKey(context: ChatContextItem): string {
  return `${context.context_type}:${context.concept_id ?? ""}:${context.label}:${context.content.slice(0, 80)}`;
}

function contextTypeLabel(type: string): string {
  return {
    concept: "知识点",
    note_selection: "笔记选区",
    exam_selection: "试卷选区",
    selection: "选区",
  }[type] ?? type;
}
