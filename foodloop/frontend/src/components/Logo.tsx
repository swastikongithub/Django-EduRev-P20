import { Link } from "react-router";

/** A circular "loop" arrow around a leaf: food that comes back around instead of being thrown away. */
export function LogoMark({ className = "size-9" }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true">
      <rect width="64" height="64" rx="18" fill="var(--color-leaf-600)" />
      <path d="M32 13a19 19 0 1 0 18.4 14.3" fill="none" stroke="#FAF6EE" strokeWidth="5.5" strokeLinecap="round" />
      <path
        d="M44.6 18.2 51.4 27l-10.8 1.4"
        fill="none"
        stroke="#FAF6EE"
        strokeWidth="5.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M24 39.5c0-8.8 6.6-15 16-15.5-.4 9.6-6.7 16-16 15.5Z" fill="var(--color-turmeric-400)" />
      <path d="M24.5 39 33 30.5" stroke="var(--color-leaf-600)" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function Logo({ to = "/", tone = "dark" }: { to?: string; tone?: "dark" | "light" }) {
  return (
    <Link to={to} className="group inline-flex items-center gap-2.5 rounded-xl" aria-label="FoodLoop home">
      <LogoMark className="size-9 transition-transform duration-500 group-hover:-rotate-[20deg]" />
      <span
        className={`font-display text-[1.375rem] font-extrabold tracking-tight ${tone === "light" ? "text-white" : "text-ink-900"}`}
      >
        Food<span className={tone === "light" ? "text-leaf-200" : "text-leaf-600"}>Loop</span>
      </span>
    </Link>
  );
}
