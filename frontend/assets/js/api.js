const API_BASE =
  window.VIRALPICK_API_BASE ||
  (window.location.protocol.startsWith("http") ? `${window.location.origin}/api` : "http://127.0.0.1:5000/api");
const TOKEN_KEY = "viralpick_access_token";

function toQuery(params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, value);
    }
  });
  const text = query.toString();
  return text ? `?${text}` : "";
}

async function request(path, options = {}) {
  const token = window.localStorage.getItem(TOKEN_KEY);
  const isFormData = options.body instanceof FormData;
  const headers = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };
  const response = await fetch(`${API_BASE}${path}`, {
    headers,
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.success === false) {
    throw new Error(payload.error || `请求失败：${path}`);
  }
  return payload.data;
}

async function requestBlob(path, options = {}) {
  const token = window.localStorage.getItem(TOKEN_KEY);
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || `请求失败：${path}`);
  }
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get("Content-Disposition")) || "ViralPick-AI-report",
  };
}

function filenameFromDisposition(value) {
  if (!value) return "";
  const utf8Match = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) return decodeURIComponent(utf8Match[1]);
  const asciiMatch = value.match(/filename="?([^";]+)"?/i);
  return asciiMatch ? asciiMatch[1] : "";
}

export const api = {
  tokenKey: TOKEN_KEY,
  health: () => request("/health"),
  llmStatus: () => request("/llm/status"),
  knowledgeStatus: () => request("/knowledge/status"),
  knowledgeSearch: (params = {}) => request(`/knowledge/search${toQuery(params)}`),
  rebuildKnowledge: () => request("/knowledge/rebuild", { method: "POST" }),
  assistantChat: (payload = {}) =>
    request("/assistant/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  login: (payload) =>
    request("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  register: (payload) =>
    request("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  me: () => request("/auth/me"),
  permissions: () => request("/auth/permissions"),
  logout: () => request("/auth/logout", { method: "POST" }),
  brandSettings: () => request("/brand/settings"),
  updateBrandSettings: (payload) =>
    request("/brand/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  teamMembers: () => request("/team/members"),
  teamInvitations: (params = {}) => request(`/team/invitations${toQuery(params)}`),
  createTeamInvitation: (payload) =>
    request("/team/invitations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  revokeTeamInvitation: (invitationId) => request(`/team/invitations/${encodeURIComponent(invitationId)}`, { method: "DELETE" }),
  invitation: (inviteToken) => request(`/team/invitations/${encodeURIComponent(inviteToken)}`),
  acceptInvitation: (inviteToken, payload) =>
    request(`/team/invitations/${encodeURIComponent(inviteToken)}/accept`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  createTeamMember: (payload) =>
    request("/team/members", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateTeamMember: (userId, payload) =>
    request(`/team/members/${encodeURIComponent(userId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  auditLogs: (params = {}) => request(`/audit/logs${toQuery(params)}`),
  opsStatus: () => request("/ops/status"),
  opsMonitoring: () => request("/ops/monitoring"),
  opsAlertStatus: () => request("/ops/alerts/status"),
  dispatchOpsAlerts: () => request("/ops/alerts/dispatch", { method: "POST" }),
  opsAutomationRuns: (params = {}) => request(`/ops/automation/runs${toQuery(params)}`),
  runOpsAutomationOnce: () => request("/ops/automation/run-once", { method: "POST" }),
  opsBackups: () => request("/ops/backups"),
  createBackup: () => request("/ops/backups", { method: "POST" }),
  verifyBackup: (filename) => request(`/ops/backups/${encodeURIComponent(filename)}/verify`),
  imports: (params = {}) => request(`/imports${toQuery(params)}`),
  importSchema: () => request("/imports/schema"),
  importPreview: (formData) =>
    request("/imports/preview", {
      method: "POST",
      body: formData,
    }),
  importCommit: (payload = {}) =>
    request("/imports/commit", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  importTemplate: (datasetType) => requestBlob(`/imports/templates/${encodeURIComponent(datasetType)}`),
  importErrors: (jobId) => requestBlob(`/imports/${encodeURIComponent(jobId)}/errors`),
  uploadImport: (formData) =>
    request("/imports", {
      method: "POST",
      body: formData,
    }),
  overview: () => request("/overview"),
  executiveDashboard: () => request("/dashboard/executive"),
  marketingSummary: () => request("/marketing/summary"),
  inventorySummary: () => request("/inventory/summary"),
  platformConnections: () => request("/platforms/connections"),
  syncPlatform: (payload = {}) =>
    request("/platforms/sync", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  authorizePlatform: (payload = {}) =>
    request("/platforms/authorize", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  categories: () => request("/categories"),
  products: (params = {}) => request(`/products${toQuery(params)}`),
  product: (productId) => request(`/products/${encodeURIComponent(productId)}`),
  rankings: (params = {}) => request(`/products/rankings${toQuery(params)}`),
  hotProducts: (limit = 10) => request(`/hot-products?limit=${limit}`),
  hotScoring: (params = {}) => request(`/hot-products/scoring${toQuery(params)}`),
  scoringModels: (params = {}) => request(`/scoring/models${toQuery(params)}`),
  createScoringModel: (payload = {}) =>
    request("/scoring/models", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  salesAnalysis: () => request("/analysis/sales"),
  priceBands: () => request("/analysis/price-bands"),
  trend: (params = {}) => request(`/sales/trend${toQuery(params)}`),
  sentiment: (params = {}) => request(`/comments/sentiment${toQuery(params)}`),
  keywords: (params = {}) => request(`/comments/keywords${toQuery(params)}`),
  competitorSummary: (params = {}) => request(`/competitors/summary${toQuery(params)}`),
  createCompetitor: (payload = {}) =>
    request("/competitors", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  forecast: (params = {}) => request(`/forecast/sales${toQuery(params)}`),
  generateReport: (payload = {}) =>
    request("/reports/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  report: (reportId) => request(`/reports/${encodeURIComponent(reportId)}`),
  reportSchedules: (params = {}) => request(`/reports/schedules${toQuery(params)}`),
  reportDeliveryStatus: () => request("/reports/delivery/status"),
  reportDeliveryRetries: (params = {}) => request(`/reports/delivery/retries${toQuery(params)}`),
  runDueReportDeliveryRetries: () => request("/reports/delivery/retries/run-due", { method: "POST" }),
  reportScheduleDeliveries: (scheduleId, params = {}) =>
    request(`/reports/schedules/${encodeURIComponent(scheduleId)}/deliveries${toQuery(params)}`),
  retryReportDelivery: (deliveryId) => request(`/reports/deliveries/${encodeURIComponent(deliveryId)}/retry`, { method: "POST" }),
  createReportSchedule: (payload = {}) =>
    request("/reports/schedules", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateReportSchedule: (scheduleId, payload = {}) =>
    request(`/reports/schedules/${encodeURIComponent(scheduleId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  archiveReportSchedule: (scheduleId) => request(`/reports/schedules/${encodeURIComponent(scheduleId)}`, { method: "DELETE" }),
  runReportSchedule: (scheduleId) => request(`/reports/schedules/${encodeURIComponent(scheduleId)}/run`, { method: "POST" }),
  runDueReportSchedules: () => request("/reports/schedules/run-due", { method: "POST" }),
  createReportShare: (reportId, payload = {}) =>
    request(`/reports/${encodeURIComponent(reportId)}/shares`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  reportShares: (reportId) => request(`/reports/${encodeURIComponent(reportId)}/shares`),
  reportShareAccessLogs: (shareId, params = {}) =>
    request(`/reports/shares/${encodeURIComponent(shareId)}/access-logs${toQuery(params)}`),
  revokeReportShare: (shareId) => request(`/reports/shares/${encodeURIComponent(shareId)}`, { method: "DELETE" }),
  sharedReport: (shareToken) => request(`/reports/shared/${encodeURIComponent(shareToken)}`),
  exportReport: (reportId, format = "docx") =>
    requestBlob(`/reports/${encodeURIComponent(reportId)}/export${toQuery({ format })}`),
};
