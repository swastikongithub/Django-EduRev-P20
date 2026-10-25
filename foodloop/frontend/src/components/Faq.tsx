import { Plus } from "lucide-react";

import type { FaqItem } from "../lib/faq";

/** Questions that open and close. Built on <details>, so it works with a keyboard and screen readers. */
export function FaqList({ items }: { items: FaqItem[] }) {
  return (
    <div className="divide-y divide-line overflow-hidden rounded-[1.25rem] border border-line/80 bg-panel shadow-soft">
      {items.map((item) => (
        <details key={item.q} className="group">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4 text-[15.5px] font-semibold text-fg transition hover:bg-panel sm:px-6 [&::-webkit-details-marker]:hidden">
            {item.q}
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-brand-950 text-brand-400 transition duration-300 group-open:rotate-45 group-open:bg-brand-500 group-open:text-night">
              <Plus className="size-4" aria-hidden="true" />
            </span>
          </summary>
          <p className="animate-fade px-5 pb-5 text-[15px] leading-relaxed text-fg-soft sm:px-6">{item.a}</p>
        </details>
      ))}
    </div>
  );
}
