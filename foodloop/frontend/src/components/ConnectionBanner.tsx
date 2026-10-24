// When FoodLoop's server or database is down, say so plainly, keep checking, and reload the data by itself
// the moment it's back. Nobody has to guess what "something went wrong" means or keep pressing refresh.

import { useQueryClient } from "@tanstack/react-query";
import { PlugZap, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { type ConnectionProblem, connectionProblem } from "../api/client";
import { PROBLEM_TEXT } from "../lib/connection";
import { useToast } from "./Toast";

const CHECK_EVERY_MS = 4000;

async function serverHealthy(): Promise<ConnectionProblem | null> {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    if (response.ok) return null;
    const body = (await response.json().catch(() => null)) as { database?: string } | null;
    return body?.database === "unreachable" ? "database_unavailable" : "server_unreachable";
  } catch {
    return "offline";
  }
}

export function ConnectionBanner() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [problem, setProblem] = useState<ConnectionProblem | null>(null);

  // Notice any data request that failed because the server or database is down.
  useEffect(
    () =>
      queryClient.getQueryCache().subscribe((event) => {
        if (event.type === "updated" && event.action.type === "error") {
          const found = connectionProblem(event.action.error);
          if (found) setProblem(found);
        }
      }),
    [queryClient],
  );

  // While there's a problem, check every few seconds. When it's fixed, reload everything on the page.
  useEffect(() => {
    if (!problem) return;
    let stopped = false;
    const timer = window.setInterval(async () => {
      const now = await serverHealthy();
      if (stopped) return;
      if (now === null) {
        setProblem(null);
        queryClient.invalidateQueries();
        toast.success("Connected again", "Everything is up to date.");
      } else {
        setProblem(now);
      }
    }, CHECK_EVERY_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [problem, queryClient, toast]);

  if (!problem) return null;
  const text = PROBLEM_TEXT[problem];
  return (
    <div role="status" className="sticky top-[4.25rem] z-30 border-b border-saffron-100 bg-saffron-50/95 backdrop-blur">
      <div className="container-page flex flex-wrap items-start gap-3 py-3 text-[14px] text-ink-900">
        <PlugZap className="mt-0.5 size-5 shrink-0 text-saffron-600" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">{text.title}</p>
          <p className="text-ink-700">
            {text.body}
            {import.meta.env.DEV && text.devHint && <span className="mt-0.5 block text-[13px] text-ink-600">{text.devHint}</span>}
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 self-center rounded-full bg-white px-3 py-1 text-[12.5px] font-semibold text-saffron-600 ring-1 ring-saffron-100">
          <RefreshCw className="size-3.5 animate-spin [animation-duration:2.5s]" aria-hidden="true" /> Reconnecting…
        </span>
      </div>
    </div>
  );
}
