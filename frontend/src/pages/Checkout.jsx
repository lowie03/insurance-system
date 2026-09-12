import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import Shell from "../components/Shell";
import { Button, LedgerRow, Notice } from "../components/ui";
import { money, planSummary } from "../lib/format";
import { useAsync } from "../lib/useAsync";

export default function Checkout() {
  const { quoteId } = useParams();
  const navigate = useNavigate();
  const passed = useLocation().state ?? {};
  const [basket, setBasket] = useState(passed.basket ?? null);
  const [loadError, setLoadError] = useState(null);
  const chosen = passed.chosen ?? [];

  // On a refresh the selection is gone, so send the person back rather than guessing what they picked.
  useEffect(() => {
    if (basket || chosen.length === 0) return;
    api.previewBasket(quoteId, chosen.map((product_code) => ({ product_code })))
      .then(setBasket)
      .catch((error) => setLoadError(error.message));
  }, [basket, chosen, quoteId]);

  const pay = useAsync(async () => {
    const payment = await api.startPayment({
      quote_id: quoteId,
      items: basket.lines.map((line) => ({ product_code: line.product, payment_plan: line.payment_plan })),
    });
    // Remember the reference before leaving: Paystack takes over the tab from here.
    sessionStorage.setItem("lastPaymentReference", payment.reference);
    window.location.assign(payment.authorization_url);
  });

  if (!basket) {
    return (
      <Shell journey>
        <Notice tone="warn" title="We've lost your selection">
          {loadError ?? "Go back and choose your cover again."}
        </Notice>
        <Button className="mt-5 w-full" onClick={() => navigate(`/quotes/${quoteId}`)}>
          Back to your options
        </Button>
      </Shell>
    );
  }

  const switched = basket.lines.filter((line) =>
    line.notes?.some((note) => note.startsWith("monthly payments suggested")),
  );

  return (
    <Shell journey>
      <h1 className="font-display text-3xl font-extrabold leading-tight sm:text-4xl">Check and pay</h1>
      <p className="mt-2 max-w-prose text-ink-soft">
        Paying starts your cover today. Each policy runs for a year from now.
      </p>

      <section className="mt-6 rounded-2xl border border-ink/15 bg-white p-4">
        {basket.lines.map((line) => (
          <div key={line.product} className="border-b border-ink/10 py-3 first:pt-0 last:border-0 last:pb-0">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="font-medium">{line.product_name}</h2>
              <span className="shrink-0 font-medium">{money(line.payment_ngn)}</span>
            </div>
            <p className="text-sm text-ink-soft">{planSummary(line)}</p>
          </div>
        ))}

        <div className="mt-3 border-t border-ink/15 pt-2">
          <LedgerRow label="Cover for a year" amount={money(basket.total_annual_ngn)} muted />
          <LedgerRow label="Left of your yearly budget" amount={money(basket.budget_remaining_ngn)} muted />
        </div>

        <div className="mt-3 flex items-baseline justify-between gap-3 border-t-2 border-palm-700 pt-3">
          <span className="font-medium">To pay now</span>
          <span className="font-display text-2xl font-extrabold">{money(basket.first_payment_ngn)}</span>
        </div>
      </section>

      {switched.length > 0 && (
        <div className="mt-4">
          <Notice title="Why some of these are monthly">
            {`Paying for ${switched.map((l) => l.product_name).join(" and ")} in one go would take too much `}
            {"of a single month's income, so we've spread it. Monthly costs a little more in total."}
          </Notice>
        </div>
      )}

      {pay.error && (
        <div className="mt-4"><Notice tone="warn" title="We couldn't start the payment">{pay.error}</Notice></div>
      )}

      <div className="mt-6 flex flex-col gap-3 sm:flex-row-reverse">
        <Button variant="accent" className="sm:flex-1" disabled={pay.pending} onClick={pay.run}>
          {pay.pending ? "Opening Paystack…" : `Pay ${money(basket.first_payment_ngn)} with Paystack`}
        </Button>
        <Button variant="quiet" disabled={pay.pending} onClick={() => navigate(`/quotes/${quoteId}`)}>
          Change my cover
        </Button>
      </div>

      <p className="mt-4 text-sm text-ink-soft">
        Payment is handled by Paystack. This prototype runs in test mode, so no real money moves.
      </p>
    </Shell>
  );
}