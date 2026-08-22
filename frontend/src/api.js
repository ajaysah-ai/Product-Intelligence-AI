const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function handle(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok && !data.error) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return data;
}

export async function importDataset(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/import-dataset`, { method: "POST", body: form });
  return handle(res);
}

export async function submitRequest({ text, files, sourcesSelected }) {
  const form = new FormData();
  if (text) form.append("text", text);
  for (const f of files || []) form.append("files", f);
  if (sourcesSelected) form.append("sources_selected", JSON.stringify(sourcesSelected));
  const res = await fetch(`${API_BASE}/submit`, { method: "POST", body: form });
  return handle(res);
}

export async function listRequests() {
  const res = await fetch(`${API_BASE}/requests`);
  return handle(res);
}

export async function getRequestDetail(requestId) {
  const res = await fetch(`${API_BASE}/requests/${requestId}`);
  return handle(res);
}

export async function runExtract(requestId) {
  const res = await fetch(`${API_BASE}/extract/${requestId}`, { method: "POST" });
  return handle(res);
}

export async function runChunkAndEmbed(requestId) {
  const res = await fetch(`${API_BASE}/chunk-and-embed/${requestId}`, { method: "POST" });
  return handle(res);
}

export async function runOrchestrate(requestId, urls = {}) {
  const res = await fetch(`${API_BASE}/orchestrate/${requestId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ urls }),
  });
  return handle(res);
}

export async function approveRequest(requestId, overrides = {}) {
  const res = await fetch(`${API_BASE}/approve/${requestId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(overrides),
  });
  return handle(res);
}
