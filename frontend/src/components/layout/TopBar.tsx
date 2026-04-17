import { type ReactNode } from "react";
import { Link } from "react-router-dom";
import "./TopBar.css";

export function TopBar({ actions }: { actions?: ReactNode }) {
  return (
    <header className="topbar">
      <Link to="/" className="topbar-brand">
        <span className="topbar-logo">Course2note</span>
      </Link>
      <div className="topbar-spacer" />
      {actions && <div className="topbar-actions">{actions}</div>}
    </header>
  );
}
