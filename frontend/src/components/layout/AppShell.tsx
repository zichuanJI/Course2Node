import { type ReactNode } from "react";
import { TopBar } from "./TopBar";
import "./AppShell.css";

export function AppShell({ children, topBarActions }: { children: ReactNode; topBarActions?: ReactNode }) {
  return (
    <div className="app-shell">
      <TopBar actions={topBarActions} />
      <main className="app-shell-content">{children}</main>
    </div>
  );
}
