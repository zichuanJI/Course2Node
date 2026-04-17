import { useCallback, useEffect, useRef, useState } from "react";
import { getSessionStatus } from "../api/client";
import type { SessionStatus } from "../types";

interface StatusPayload {
  status: SessionStatus;
  stats: Record<string, number>;
  error_message?: string | null;
}

export function useSessionStatus(sessionId: string | null, active: boolean) {
  const [data, setData] = useState<StatusPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startedAt = useRef(Date.now());

  const stop = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!active || !sessionId) return;
    startedAt.current = Date.now();
    let cancelled = false;

    async function poll() {
      if (cancelled || !sessionId) return;
      try {
        const result = await getSessionStatus(sessionId) as StatusPayload;
        if (!cancelled) setData(result);
      } catch (e) {
        if (!cancelled) setError(String(e));
        return;
      }

      if (cancelled) return;
      const elapsed = Date.now() - startedAt.current;
      const delay = elapsed > 30_000 ? 3000 : 1500;
      timerRef.current = setTimeout(poll, delay);
    }

    void poll();

    return () => {
      cancelled = true;
      stop();
    };
  }, [active, sessionId, stop]);

  return { data, error, stop };
}
