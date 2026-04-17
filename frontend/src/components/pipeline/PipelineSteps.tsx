import clsx from "clsx";
import type { SessionStatus } from "../../types";
import "./PipelineSteps.css";

type StepState = "pending" | "active" | "done" | "failed";

interface Step {
  key: string;
  label: string;
}

const STEPS: Step[] = [
  { key: "uploaded",    label: "文件上传完成" },
  { key: "ingesting",   label: "解析内容（PDF / 音频）" },
  { key: "graph_ready", label: "构建知识点图谱" },
];

function deriveStepState(stepKey: string, status: SessionStatus): StepState {
  if (status === "failed") {
    if (stepKey === "ingesting" || stepKey === "graph_ready") return "failed";
    return "done";
  }
  const order = ["uploaded", "ingesting", "graph_ready", "notes_ready"] as const;
  const stepIdx = order.indexOf(stepKey as typeof order[number]);
  const curIdx = order.indexOf(status as typeof order[number]);
  if (stepIdx < 0 || curIdx < 0) return "pending";
  if (stepIdx < curIdx) return "done";
  if (stepIdx === curIdx) return "active";
  return "pending";
}

export function PipelineSteps({ status }: { status: SessionStatus }) {
  return (
    <div className="pipeline-steps">
      {STEPS.map((step) => {
        const state = deriveStepState(step.key, status);
        return (
          <div key={step.key} className="pipeline-step">
            <div className={clsx("step-dot", `step-dot-${state}`)} />
            <span className={clsx("step-label", `step-label-${state}`)}>
              {step.label}
              {state === "active" && "…"}
            </span>
          </div>
        );
      })}
    </div>
  );
}
