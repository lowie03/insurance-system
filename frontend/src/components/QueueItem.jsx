import { useState } from "react";

import ResolveForm from "./ResolveForm";
import { Button, Notice } from "./ui";
import { api } from "../api/client";
import { money } from "../lib/format";

const KINDS = {
  referral: { label: "Needs advice", tone: "bg-ochre-100 text-ochre-600" },
  stuck_payment: { label: "Paid, not covered", tone: "bg-clay-100 text-clay-600" },
  failed_payment: { label: "Payment failed", tone: "bg-paper-dim text-ink-soft" },
};

const REFERRAL_OUTCOMES = [
  { value: "contacted", label: "I contacted them", note: "Spoke to the customer about their options." },
  { value: "advised_subsidy", label: "Pointed them to a state scheme",
    note: "Nothing commercial fits their income." },
  { value: "no_action", label: "No action needed", note: "Closing without contact." },
];

const PAYMENT_OUTCOMES = [
  { value: "refunded", label: "I refunded them",
    note: "Refund done in the Paystack dashboard — this only records it." },
  { value: "issued_manually", label: "I issued the policy by hand", note: "Handled outside this system." },
  { value: "no_action", label: "No action needed", note: "Closing without action." },
];

export default function QueueItem({ item, token, onResolved }) {
  const [open, setOpen] = useState(false);
  const [resolved, setResolved] = useState(null);
  const kind = KINDS[item.kind];
  const isReferral = item.kind === "referral";

  return (
    <article className="rounded-2xl border border-ink/15 bg-white p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <span className={`inline-block rounded-full px-2.5 py-1 text-xs font-semibold ${kind.tone}`}>
            {kind.label}
          </span>
          <p className="mt-2 break-all font-mono text-sm text-ink-soft">
            {isReferral ? item.quote_id : item.reference}
          </p>
        </div>
        {!isReferral && (
          <p className="shrink-0 text-right">
            <span className="font-display text-xl font-bold">{money(item.amount_ngn)}</span>
            <span className="block text-sm text-ink-soft">taken from the customer</span>
          </p>
        )}
      </div>

      <p className="mt-3">{isReferral ? item.refer_reason : item.reason}</p>

      {isReferral && item.recommendations?.length > 0 && (
        <p className="mt-2 text-sm text-ink-soft">
          Suggested: {item.recommendations.map((r) => r.product_name).join(", ")}
        </p>
      )}
      {isReferral && item.excluded?.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-sm font-medium text-palm-500">
            {item.excluded.length} products ruled out
          </summary>
          <dl className="mt-2 space-y-1.5 text-sm">
            {item.excluded.map((exclusion) => (
              <div key={exclusion.product}>
                <dt className="font-medium">{exclusion.product_name}</dt>
                <dd className="text-ink-soft">{exclusion.reason}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
      {!isReferral && item.lines?.length > 0 && (
        <ul className="mt-2 text-sm text-ink-soft">
          {item.lines.map((line) => (
            <li key={line.product_code}>
              {line.product_name} — {money(line.payment_ngn)} {line.payment_plan}
            </li>
          ))}
        </ul>
      )}

      {resolved ? (
        <div className="mt-4"><Notice title="Recorded">{resolved.message}</Notice></div>
      ) : item.kind === "failed_payment" ? (
        <p className="mt-4 text-sm text-ink-soft">
          Nothing to do: the customer was not charged and holds no policy.
        </p>
      ) : open ? (
        <ResolveForm
          options={isReferral ? REFERRAL_OUTCOMES : PAYMENT_OUTCOMES}
          noteLabel="Note"
          submitLabel="Record this"
          onSubmit={({ outcome, note }) =>
            isReferral
              ? api.resolveReferral(token, item.quote_id, { outcome, note })
              : api.resolvePayment(token, item.reference, { outcome, note })}
          onDone={(result) => { setResolved(result); onResolved?.(item); }}
        />
      ) : (
        <Button variant="quiet" className="mt-4 w-full sm:w-auto" onClick={() => setOpen(true)}>
          Resolve this
        </Button>
      )}
    </article>
  );
}