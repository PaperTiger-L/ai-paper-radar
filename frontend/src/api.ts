/* API 封装：baseURL '/api'，自动携带 Bearer token，401 跳回登录页 */

const BASE_URL = '/api';
const TOKEN_KEY = 'paper_radar_token';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
}

export function redirectToLogin() {
  clearToken();
  // 登录页是站点根路径的独立静态 index.html
  window.location.href = '/';
}

export class ApiError extends Error {
  status: number;
  payload: unknown;
  constructor(status: number, message: string, payload?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

/** 从后端错误响应中提取可读 message */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return '请求失败，请稍后重试';
}

interface RequestOptions {
  body?: unknown;
  params?: Record<string, string | number | boolean | undefined | null>;
}

async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
  let url = `${BASE_URL}${path}`;
  if (opts.params) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(opts.params)) {
      if (v !== undefined && v !== null && v !== '') qs.append(k, String(v));
    }
    const s = qs.toString();
    if (s) url += `?${s}`;
  }
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch (e) {
    throw new ApiError(0, '无法连接后端服务，请检查网络或服务是否运行');
  }

  if (res.status === 401) {
    redirectToLogin();
    throw new ApiError(401, '登录已过期，请重新登录');
  }

  // 204 / 空响应
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    const msg =
      (data as { message?: string; detail?: string })?.message ??
      (data as { detail?: string })?.detail ??
      `请求失败（${res.status}）`;
    throw new ApiError(res.status, String(msg), data);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, params?: RequestOptions['params']) =>
    request<T>('GET', path, { params }),
  post: <T>(path: string, body?: unknown, params?: RequestOptions['params']) =>
    request<T>('POST', path, { body, params }),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, { body }),
  del: <T>(path: string, params?: RequestOptions['params']) =>
    request<T>('DELETE', path, { params }),
};
