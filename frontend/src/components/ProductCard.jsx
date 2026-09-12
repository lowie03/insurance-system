import { useState } from "react";

import PremiumBreakdown from "./PremiumBreakdown";
import { money, planSummary } from "../lib/format";

/** One recommended product: what it is, what it costs, and how that cost was reached. */
export default function ProductCard({ line, selected, onToggle, rank }) {
  const [showWorking, setShowWorking] = useState(false);

  return (
    <article
      className={`rounded-2xl border bg-white transition-colors ${
        selected ? "border-palm-700 ring-1 ring-palm-700" : "border-ink/15"
      }`}
    >
      <label className="flex cursor-pointer items-start gap-3 p-4">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          className="mt-1 h-5 w-5 shrink-0 accent-[#0C3B36]"
        />
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-3">
            <span className="font-display text-xl font-bold leading-tight">{line.product_name}</span>
            {rank === 0 && (
              <span className="shrink-0 rounded-full bg-ochre-100 px-2.5 py-1 text-xs font-semibold text-ochre-600">
                Best fit
              </span>
            )}
          </span>
          <span className="mt-1 block text-lg font-semibold text-palm-700">{planSummary(line)}</span>
          {line.payment_plan === "monthly" && (
            <span className="block text-sm text-ink-soft">{money(line.total_ngn)} over the year</span>
          )}
        </span>
      </label>

      {line.notes?.length > 0 && (
        <ul className="space-y-1.5 px-4 pb-3 text-sm text-ink-soft">
          {line.notes.map((note) => (
            <li key={note} className="flex gap-2">
              <span aria-hidden="true" className="text-ochre-600">•</span>
              <span>{note}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="border-t border-ink/10 px-4 py-2">
        <button
          type="button"
          onClick={() => setShowWorking((open) => !open)}
          aria-expanded={showWorking}
          className="text-sm font-medium text-palm-500 underline underline-offset-4"
        >
          {showWorking ? "Hide how this price was worked out" : "How was this price worked out?"}
        </button>
      </div>

      {showWorking && (
        <div className="px-4 pb-4">
          <PremiumBreakdown steps={line.breakdown} total={line.premium_ngn} />
        </div>
      )}
    </article>
  );
}