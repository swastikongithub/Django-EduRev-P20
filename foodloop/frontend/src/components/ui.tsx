// Small shared building blocks: states (loading / empty / error), badges, fields and stat tiles.

import { CircleAlert, CircleCheck, Info, LoaderCircle, PlugZap, RefreshCw, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { connectionProblem, errorMessage } from "../api/client";
import { PROBLEM_TEXT } from "../lib/connection";
import type { Diet, DisplayStatus } from "../api/types";

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-sm text-fg-muted">
      <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
      {label}
    </span>
  );
}

/** Button content that swaps to a spinner while an action is running. */
export function BusyLabel({ busy, busyText, children }: { busy: boolean; busyText: string; children: ReactNode }) {
  return busy ? (
    <>
      <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
      {busyText}
    </>
  ) : (
    <>{children}</>
  );
}

export function PageLoader() {
  return (
    <div className="grid min-h-[50vh] place-items-center">
      <Spinner label="Loading…" />
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mx-auto flex max-w-md animate-rise flex-col items-center px-6 py-14 text-center">
      <div className="mb-5 grid size-16 place-items-center rounded-full bg-brand-950 text-brand-400 ring-8 ring-brand-950/50">
        {icon}
      </div>
      <h3 className="text-xl font-semibold text-fg">{title}</h3>
      {children && <div className="mt-2 text-[15px] leading-relaxed text-fg-soft">{children}</div>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const problem = connectionProblem(error);
  const text = problem ? PROBLEM_TEXT[problem] : null;
  return (
    <div role="alert" className="mx-auto flex max-w-md flex-col items-center px-6 py-12 text-center">
      <div
        className={`mb-4 grid size-14 place-items-center rounded-full ${text ? "bg-brand-950 text-brand-400" : "bg-danger-950 text-danger-400"}`}
      >
        {text ? <PlugZap className="size-7" aria-hidden="true" /> : <CircleAlert className="size-7" aria-hidden="true" />}
      </div>
      <h3 className="text-lg font-semibold">{text ? text.title : "We couldn't load this"}</h3>
      <p className="mt-1.5 text-[15px] text-fg-soft">{text ? text.body : errorMessage(error)}</p>
      {text && import.meta.env.DEV && text.devHint && <p className="mt-2 text-[13px] leading-relaxed text-fg-muted">{text.devHint}</p>}
      {onRetry && (
        <button type="button" className="btn-secondary mt-5" onClick={onRetry}>
          <RefreshCw className="size-4" aria-hidden="true" /> Try again
        </button>
      )}
    </div>
  );
}

const NOTICE_STYLES = {
  info: { box: "border-brand-800/80 bg-brand-950 text-brand-100", icon: Info },
  success: { box: "border-leaf-900 bg-leaf-950 text-leaf-300", icon: CircleCheck },
  warning: { box: "border-turmeric-400/35 bg-turmeric-950 text-turmeric-300", icon: TriangleAlert },
  danger: { box: "border-danger-500/40 bg-danger-950 text-danger-300", icon: CircleAlert },
} as const;

export function Notice({
  tone = "info",
  title,
  children,
  className = "",
}: {
  tone?: keyof typeof NOTICE_STYLES;
  title?: string;
  children?: ReactNode;
  className?: string;
}) {
  const style = NOTICE_STYLES[tone];
  const Icon = style.icon;
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={`flex gap-3 rounded-2xl border px-4 py-3.5 text-[14px] leading-relaxed ${style.box} ${className}`}
    >
      <Icon className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
      <div>
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={title ? "mt-0.5 opacity-90" : ""}>{children}</div>}
      </div>
    </div>
  );
}

/** India's food marking: a green dot in a square for veg, a brown triangle for non-veg. */
export function DietMark({ diet, label }: { diet: Diet; label?: string }) {
  const color = diet === "non_veg" ? "var(--color-nonveg)" : diet === "egg" ? "#c58a12" : "var(--color-veg)";
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-fg-soft">
      <svg viewBox="0 0 16 16" className="size-4 shrink-0" aria-hidden="true">
        <rect x="1" y="1" width="14" height="14" rx="2" fill="#fff" stroke={color} strokeWidth="1.6" />
        {diet === "non_veg" ? <path d="M8 4.2 11.6 11H4.4Z" fill={color} /> : <circle cx="8" cy="8" r="3.6" fill={color} />}
      </svg>
      {label}
    </span>
  );
}

export function SampleBadge({ className = "" }: { className?: string }) {
  return (
    <span
      className={`badge bg-night/85 text-[11px] tracking-wide text-white uppercase backdrop-blur ${className}`}
      title="Development sample data. Not a real kitchen or meal."
    >
      Sample data
    </span>
  );
}

