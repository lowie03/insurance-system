import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import QueueItem from "../components/QueueItem";
import Shell from "../components/Shell";
import { Button, Field, Input, Notice } from "../components/ui";
import { useAsync } from "../lib/useAsync";

const FILTERS = [
  { value: "", label: "Everything" },
  { value: "referral", label: "Needs advice" },
  { value: "stuck_payment", label: "Paid, not covered" },
  { value: "failed_payment", label: "Payment failed" },
];

/** The broker's working list. Deliberately plain: a broker uses this all day and wants density,
    not the reassurance the customer pages are designed to give. */
export default function BrokerQueue() {
  // The token lives in memory only. Storing it would leave it on any shared machine.
  const [token, setToken] = useState("");
  const [signedIn, setSignedIn] = useState(false);
  const [kind, setKind] = useState("");
  const [items, setItems] = useState([]);
  const [hasMore, setHasMore] = useState(false);

  const load = useAsync(async (nextKind = kind, offset = 0) => {
    const page = await api.brokerQueue(token, { kind: nextKind || undefined, offset });
    setItems((current) => (offset === 0 ? page.items : [...current, ...page.items]));
    setHasMore(page.has_more);
    setSignedIn(true);
    return page;
  });

  const signIn = useCallback(() => load.run(kind, 0), [load, kind]);

  useEffect(() => { if (signedIn) load.run(kind, 0); }, [kind, signedIn]);

  if (!signedIn) {
    return (
      <Shell step="Broker">
        <h1 className="font-display text-3xl font-extrabold leading-tight sm:text-4xl">Broker queue</h1>
        <p className="mt-2 max-w-prose text-ink-soft">
          Customers who need a person: those the system couldn&apos;t match, and those whose payment went
          through without a policy.
        </p>

        <div className="mt-6 max-w-md space-y-4">
          <Field label="Broker token" id="token">
            <Input id="token" type="password" autoComplete="off" value={token}
                   onChange={(event) => setToken(event.target.value)}
                   onKeyDown={(event) => event.key === "Enter" && token && signIn()} />
          </Field>
          {load.error && <Notice tone="warn" title="That didn't work">{load.error}</Notice>}
          <Button onClick={signIn} disabled={!token || load.pending} className="w-full sm:w-auto">
            {load.pending ? "Checking…" : "Open the queue"}
          </Button>
          <p className="text-sm text-ink-soft">
            One shared token for all brokers, so the audit log records that a broker acted, not which one.
            Individual accounts are still to come.
          </p>
        </div>
      </Shell>
    );
  }

  return (
    <Shell step="Broker" size="wide">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="font-display text-3xl font-extrabold leading-tight sm:text-4xl">Broker queue</h1>
        <Button variant="quiet" onClick={() => load.run(kind, 0)} disabled={load.pending}>
          {load.pending ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {FILTERS.map((filter) => (
          <button
            key={filter.value}
            type="button"
            aria-pressed={kind === filter.value}
            onClick={() => setKind(filter.value)}
            className={`rounded-full border px-4 py-2 text-sm transition-colors ${
              kind === filter.value
                ? "border-palm-700 bg-palm-700 text-paper"
                : "border-ink/20 hover:border-palm-500"
            }`}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {load.error && <div className="mt-5"><Notice tone="warn">{load.error}</Notice></div>}

      {items.length === 0 && !load.pending ? (
        <p className="mt-10 text-ink-soft">
          Nothing waiting. Every customer was either matched or has already been dealt with.
        </p>
      ) : (
        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          {items.map((item) => (
            <QueueItem
              key={item.quote_id ?? item.reference}
              item={item}
              token={token}
              onResolved={() => {}}
            />
          ))}
        </div>
      )}

      {hasMore && (
        <Button variant="quiet" className="mt-6 w-full sm:w-auto" disabled={load.pending}
                onClick={() => load.run(kind, items.length)}>
          Load more
        </Button>
      )}
    </Shell>
  );
}