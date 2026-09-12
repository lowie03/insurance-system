import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import Shell from "../components/Shell";
import { Button } from "../components/ui";
import { longDate } from "../lib/format";

/** What the QR code on a certificate opens. PUBLIC: anyone can check a policy is genuine,
    so it shows a status, the product and the expiry date — never a name, amount or contact detail. */
const OUTCOMES = {
  VALID: { headline: "This policy is genuine", tone: "good",
           detail: "It was issued by this system and is still in force." },
  EXPIRED: { headline: "This policy has expired", tone: "warn",
             detail: "It was genuine, but the cover period has ended." },
  CANCELLED: { headline: "This policy was cancelled", tone: "warn",
               detail: "It was issued by this system, then cancelled." },
  NOT_FOUND: { headline: "No policy with this number", tone: "bad",
               detail: "Nothing was ever issued under this number. Check it was typed correctly." },
  INVALID_NUMBER: { headline: "That isn't a valid policy number", tone: "bad",
                    detail: "The number doesn't pass our check digit, so it contains a typo or was made up." },
  SIGNATURE_MISMATCH: { headline: "This certificate has been altered", tone: "bad",
                        detail: "A policy with this number exists, but the details on the certificate don't match "
                              + "what we issued. Treat it as a forgery." },
};

const TONES = {
  good: "border-palm-500 bg-palm-100/60",
  warn: "border-ochre-600 bg-ochre-100",
  bad: "border-clay-600 bg-clay-100",
};

export default function VerifyPolicy() {
  const { policyNumber } = useParams();
  const [params] = useSearchParams();
  const signature = params.get("s") ?? "";
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let stop = false;
    api.verifyPolicy(policyNumber, signature)
      .then((body) => { if (!stop) setResult(body); })
      .catch((e) => { if (!stop) setError(e.message); });
    return () => { stop = true; };
  }, [policyNumber, signature]);

  const outcome = result ? OUTCOMES[result.status] ?? OUTCOMES.NOT_FOUND : null;

  return (
    <Shell step="Policy check">
      <h1 className="font-display text-3xl font-extrabold leading-tight sm:text-4xl">Policy check</h1>
      <p className="mt-2 break-all font-mono text-sm text-ink-soft">{policyNumber}</p>

      {error && <p className="mt-6 text-clay-600">{error}</p>}
      {!result && !error && <p className="mt-6 text-ink-soft">Checking…</p>}

      {outcome && (
        <>
          <div className={`mt-6 rounded-2xl border-2 p-5 sm:p-6 ${TONES[outcome.tone]}`}>
            <p className="font-display text-2xl font-extrabold leading-tight sm:text-3xl">{outcome.headline}</p>
            <p className="mt-2">{outcome.detail}</p>
          </div>

          {result.product_name && (
            <dl className="mt-6 max-w-md space-y-2">
              <div className="flex justify-between gap-4 border-b border-ink/10 pb-2">
                <dt className="text-ink-soft">Cover</dt>
                <dd className="font-medium">{result.product_name}</dd>
              </div>
              {result.valid_until && (
                <div className="flex justify-between gap-4 border-b border-ink/10 pb-2">
                  <dt className="text-ink-soft">
                    {result.status === "VALID" ? "Valid until" : "Cover period ended"}
                  </dt>
                  <dd className="font-medium">{longDate(result.valid_until)}</dd>
                </div>
              )}
            </dl>
          )}

          <p className="mt-6 max-w-prose text-sm text-ink-soft">
            This check shows only whether the policy is real and in force. The policyholder&apos;s name and
            the amount they paid are never shown here.
          </p>
        </>
      )}

      <Button as={Link} variant="quiet" to="/" className="mt-8">Get cover yourself</Button>
    </Shell>
  );
}