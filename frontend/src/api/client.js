/** The only place that knows how to reach the backend. Pages never call fetch directly. */

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  constructor(message, { status, detail } = {}) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

/** FastAPI returns validation problems as a list of field errors; flatten them into readable lines. */
function readDetail(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = (d.loc ?? []).filter((p) => p !== "body").join(" › ");
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("\n");
  }
  if (detail && typeof detail === "object") return detail.message ?? JSON.stringify(detail);
  return null;
}

async function request(path, { method = "GET", body, signal } = {}) {
  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      signal,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (cause) {
    if (cause.name === "AbortError") throw cause;
    throw new ApiError("Can't reach the server. Check your connection and try again.", { status: 0 });
  }

  if (response.status === 204) return null;

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = readDetail(payload?.detail);
    throw new ApiError(detail ?? `Something went wrong (error ${response.status}).`, {
      status: response.status,
      detail: payload?.detail,
    });
  }
  return payload;
}

export const api = {
  health: () => request("/health"),
  createQuote: (body) => request("/quotes", { method: "POST", body }),
  getQuote: (quoteId) => request(`/quotes/${quoteId}`),
  previewBasket: (quoteId, items) => request(`/quotes/${quoteId}/basket`, { method: "POST", body: { items } }),
  startPayment: (body) => request("/payments/initialize", { method: "POST", body }),
  paymentStatus: (reference) => request(`/payments/${reference}`),
  recheckPayment: (reference) => request(`/payments/${reference}/verify`, { method: "POST" }),
  verifyPolicy: (policyNumber, signature) =>
    request(`/verify/${encodeURIComponent(policyNumber)}?s=${encodeURIComponent(signature)}`),
};