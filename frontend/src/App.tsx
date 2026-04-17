import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ToastProvider } from "./components/primitives/Toast";
import { AppShell } from "./components/layout/AppShell";
import { HomePage } from "./pages/HomePage";
import { NewSessionPage } from "./pages/NewSessionPage";
import { PipelinePage } from "./pages/PipelinePage";
import { NotFoundPage } from "./pages/NotFoundPage";

const WorkspacePage = lazy(() =>
  import("./pages/WorkspacePage").then((m) => ({ default: m.WorkspacePage })),
);

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AppShell>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/new" element={<NewSessionPage />} />
            <Route path="/session/:id/pipeline" element={<PipelinePage />} />
            <Route
              path="/session/:id"
              element={
                <Suspense fallback={null}>
                  <WorkspacePage />
                </Suspense>
              }
            />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </AppShell>
      </ToastProvider>
    </BrowserRouter>
  );
}
