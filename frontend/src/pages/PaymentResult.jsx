import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import Shell from "../components/Shell";
import { Button, Notice } from "../components/ui";
import { longDate, money } from "../lib/format";
import { useAsync } from "../lib/useAsync";

/** Where Paystack returns the customer. The webhook may already have issued the policies,
    so we ask the server, and keep asking for a short while if it's still catching up. */
export default function PaymentResult() {
  const [params] = useSearchParams();
  const reference = params.get("reference") ?? sessionStorage.getItem("lastPaymentReference");
  const [payment, setPayment] = useState(null);
  const [attempts, setAttempts] = useState(0);

  const recheck = useAsync(async () => setPayment(await api.recheckPayment(reference)));

  useEffect(() => {
    if (!reference) return;
    let stop = false;
    api.recheckPayment(reference)
      .then((result) => { if (!stop) setPayment(result); })
      .catch(() => api.paymentStatus(reference).then((result) => { if (!stop) setPayment(result); }).catch(() => {}));
    return () => { stop = true; };
  }, [reference]);

  // Still "initialized" right after paying usually means the confirmation is a second behind. Retry a few times.
  useEffect(() => {
    if (payment?.status !== "initialized" || attempts >= 5) return;
    const timer = setTimeout(() => {
      setAttempts((n) => n + 1);
      api.recheckPayment(reference).then(setPayment).catch(() => {});
    }, 2000);
    return () => clearTimeout(timer);
  }, [payment, attempts, reference]);

  if (!reference) {
    return (
      <Shell>
        <Notice tone="warn" title="We don't know which payment this is">
          Open the link from your email, or start again.
        </Notice>
        <Button as={Link} to="/" className="mt-5 w-full">Start again</Button>
      </Shell>
    );
  }

  if (!payment) {
    return <Shell journey><p className="py-10 text-center text-ink-soft">Checking your payment…</p></Shell>;
  }

  if (payment.status === "issued") {
    return (
      <Shell size="wide" journey>
        <p className="font-display text-sm font-semibold uppercase tracking-wide text-palm-500">
          You&apos;re covered
        </p>
        <h1 className="mt-1 font-display text-3xl font-extrabold leading-tight sm:text-4xl">
          {payment.policies.length === 1 ? "Your policy is ready" : `Your ${payment.policies.length} policies are ready`}
        </h1>
        <p className="mt-2 max-w-prose text-ink-soft">
          Keep these certificates. Anyone can check they&apos;re genuine using the QR code on them.
        </p>

        <div className="mt-6 grid gap-4 md:grid-cols-2">
          {payment.policies.map((policy) => (
            <article key={policy.policy_number} className="rounded-2xl border border-ink/15 bg-white p-4">
              <h2 className="font-display text-xl font-bold">{policy.product_name}</h2>
              <dl className="mt-3 space-y-1 text-sm">
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-soft">Policy number</dt>
                  <dd className="font-medium">{policy.policy_number}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-soft">Covered until</dt>
                  <dd className="font-medium">{longDate(policy.end_date)}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-soft">You pay</dt>
                  <dd className="font-medium">
                    {policy.payment_plan === "monthly"
                      ? `${money(policy.payment_ngn)} a month`
                      : `${money(policy.payment_ngn)} a year`}
                  </dd>
                </div>
              </dl>
              <div className="mt-4 flex gap-3">
                <Button as="a" href={policy.certificate_url} target="_blank" rel="noopener"
                        className="flex-1">Download certificate</Button>
                <Button as="a" variant="quiet" href={policy.verify_url} target="_blank" rel="noopener">
                  Check it
                </Button>
              </div>
            </article>
          ))}
        </div>

        <div className="mt-6 max-w-prose">
        <Notice title="One thing to know">
          This is a university research prototype. The certificates are marked as prototypes and are not
          valid insurance contracts.
        </Notice>
        </div>
      </Shell>
    );
  }

  const states = {
    initialized: {
      title: "We haven't seen your payment yet",
      tone: "info",
      body: "If you've just paid, give it a moment. If you closed Paystack before finishing, nothing was charged.",
    },
    failed: {
      title: "That payment didn't go through",
      tone: "warn",
      body: `${payment.message} Nothing was charged to you, and no policy was issued.`,
    },
    paid_not_issued: {
      title: "We've got your payment, but the policy is on hold",
      tone: "warn",
      body: `${payment.message} Quote this reference when they contact you: ${payment.reference}`,
    },
  }[payment.status];

  return (
    <Shell journey>
      <h1 className="font-display text-3xl font-extrabold leading-tight sm:text-4xl">{states.title}</h1>
      <div className="mt-5 max-w-prose">
        <Notice tone={states.tone}>{states.body}</Notice>
      </div>

      {payment.status === "initialized" && (
        <Button className="mt-5 w-full sm:w-auto" disabled={recheck.pending} onClick={recheck.run}>
          {recheck.pending ? "Checking…" : "Check again"}
        </Button>
      )}
      <Button as={Link} variant="quiet" to="/" className="mt-3 w-full sm:ml-3 sm:w-auto">Start a new quote</Button>
    </Shell>
  );
}