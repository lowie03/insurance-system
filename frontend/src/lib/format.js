const naira = new Intl.NumberFormat("en-NG", {
  style: "currency", currency: "NGN", maximumFractionDigits: 0,
});

export const money = (amount) => naira.format(amount ?? 0);

/** "₦2,590/month for 12 months" vs "₦15,000 once" — say the shape of the commitment, not just the number. */
export function planSummary(line) {
  return line.payment_plan === "monthly"
    ? `${money(line.payment_ngn)} a month for 12 months`
    : `${money(line.payment_ngn)} once a year`;
}

export const longDate = (iso) =>
  new Date(iso).toLocaleDateString("en-NG", { day: "numeric", month: "long", year: "numeric" });