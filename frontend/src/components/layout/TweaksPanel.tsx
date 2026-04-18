import { useEffect } from "react";
import clsx from "clsx";
import "./TweaksPanel.css";

interface TweaksPanelProps {
  open: boolean;
  onClose: () => void;
  theme: string;
  setTheme: (t: string) => void;
  graphStyle: string;
  setGraphStyle: (g: string) => void;
}

const THEMES = [
  { id: "copper", label: "赭石", color: "#b25a2d" },
  { id: "ink",    label: "墨蓝", color: "#2b4a7f" },
  { id: "forest", label: "苍绿", color: "#4e6d3e" },
  { id: "violet", label: "紫灰", color: "#6d4c8c" },
];

const GRAPH_STYLES = [
  { id: "force",   label: "力导向" },
  { id: "radial",  label: "径向" },
  { id: "cluster", label: "分组聚类" },
];

export function TweaksPanel({ open, onClose, theme, setTheme, graphStyle, setGraphStyle }: TweaksPanelProps) {
  // Apply theme to document
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  if (!open) return null;

  return (
    <div className="tweaks" role="dialog" aria-label="外观设置">
      <div className="tweaks-head">
        <span className="tweaks-head-title">外观设置</span>
        <button
          className="btn-icon"
          onClick={onClose}
          type="button"
          aria-label="关闭"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="tweaks-section">
        <div className="tweaks-section-label">主题</div>
        <div className="tweaks-swatches">
          {THEMES.map((t) => (
            <button
              key={t.id}
              className={clsx("swatch", { active: theme === t.id })}
              onClick={() => setTheme(t.id)}
              type="button"
            >
              <span className="swatch-dot" style={{ background: t.color }} />
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="tweaks-section">
        <div className="tweaks-section-label">图谱布局</div>
        <div className="tweaks-radios">
          {GRAPH_STYLES.map((g) => (
            <button
              key={g.id}
              className={clsx("radio-card", { active: graphStyle === g.id })}
              onClick={() => setGraphStyle(g.id)}
              type="button"
            >
              {g.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
