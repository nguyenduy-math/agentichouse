const BASE = "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: () => request("/health"),

  uploadClaims: (file) => {
    const form = new FormData();
    form.append("file", file);
    return request("/claims/upload", { method: "POST", body: form });
  },

  listClaims: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/claims${qs ? "?" + qs : ""}`);
  },

  getClaim: (id) => request(`/claims/${id}`),

  reviewQueue: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/review/queue${qs ? "?" + qs : ""}`);
  },

  submitDecision: (claimId, body) =>
    request(`/review/${claimId}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  reviewStats: () => request("/review/stats"),

  triggerBatch: () => request("/batch/run", { method: "POST" }),

  batchStatus: () => request("/batch/status"),

  modelStatus: () => request("/batch/model-status"),

  trainModel: () => request("/batch/train", { method: "POST" }),
};
