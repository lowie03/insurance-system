import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import ExclusionLedger from "../components/ExclusionLedger";
import ProductCard from "../components/ProductCard";
import Shell from "../components/Shell";
import { Button, Notice } from "../components/ui";
import { money } from "../lib/format";
import { useAsync } from "../lib/useAsync";

export default function Recommendations() {
  const { quoteId } = useParams();
  const navigate = useNavigate();
  // Coming from the form we already have the quote; on a refresh or shared link we fetch it.
  const [quote, setQuote] = useState(useLocation().state?.quote ?? null);
  const [chosen, setChosen] = useState([]);
  const [basket, setBasket] = useState(null);
  const [basketError, setBasketError] = useState(null);

  const load = useAsync(async () => setQuote(await api.getQuote(quoteId)));
  useEffect(() => { if (!quote) load.run(); }, [quote, quoteId]);

  // The first recommendation starts ticked, so the page has a sensible default.
  useEffect(() => {
    if (quote?.recommendations?.length && chosen.length === 0) {
      setChosen([quote.recommendations[0].product]);
    }
  }, [quote]);

  // Ask the server to price the selection whenever it changes: it applies the combined
  // budget and cash-flow rules, which the browser must never try to work out itself.
  useEffect(() => {
    if (!quote || chosen.length === 0) { setBasket(null); setBasketError(null); return; }
    let cancelled = false;
    api.previewBasket(quoteId, chosen.map((product_code) => ({ product_code })))
      .then((preview) => { if (!cancelled) { setBasket(preview); setBasketError(null); } })
      .catch((error) => { if (!cancelled) { setBasket(null); setBasketError(error.message); } });
    return () => { cancelled = true; };
  }, [quote, quoteId, chosen]);

  const byProduct = useMemo(
    () => Object.fromEntries((basket?.lines ?? []).map((line) => [line.product, line])),
    [basket],
  );

  function toggle(product) {
    setChosen((current) =>
      current.includes(product) ? current.filter((p) => p !== product) : [...current, product],
    );
  }

  if (load.pending || (!quote && !load.error)) {
    return <Shell><p className="py-10 text-center text-ink-soft">Loading your recommendations…</p></Shell>;
  }
  if (!quote) {
    return (
      <Shell>
        <Notice tone="warn" title="We couldn't open this quote">{load.error}</Notice>
        <Button className="mt-5 w-full" onClick={() => navigate("/")}>Start again</Button>
      </Shell>
    );
  }

  const { recommendations, excluded, refer_to_broker, refer_reason } = quote;

  return (
    <Shell size="wide" journey>
      <h1 className="font-display text-3xl font-extrabold leading-tight sm:text-4xl">What suits you</h1>
      <p className="mt-2 max-w-prose text-ink-soft">
        Based on what you told us. Pick as many as you want; we'll check the total against your budget.
      </p>

      {refer_to_broker && (
        <div className="mt-5">
          <Notice tone="warn" title="A broker should look at this with you">
            {refer_reason}
            {"\n"}You can still go ahead on your own, or ask a broker to review your situation first.
          </Notice>
        </div>
      )}

      {/* One column on a phone; products and running total side by side from lg upwards. */}
      <div className="mt-6 lg:grid lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start lg:gap-8">
        <div>
      {recommendations.length > 0 ? (
        <div className="space-y-3 sm:space-y-4">
          {recommendations.map((rec, index) => (
            <ProductCard
              key={rec.product}
              rank={index}
              // While a preview is loading, keep showing the quote's own pricing for this product.
              line={byProduct[rec.product] ?? rec}
              selected={chosen.includes(rec.product)}
              onToggle={() => toggle(rec.product)}
            />
          ))}
        </div>
      ) : (
        <div>
          {/* When the referral notice above already explains this, don't say it twice. */}
          {refer_to_broker ? (
            <p className="text-ink-soft">
              Nothing on our list is affordable for you at the moment, so there's nothing to select here.
            </p>
          ) : (
            <Notice tone="warn" title="Nothing here fits your budget right now">
              Everything available costs more than we think you can comfortably afford. A broker can point
              you towards a subsidised state health scheme instead.
            </Notice>
          )}
        </div>
      )}

          <ExclusionLedger excluded={excluded} />
        </div>

      {/* The cost stays in view either way: pinned to the bottom on a phone, a sticky panel on a wide screen. */}
      {(basket || basketError) && (
        <aside className="sticky bottom-0 -mx-5 mt-8 border-t border-ink/15 bg-paper/95 px-5 py-4 backdrop-blur
                          sm:-mx-8 sm:px-8
                          lg:top-8 lg:bottom-auto lg:mx-0 lg:mt-0 lg:rounded-2xl lg:border lg:bg-white lg:px-5 lg:py-5 lg:backdrop-blur-none">
          {basketError ? (
            <Notice tone="warn" title="That combination doesn't work">{basketError}</Notice>
          ) : (
            <>
              <div className="flex items-baseline justify-between gap-4 lg:block">
                <div>
                  <p className="text-sm text-ink-soft">
                    {chosen.length} {chosen.length === 1 ? "policy" : "policies"} · first payment
                  </p>
                  <p className="font-display text-3xl font-extrabold leading-tight">
                    {money(basket.first_payment_ngn)}
                  </p>
                </div>
                <p className="text-right text-sm text-ink-soft lg:mt-3 lg:text-left">
                  {money(basket.total_annual_ngn)} a year
                  <br />
                  {money(basket.budget_remaining_ngn)} of budget left
                </p>
              </div>

              {basket.notes?.length > 0 && (
                <ul className="mt-3 space-y-1 text-sm text-ink-soft">
                  {basket.notes.map((note) => <li key={note}>{note}</li>)}
                </ul>
              )}

              <Button
                variant="accent"
                className="mt-4 w-full"
                onClick={() => navigate(`/quotes/${quoteId}/checkout`, { state: { quote, chosen, basket } })}
              >
                Continue to payment
              </Button>
            </>
          )}
        </aside>
      )}
      </div>
    </Shell>
  );
}