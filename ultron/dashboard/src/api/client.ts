const API = '';

function getToken(): string {
  try { return localStorage.getItem('ultron-auth-token') || ''; } catch { return ''; }
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (t) h['Authorization'] = 'Bearer ' + t;
  return h;
}

async function handleResponse(r: Response) {
  if (r.status === 401) {
    localStorage.removeItem('ultron-auth-token');
    localStorage.removeItem('ultron-auth-user');
    window.dispatchEvent(new Event('ultron-logout'));
    throw new Error('Unauthorized');
  }
  return r.json();
}

export async function api(path: string) {
  const r = await fetch(API + path, { headers: authHeaders() });
  return handleResponse(r);
}

export async function apiPost(path: string, body: unknown) {
  const r = await fetch(API + path, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  return handleResponse(r);
}

export async function apiDelete(path: string, body: unknown) {
  const r = await fetch(API + path, {
    method: 'DELETE',
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  return handleResponse(r);
}

export async function login(username: string, password: string) {
  const r = await fetch(API + '/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  return r.json();
}

export async function register(username: string, password: string) {
  const r = await fetch(API + '/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  return r.json();
}

export async function checkAuth() {
  const token = getToken();
  if (!token) return null;
  const r = await fetch(API + '/auth/me', { headers: { 'Authorization': 'Bearer ' + token } });
  if (!r.ok) return null;
  const j = await r.json();
  if (j.success) return { username: j.data.username };
  return null;
}
