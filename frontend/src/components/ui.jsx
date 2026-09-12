/** Small shared pieces. Kept in one file while the set is small. */

export function Button({ as: Tag = "button", variant = "primary", className = "", ...props }) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-xl px-5 py-3.5 text-base font-medium " +
    "transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
  const variants = {
    primary: "bg-palm-700 text-paper hover:bg-palm-900",
    accent: "bg-ochre-500 text-palm-900 font-semibold hover:bg-ochre-600",
    quiet: "border border-ink/20 text-ink hover:border-ink/40 hover:bg-paper-dim",
  };
  return <Tag className={`${base} ${variants[variant]} ${className}`} {...props} />;
}

export function Field({ label, hint, error, children, id }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-base font-medium">{label}</label>
      {hint && <p className="text-sm text-ink-soft">{hint}</p>}
      {children}
      {error && <p className="text-sm text-clay-600">{error}</p>}
    </div>
  );
}

const control =
  "w-full rounded-xl border border-ink/20 bg-white px-4 py-3.5 text-base " +
  "focus:border-palm-500 focus:outline-none focus:ring-2 focus:ring-palm-500/30";

export const Input = (props) => <input className={control} {...props} />;

export const Select = ({ children, ...props }) => (
  <select className={`${control} appearance-none`} {...props}>{children}</select>
);

/** Big tap targets: on a phone these are far easier than a dropdown. */
export function Choice({ options, value, onChange, name, columns = 2 }) {
  return (
    <div className={`grid gap-2 ${columns === 1 ? "grid-cols-1" : "grid-cols-2"}`}>
      {options.map((option) => {
        const selected = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(option.value)}
            className={`rounded-xl border px-4 py-3.5 text-left text-base transition-colors ${
              selected
                ? "border-palm-700 bg-palm-700 text-paper"
                : "border-ink/20 bg-white hover:border-palm-500"
            }`}
          >
            <span className="block font-medium">{option.label}</span>
            {option.note && (
              <span className={`block text-sm ${selected ? "text-palm-100" : "text-ink-soft"}`}>
                {option.note}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function Toggle({ label, hint, checked, onChange, id }) {
  return (
    <button
      type="button"
      id={id}
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex w-full items-start gap-3 rounded-xl border border-ink/20 bg-white px-4 py-3.5 text-left hover:border-palm-500"
    >
      <span
        className={`mt-0.5 flex h-6 w-11 shrink-0 rounded-full p-0.5 transition-colors ${
          checked ? "bg-palm-700" : "bg-ink/20"
        }`}
      >
        <span className={`h-5 w-5 rounded-full bg-white transition-transform ${checked ? "translate-x-5" : ""}`} />
      </span>
      <span>
        <span className="block font-medium">{label}</span>
        {hint && <span className="block text-sm text-ink-soft">{hint}</span>}
      </span>
    </button>
  );
}

export function Notice({ tone = "info", title, children }) {
  const tones = {
    info: "border-palm-500/30 bg-palm-100/50",
    warn: "border-clay-600/30 bg-clay-100",
  };
  return (
    <div className={`rounded-xl border px-4 py-3 ${tones[tone]}`}>
      {title && <p className="font-medium">{title}</p>}
      <div className="text-sm text-ink-soft whitespace-pre-line">{children}</div>
    </div>
  );
}

/** label .......... amount */
export function LedgerRow({ label, amount, muted = false }) {
  return (
    <div className={`ledger-row ${muted ? "text-ink-soft" : ""}`}>
      <span className="text-sm">{label}</span>
      <span className="ledger-fill" aria-hidden="true" />
      <span className="text-sm font-medium">{amount}</span>
    </div>
  );
}