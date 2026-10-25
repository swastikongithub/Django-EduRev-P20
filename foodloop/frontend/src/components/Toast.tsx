// Small toast notifications ("Reserved!", "Listing saved") without an extra library.
// Screen readers hear them through an aria-live region; they disappear on their own after a few seconds.

import { CircleAlert, CircleCheck, X } from "lucide-react";
import { createContext, type ReactNode, useCallback, useContext, useMemo, useRef, useState } from "react";

type Tone = "success" | "error";
interface ToastItem {
  id: number;
  tone: Tone;
  title: string;
  body?: string;
}
interface ToastApi {
  success: (title: string, body?: string) => void;
  error: (title: string, body?: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => setItems((current) => current.filter((item) => item.id !== id)), []);
  const push = useCallback(
    (tone: Tone, title: string, body?: string) => {
      const id = nextId.current++;
      setItems((current) => [...current.slice(-2), { id, tone, title, body }]);
      window.setTimeout(() => dismiss(id), tone === "error" ? 7000 : 4500);
    },
    [dismiss],
  );
  const api = useMemo<ToastApi>(
    () => ({ success: (title, body) => push("success", title, body), error: (title, body) => push("error", title, body) }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-0 bottom-4 z-[60] flex flex-col items-center gap-2 px-4 sm:inset-x-auto sm:right-6 sm:bottom-6 sm:items-end"
      >
        {items.map((item) => (
          <div
            key={item.id}
            role={item.tone === "error" ? "alert" : "status"}
            className="pointer-events-auto flex w-full max-w-sm animate-rise items-start gap-3 rounded-2xl border border-line bg-panel p-4 shadow-lift"
          >
            {item.tone === "success" ? (
              <CircleCheck className="mt-0.5 size-5 shrink-0 text-leaf-400" aria-hidden="true" />
            ) : (
              <CircleAlert className="mt-0.5 size-5 shrink-0 text-danger-400" aria-hidden="true" />
            )}
            <div className="min-w-0 flex-1">
              <p className="text-[14.5px] font-semibold text-fg">{item.title}</p>
              {item.body && <p className="mt-0.5 text-[13.5px] leading-snug text-fg-soft">{item.body}</p>}
            </div>
            <button
              type="button"
              onClick={() => dismiss(item.id)}
              className="-m-1 grid size-8 shrink-0 place-items-center rounded-full text-fg-muted hover:bg-raised"
              aria-label="Dismiss notification"
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside <ToastProvider>");
  return context;
}
