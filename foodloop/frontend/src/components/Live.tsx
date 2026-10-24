// Small pieces that make pages feel alive: ticking countdowns, numbers that count up, sections that rise
// into view, a ticker of live deals and swipeable rows. They only ever show real data, and all motion
// stops for people who prefer reduced motion.

import { ChevronLeft, ChevronRight, Timer } from "lucide-react";
import { type ElementType, type ReactNode, useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import type { Listing } from "../api/types";
import { formatRupees } from "../lib/format";
import { photoForMeal } from "../lib/photos";
import { Photo } from "./Photo";

const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** True once the element has scrolled into view (stays true). */
function useSeen<T extends Element>(rootMargin = "0px 0px -10% 0px") {
  const [element, setElement] = useState<T | null>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    if (!element || seen) return;
    if (typeof IntersectionObserver === "undefined") {
      setSeen(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setSeen(true);
      },
      { rootMargin },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [element, seen, rootMargin]);
  return [setElement, seen] as const;
}

/** Content that rises gently into place the first time it scrolls into view. */
export function Reveal({
  children,
  delay = 0,
  className = "",
  as: Tag = "div",
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
  as?: ElementType;
}) {
  const [ref, seen] = useSeen<HTMLElement>();
  return (
    <Tag
      ref={ref}
      className={`${seen ? "animate-rise" : "opacity-0"} ${className}`}
      style={seen && delay ? { animationDelay: `${delay}ms` } : undefined}
    >
      {children}
    </Tag>
  );
}

/** A number that counts up from zero when it first appears. */
export function CountUp({ value, format = (n) => String(n) }: { value: number; format?: (n: number) => string }) {
  const [ref, seen] = useSeen<HTMLSpanElement>();
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (!seen) return;
    if (prefersReducedMotion()) {
      setShown(value);
      return;
    }
    const start = performance.now();
    const duration = 1100;
    let frame = 0;
    const step = (time: number) => {
      const progress = Math.min(1, (time - start) / duration);
      setShown(Math.round(value * (1 - Math.pow(1 - progress, 3))));
      if (progress < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [seen, value]);
  return (
    <span ref={ref} className="tabular-nums">
      {format(shown)}
      <span className="sr-only">{format(value)}</span>
    </span>
  );
}

/** A pulsing green dot that says "this is live". */
export function LiveDot({ className = "" }: { className?: string }) {
  return (
    <span className={`relative inline-flex size-2.5 ${className}`} aria-hidden="true">
      <span className="absolute inline-flex size-full animate-ping-soft rounded-full bg-leaf-500/70" />
      <span className="relative inline-flex size-2.5 rounded-full bg-leaf-500" />
    </span>
  );
}

function useTick(ms: number, active: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(id);
  }, [ms, active]);
  return now;
}

/** "Closes in 24:13", ticking every second in the last hour; turns orange in the last 30 minutes. */
export function Countdown({ to, label = "Closes in", className = "" }: { to: string; label?: string; className?: string }) {
  const target = new Date(to).getTime();
  const [soon, setSoon] = useState(() => target - Date.now() < 3_600_000);
  const now = useTick(soon ? 1000 : 30_000, true);
  const left = Math.max(0, target - now);
  useEffect(() => setSoon(left < 3_600_000), [left]);
  const minutes = Math.floor(left / 60_000);
  const text =
    left <= 0
      ? "Closed"
      : minutes >= 60
        ? `${Math.floor(minutes / 60)} h ${minutes % 60} min`
        : `${String(minutes).padStart(2, "0")}:${String(Math.floor((left % 60_000) / 1000)).padStart(2, "0")}`;
  const urgent = left > 0 && minutes < 30;
  return (
    <span className={`inline-flex items-center gap-1 font-semibold tabular-nums ${urgent ? "text-saffron-600" : "text-ink-700"} ${className}`}>
      <Timer className="size-3.5" aria-hidden="true" />
      {left > 0 && <span className="font-medium">{label}</span>} {text}
    </span>
  );
}

/** A slow, endless ticker of real deals. Pauses on hover; the copy is hidden from screen readers. */
export function DealTicker({ listings }: { listings: Listing[] }) {
  if (listings.length === 0) return null;
  const items = listings.slice(0, 14);
  const row = (hidden: boolean) =>
    items.map((listing) => (
      <Link
        key={`${listing.id}-${hidden}`}
        to={`/meals/${listing.id}`}
        tabIndex={hidden ? -1 : undefined}
        aria-hidden={hidden || undefined}
        className="group flex shrink-0 items-center gap-2.5 rounded-full bg-white/10 py-1.5 pr-4 pl-1.5 ring-1 ring-white/15 transition hover:bg-white/20"
      >
        <span className="size-8 overflow-hidden rounded-full">
          <Photo photo={photoForMeal(listing.meal_type, listing.title, listing.id)} sizes="32px" alt="" />
        </span>
        <span className="text-[13.5px] font-semibold whitespace-nowrap text-white">{listing.title}</span>
        <span className="text-[13.5px] font-bold whitespace-nowrap text-turmeric-300">{formatRupees(listing.price_paise)}</span>
        <span className="text-[12px] whitespace-nowrap text-white/60 line-through">{formatRupees(listing.original_price_paise)}</span>
      </Link>
    ));
  return (
    <div className="group/ticker relative overflow-hidden" aria-label="Live deals">
      <div className="flex w-max animate-marquee gap-3 group-hover/ticker:[animation-play-state:paused]">
        {row(false)}
        {row(true)}
      </div>
      <div className="pointer-events-none absolute inset-y-0 left-0 w-16 bg-gradient-to-r from-leaf-900 to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-16 bg-gradient-to-l from-leaf-900 to-transparent" />
    </div>
  );
}

/** A horizontal, swipeable row with previous/next buttons on larger screens. */
export function Rail({ children, label }: { children: ReactNode; label: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const scroll = (direction: 1 | -1) => ref.current?.scrollBy({ left: direction * ref.current.clientWidth * 0.85, behavior: "smooth" });
  return (
    <div className="relative">
      <div ref={ref} className="rail -mx-4 px-4 sm:-mx-6 sm:px-6 lg:mx-0 lg:px-0" role="region" aria-label={label} tabIndex={0}>
        {children}
      </div>
      <div className="pointer-events-none absolute top-[22%] -right-5 -left-5 hidden justify-between lg:flex">
        {([-1, 1] as const).map((direction) => (
          <button
            key={direction}
            type="button"
            onClick={() => scroll(direction)}
            className="pointer-events-auto grid size-11 place-items-center rounded-full bg-white text-ink-900 shadow-lift ring-1 ring-black/5 transition hover:scale-105 hover:bg-leaf-50"
            aria-label={direction === 1 ? `Scroll ${label} right` : `Scroll ${label} left`}
          >
            {direction === 1 ? <ChevronRight className="size-5" aria-hidden="true" /> : <ChevronLeft className="size-5" aria-hidden="true" />}
          </button>
        ))}
      </div>
    </div>
  );
}
