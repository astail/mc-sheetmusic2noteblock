// バックエンド API の薄い fetch ラッパ(docs/DESIGN.md §5・§8)。

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    // FastAPI のエラー形式 {detail: "..."} を整形。JSON でなければステータス文言
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body && body.detail) detail = body.detail;
    } catch {
      // JSON でないレスポンスはそのまま
    }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

// POST /api/scores (multipart) → {score_id, summary, recommended_tpq}
export function uploadScore(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/api/scores", { method: "POST", body: form });
}

// GET /api/scores/{id} → {score_id, summary, recommended_tpq}
export function getScore(scoreId) {
  return request(`/api/scores/${encodeURIComponent(scoreId)}`);
}

// POST /api/scores/{id}/blueprint (body = ConversionSettings) → Blueprint
export function createBlueprint(scoreId, settings) {
  return request(`/api/scores/${encodeURIComponent(scoreId)}/blueprint`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

// GET /api/scores/{id}/blueprint → Blueprint
export function getBlueprint(scoreId) {
  return request(`/api/scores/${encodeURIComponent(scoreId)}/blueprint`);
}
