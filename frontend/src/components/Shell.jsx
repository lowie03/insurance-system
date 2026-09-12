import { Link, useLocation } from "react-router-dom";

/** The customer journey, shown in the header so people always know where they are and what's left. */
const JOURNEY = [
  { key: "quote", label: "Your details", match: (path) => path === "/" },
  { key: "options", label: "Your options", match: (path) => /^\/quotes\/[^/]+$/.test(path) },
  { key: "pay", label: "Pay", match: (path) => path.endsWith("/checkout") || path === "/payment" },
];

function Mark() {
  // A shield drawn as a policy document: the subject matter, not a generic logo shape.
  return (
    <span className="flex items-center gap-2">
      <svg viewBox="0 0 24 28" aria-hidden="true" className="h-6 w-6">
        <path d="M12 1 22 4v11c0 6-4.6 10.4-10 13C6.6 25.4 2 21 2 15V4l10-3Z"
              fill="currentColor" opacity="0.25" />
        <path d="M12 1 22 4v11c0 6-4.6 10.4-10 13C6.6 25.4 2 21 2 15V4l10-3Z"
              fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path d="M7.5 10.5h9M7.5 14h9M7.5 17.5h5.5"
              stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
      <span className="font-display text-xl font-extrabold tracking-tight sm:text-2xl">Cover</span>
    </span>
  );
}

export default function Shell({ children, step, size = "narrow", journey = false }) {
  const width = size === "wide" ? "max-w-6xl" : "max-w-2xl";
  const { pathname } = useLocation();
  const current = JOURNEY.findIndex((stage) => stage.match(pathname));

  return (
    <div className="flex min-h-dvh flex-col bg-paper">
      <header className="sticky top-0 z-20 bg-palm-700 text-paper">
        <div className={`mx-auto flex ${width} items-center justify-between gap-4 px-5 py-3.5 sm:px-8`}>
          <Link to="/" className="shrink-0 hover:text-ochre-500" aria-label="Cover, start a new quote">
            <Mark />
          </Link>

          {journey && current >= 0 ? (
            <nav aria-label="Progress" className="min-w-0">
              <ol className="flex items-center gap-2 sm:gap-3">
                {JOURNEY.map((stage, index) => {
                  const state = index < current ? "done" : index === current ? "now" : "later";
                  return (
                    <li key={stage.key} className="flex items-center gap-2 sm:gap-3">
                      {index > 0 && (
                        <span aria-hidden="true"
                              className={`h-px w-4 sm:w-8 ${index <= current ? "bg-ochre-500" : "bg-palm-100/35"}`} />
                      )}
                      <span
                        aria-current={state === "now" ? "step" : undefined}
                        className={
                          state === "now"
                            ? "text-sm font-semibold text-ochre-500 sm:text-base"
                            : state === "done"
                              ? "text-sm text-palm-100 sm:text-base"
                              : "text-sm text-palm-100/50 sm:text-base"
                        }
                      >
                        {/* On a phone only the current stage is named; the dots carry the rest. */}
                        <span className={state === "now" ? "" : "hidden sm:inline"}>{stage.label}</span>
                        <span aria-hidden="true" className={state === "now" ? "hidden" : "sm:hidden"}>
                          <span className={`block h-2 w-2 rounded-full ${
                            state === "done" ? "bg-palm-100" : "bg-palm-100/40"}`} />
                        </span>
                      </span>
                    </li>
                  );
                })}
              </ol>
            </nav>
          ) : (
            step && <span className="truncate text-sm text-palm-100 sm:text-base">{step}</span>
          )}
        </div>
      </header>

      <main className={`mx-auto w-full ${width} grow px-5 py-7 sm:px-8 sm:py-10`}>{children}</main>

      <footer className="mt-4 border-t border-ink/10">
        <div className={`mx-auto w-full ${width} px-5 py-6 sm:px-8`}>
          <p className="max-w-prose text-sm text-ink-soft">
            A university research prototype. Certificates issued here are marked as prototypes and are not
            valid insurance contracts.
          </p>
        </div>
      </footer>
    </div>
  );
}