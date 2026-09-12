/** The part most insurance sites hide: everything we will NOT sell this person, and why.
    Kept deliberately prominent — it's the clearest evidence the system isn't just upselling. */
export default function ExclusionLedger({ excluded }) {
  if (!excluded?.length) return null;

  const groups = [
    { kind: "affordability", heading: "Too expensive for your income",
      note: "We only suggest cover costing up to 5% of what you earn in a year." },
    { kind: "eligibility", heading: "Doesn't apply to you",
      note: "These need something you told us you don't have." },
  ];

  return (
    <section className="mt-10">
      <h2 className="font-display text-2xl font-bold">What we ruled out</h2>
      <p className="mt-1 text-ink-soft">
        Every product we didn't recommend, and the reason. Nothing is hidden from you.
      </p>

      <div className="mt-5 space-y-6">
        {groups.map(({ kind, heading, note }) => {
          const items = excluded.filter((item) => item.kind === kind);
          if (!items.length) return null;
          return (
            <div key={kind} className="border-l-2 border-clay-600/40 pl-4">
              <h3 className="font-medium">{heading}</h3>
              <p className="text-sm text-ink-soft">{note}</p>
              <dl className="mt-3 space-y-3">
                {items.map((item) => (
                  <div key={item.product}>
                    <dt className="text-sm font-medium">{item.product_name}</dt>
                    <dd className="text-sm text-ink-soft">{item.reason}</dd>
                  </div>
                ))}
              </dl>
            </div>
          );
        })}
      </div>
    </section>
  );
}