const STATUS_STYLES: Record<string, string> = {
  reserved: "bg-brand-900 text-brand-200",
  collected: "bg-info-950 text-info-300",
  cancelled: "bg-raised text-fg-muted",
  no_show: "bg-danger-950 text-danger-300",
  missed: "bg-danger-950 text-danger-300",
  pending: "bg-turmeric-950 text-turmeric-300",
  approved: "bg-leaf-950 text-leaf-300",
  rejected: "bg-danger-950 text-danger-300",
  suspended: "bg-danger-950 text-danger-300",
  active: "bg-leaf-950 text-leaf-300",
  draft: "bg-raised text-fg-muted",
  paused: "bg-turmeric-950 text-turmeric-300",
  removed: "bg-danger-950 text-danger-300",
  available: "bg-leaf-950 text-leaf-300",
  sold_out: "bg-raised text-fg-muted",
  closed: "bg-turmeric-950 text-turmeric-300",
  expired: "bg-raised text-fg-muted",
  unavailable: "bg-raised text-fg-muted",
};

const STATUS_LABELS: Record<string, string> = {
  reserved: "Reserved",
  collected: "Collected",
  cancelled: "Cancelled",
  no_show: "Not collected",
  missed: "Pickup missed",
  pending: "Awaiting approval",
  approved: "Approved",
  rejected: "Not approved",
  suspended: "Suspended",
  active: "Live",
  draft: "Draft",
  paused: "Paused",
  removed: "Removed",
  available: "Available",
  sold_out: "Sold out",
  closed: "Reservations closed",
  expired: "Expired",
  unavailable: "Unavailable",
};

export function StatusPill({ status }: { status: DisplayStatus | string }) {
  return <span className={`badge ${STATUS_STYLES[status] ?? "bg-raised text-fg-soft"}`}>{STATUS_LABELS[status] ?? status}</span>;
}

export function Field({
  id,
  label,
  hint,
  error,
  children,
  optional,
}: {
  id: string;
  label: string;
  hint?: ReactNode;
  error?: string;
  children: ReactNode;
  optional?: boolean;
}) {
  return (
    <div>
      <label htmlFor={id} className="label">
        {label}
        {optional && <span className="ml-1.5 font-normal text-fg-muted">(optional)</span>}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="field-error">
          <CircleAlert className="mt-px size-4 shrink-0" aria-hidden="true" />
          {error}
        </p>
      ) : (
        hint && (
          <p id={`${id}-hint`} className="hint">
            {hint}
          </p>
        )
      )}
    </div>
  );
}

/** Props that connect an input to its Field's hint/error for screen readers. */
export function describedBy(id: string, error?: string) {
  return { id, "aria-invalid": error ? true : undefined, "aria-describedby": error ? `${id}-error` : `${id}-hint` };
}

export function StatTile({
  label,
  value,
  sub,
  icon,
  tone = "brand",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  tone?: "brand" | "attention" | "neutral";
}) {
  const ring = { brand: "bg-brand-950 text-brand-400", attention: "bg-turmeric-950 text-turmeric-300", neutral: "bg-raised text-fg-soft" }[tone];
  return (
    <div className="card flex items-start gap-3.5 p-4 sm:p-5">
      {icon && <div className={`grid size-10 shrink-0 place-items-center rounded-xl ${ring}`}>{icon}</div>}
      <div className="min-w-0">
        <p className="text-[13px] font-medium text-fg-muted">{label}</p>
        <p className="font-display mt-0.5 text-2xl font-semibold text-fg tabular-nums">{value}</p>
        {sub && <p className="mt-0.5 text-[12.5px] text-fg-muted">{sub}</p>}
      </div>
    </div>
  );
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
}: {
  tabs: { value: T; label: string; count?: number }[];
  value: T;
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex gap-1 rounded-full border border-line bg-panel p-1 shadow-soft">
      {tabs.map((tab) => (
        <button
          key={tab.value}
          role="tab"
          type="button"
          aria-selected={value === tab.value}
          onClick={() => onChange(tab.value)}
          className="group inline-flex min-h-9 items-center gap-1.5 rounded-full px-4 text-sm font-semibold text-fg-soft transition hover:text-fg aria-selected:bg-brand-500 aria-selected:text-night"
        >
          {tab.label}
          {tab.count !== undefined && tab.count > 0 && (
            <span className="rounded-full bg-brand-500 px-1.5 text-[11px] leading-[18px] text-night group-aria-selected:bg-night group-aria-selected:text-brand-300">{tab.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

/** The calm sage band at the top of dashboard-style pages: eyebrow, title, short description and actions. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  children,
  narrow = false,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  /** Line up with a narrow (max-w-4xl) page body such as a form. */
  narrow?: boolean;
}) {
  return (
    <div className="border-b border-line/70 bg-panel">
      <div className={`${narrow ? "mx-auto max-w-4xl px-4 sm:px-6" : "container-page"} py-8 sm:py-10`}>
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div className="min-w-0 animate-rise">
            {eyebrow && <p className="eyebrow">{eyebrow}</p>}
            <h1 className="mt-2 text-[2rem] leading-tight sm:text-[2.5rem]">{title}</h1>
            {description && <div className="mt-2 max-w-2xl text-[15px] leading-relaxed text-fg-soft">{description}</div>}
          </div>
          {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
        </div>
        {children && <div className="mt-6">{children}</div>}
      </div>
    </div>
  );
}
