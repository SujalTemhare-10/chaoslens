async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

export const api = {
  health: () => request("/api/health"),
  analyze: (compose) => request("/api/analyze", { method: "POST", body: JSON.stringify({ compose }) }),
  projects: () => request("/api/projects"),
  project: (name) => request(`/api/projects/${encodeURIComponent(name)}`),
  runExperiment: (body) => request("/api/experiments", { method: "POST", body: JSON.stringify(body) }),
  runCampaign: (body) => request("/api/campaigns", { method: "POST", body: JSON.stringify(body) }),
  campaign: (id) => request(`/api/campaigns/${id}`),
  history: (project) => request(`/api/experiments?project=${encodeURIComponent(project)}`),
  report: (project) => request(`/api/projects/${encodeURIComponent(project)}/report`),
};

export function streamExperiment(id, onMessage) {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${window.location.host}/api/experiments/${id}/stream`);
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  return () => ws.close();
}
