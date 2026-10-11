// Small shared building blocks: states (loading / empty / error), badges, fields and stat tiles.

import { CircleAlert, CircleCheck, Info, LoaderCircle, RefreshCw, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { errorMessage } from "../api/client";
import type { Diet, DisplayStatus } from "../api/types";

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-sm text-ink-500">
      <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
      {label}
    </span>
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
      <div className="mb-5 grid size-16 place-items-center rounded-full bg-leaf-50 text-leaf-600 ring-8 ring-leaf-50/50">
        {icon}
      </div>
      <h3 className="text-xl font-semibold text-ink-900">{title}</h3>
      {children && <div className="mt-2 text-[15px] leading-relaxed text-ink-600">{children}</div>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div role="alert" className="mx-auto flex max-w-md flex-col items-center px-6 py-12 text-center">
      <div className="mb-4 grid size-14 place-items-center rounded-full bg-danger-50 text-danger-600">
        <CircleAlert className="size-7" aria-hidden="true" />
      </div>
      <h3 className="text-lg font-semibold">We couldn't load this</h3>
      <p className="mt-1.5 text-[15px] text-ink-600">{errorMessage(error)}</p>
      {onRetry && (
        <button type="button" className="btn-secondary mt-5" onClick={onRetry}>
          <RefreshCw className="size-4" aria-hidden="true" /> Try again
        </button>
      )}
    </div>
  );
}

const NOTICE_STYLES = {
  info: { box: "border-leaf-200 bg-leaf-50 text-leaf-900", icon: Info },
  success: { box: "border-leaf-200 bg-leaf-50 text-leaf-900", icon: CircleCheck },
  warning: { box: "border-turmeric-300 bg-[#fdf6e3] text-[#5c4210]", icon: TriangleAlert },
  danger: { box: "border-danger-600/25 bg-danger-50 text-danger-600", icon: CircleAlert },
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
    <span className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-ink-700">
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
      className={`badge bg-ink-900/85 text-[11px] tracking-wide text-white uppercase backdrop-blur ${className}`}
      title="Development sample data. Not a real kitchen or meal."
    >
      Sample data
    </span>
  );
}

const STATUS_STYLES: Record<string, string> = {
  reserved: "bg-leaf-100 text-leaf-800",
  collected: "bg-[#e3eefb] text-[#1e4a7a]",
  cancelled: "bg-cream-200 text-ink-600",
  no_show: "bg-saffron-100 text-saffron-600",
  missed: "bg-saffron-100 text-saffron-600",
  pending: "bg-[#fdf3d6] text-[#6b4a08]",
  approved: "bg-leaf-100 text-leaf-800",
  rejected: "bg-danger-50 text-danger-600",
  suspended: "bg-danger-50 text-danger-600",
  active: "bg-leaf-100 text-leaf-800",
  draft: "bg-cream-200 text-ink-600",
  paused: "bg-[#fdf3d6] text-[#6b4a08]",
  removed: "bg-danger-50 text-danger-600",
  available: "bg-leaf-100 text-leaf-800",
  sold_out: "bg-cream-200 text-ink-600",
  closed: "bg-saffron-100 text-saffron-600",
  expired: "bg-cream-200 text-ink-600",
  unavailable: "bg-cream-200 text-ink-600",
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
  return <span className={`badge ${STATUS_STYLES[status] ?? "bg-cream-200 text-ink-700"}`}>{STATUS_LABELS[status] ?? status}</span>;
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
        {optional && <span className="ml-1.5 font-normal text-ink-500">(optional)</span>}
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
  tone = "leaf",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  tone?: "leaf" | "saffron" | "ink";
}) {
  const ring = { leaf: "bg-leaf-50 text-leaf-700", saffron: "bg-saffron-50 text-saffron-600", ink: "bg-cream-200 text-ink-700" }[tone];
  return (
    <div className="card flex items-start gap-3.5 p-4 sm:p-5">
      {icon && <div className={`grid size-10 shrink-0 place-items-center rounded-xl ${ring}`}>{icon}</div>}
      <div className="min-w-0">
        <p className="text-[13px] font-medium text-ink-500">{label}</p>
        <p className="font-display mt-0.5 text-2xl font-semibold text-ink-900 tabular-nums">{value}</p>
        {sub && <p className="mt-0.5 text-[12.5px] text-ink-500">{sub}</p>}
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
    <div role="tablist" aria-label={label} className="inline-flex gap-1 rounded-full border border-line bg-white p-1 shadow-soft">
      {tabs.map((tab) => (
        <button
          key={tab.value}
          role="tab"
          type="button"
          aria-selected={value === tab.value}
          onClick={() => onChange(tab.value)}
          className="inline-flex min-h-9 items-center gap-1.5 rounded-full px-4 text-sm font-semibold text-ink-600 transition hover:text-ink-900 aria-selected:bg-ink-900 aria-selected:text-white"
        >
          {tab.label}
          {tab.count !== undefined && tab.count > 0 && (
            <span className="rounded-full bg-saffron-400 px-1.5 text-[11px] leading-[18px] text-white">{tab.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}
