const REPORTS_API_BASE = '/api/reports';
const AUTH_API_BASE = '/api/auth';
const AUTH_TOKEN_KEY = 'medsenseai_auth_token';

export function getAuthToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token) {
  if (token) {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
  }
}

export function clearAuthToken() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

function buildHeaders(existingHeaders = {}, useJson = false) {
  const headers = { ...existingHeaders };
  const token = getAuthToken();

  if (useJson) {
    headers['Content-Type'] = 'application/json';
  }

  if (token) {
    headers.Authorization = `Token ${token}`;
  }

  return headers;
}

async function parseResponse(response) {
  const text = await response.text();
  let data = null;

  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }

  if (!response.ok) {
    const message =
      data?.error ||
      data?.detail ||
      data?.message ||
      `Request failed with status ${response.status}`;

    const error = new Error(message);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

async function apiFetch(url, options = {}, { auth = true, json = false } = {}) {
  const headers = auth
    ? buildHeaders(options.headers, json)
    : json
      ? { ...(options.headers || {}), 'Content-Type': 'application/json' }
      : options.headers;

  const response = await fetch(url, {
    ...options,
    headers,
  });

  return parseResponse(response);
}

export async function registerUser(payload) {
  const data = await apiFetch(
    `${AUTH_API_BASE}/register/`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    { auth: false, json: true }
  );

  setAuthToken(data.token);
  return data;
}

export async function loginUser(payload) {
  const data = await apiFetch(
    `${AUTH_API_BASE}/login/`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    { auth: false, json: true }
  );

  setAuthToken(data.token);
  return data;
}

export async function getMe() {
  return apiFetch(`${AUTH_API_BASE}/me/`);
}

export async function logoutUser() {
  try {
    return await apiFetch(`${AUTH_API_BASE}/logout/`, { method: 'POST' });
  } finally {
    clearAuthToken();
  }
}

export async function seedKnowledgeBase() {
  return apiFetch(`${REPORTS_API_BASE}/knowledge/seed/`, {
    method: 'POST',
  });
}

export async function listKnowledgeDocuments() {
  return apiFetch(`${REPORTS_API_BASE}/knowledge/`);
}

export async function uploadReport(file) {
  const formData = new FormData();
  formData.append('file', file);

  return apiFetch(`${REPORTS_API_BASE}/upload/`, {
    method: 'POST',
    body: formData,
  });
}

export async function extractText(reportId) {
  return apiFetch(`${REPORTS_API_BASE}/${reportId}/extract-text/`, {
    method: 'POST',
  });
}

export async function parseReport(reportId) {
  return apiFetch(`${REPORTS_API_BASE}/${reportId}/parse/`, {
    method: 'POST',
  });
}

export async function getReport(reportId) {
  return apiFetch(`${REPORTS_API_BASE}/${reportId}/`);
}

export async function listReports() {
  return apiFetch(`${REPORTS_API_BASE}/`);
}

export async function getPatientView(reportId, language = 'en') {
  return apiFetch(
    `${REPORTS_API_BASE}/${reportId}/patient-view/?language=${language}`
  );
}

export async function getReportSafetyAudits(reportId) {
  return apiFetch(`${REPORTS_API_BASE}/${reportId}/safety-audits/`);
}