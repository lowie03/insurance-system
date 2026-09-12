import { LedgerRow } from "./ui";
import { money } from "../lib/format";

/** The same steps the PDF certificate prints: how the price was built, line by line. */
export default function PremiumBreakdown({ steps, total }) {
  return (
    <div className="rounded-lg bg-paper-dim/70 px-4 py-2">
      {steps.map((step, index) => (
        <LedgerRow key={index} label={step.step} amount={money(step.running_total_ngn)} muted />
      ))}
      <div className="border-t border-ink/15">
        <LedgerRow label="A year of cover" amount={money(total)} />
      </div>
    </div>
  );
}