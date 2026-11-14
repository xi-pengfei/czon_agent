import { fetch } from 'expo/fetch';
import * as SecureStore from 'expo-secure-store';
import { apiUrl, serverOrigin } from './protocol';
import type { Identity } from './types';
export type Credentials = { origin: string; token: string; identity: Identity };
const KEY = 'czon.mobile.session.v1';
export class ApiError extends Error { constructor(message: string, public status: number) { super(message); } }
export class Client {
  constructor(public credentials: Credentials, public expired: () => void) {}
  async response(path: string, init: RequestInit = {}) {
    const headers = new Headers(init.headers);
    headers.set('Authorization', `Bearer ${this.credentials.token}`);
    headers.set('X-CSRF-Token', this.credentials.identity.csrf_token);
    if (typeof init.body === 'string') headers.set('Content-Type', 'application/json');
    const response = await fetch(apiUrl(this.credentials.origin, path), {
      ...init, headers, credentials: 'omit', redirect: 'error',
      signal: init.signal ?? AbortSignal.timeout(init.method === 'POST' ? 120_000 : 20_000),
    });
    if (!response.ok) {
      if (response.status === 401) this.expired();
      const data = await response.json().catch(() => ({}));
      throw new ApiError(typeof data.detail === 'string' ? data.detail : `请求失败 (${response.status})`, response.status);
    }
    return response;
  }
  async get<T>(path: string, signal?: AbortSignal): Promise<T> { return (await this.response(path, {signal})).json(); }
  async post<T>(path: string, body: unknown): Promise<T> { return (await this.response(path, {method: 'POST', body: JSON.stringify(body)})).json(); }
}
export async function login(address: string, username: string, password: string): Promise<Credentials> {
  const origin = serverOrigin(address, __DEV__);
  const response = await fetch(apiUrl(origin, '/api/auth/mobile/login'), {
    method: 'POST', credentials: 'omit', redirect: 'error', signal: AbortSignal.timeout(20_000),
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username, password}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `登录失败 (${response.status})`);
  if (!data.session_token) throw new Error('请先更新并重启后端服务，再使用移动端登录');
  const {session_token: token, ...identity} = data;
  return {origin, token, identity};
}
export async function saveCredentials(value: Credentials | null) {
  if (value) await SecureStore.setItemAsync(KEY, JSON.stringify(value), {keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY});
  else await SecureStore.deleteItemAsync(KEY);
}
export async function restoreCredentials(): Promise<Credentials | null> {
  const value = await SecureStore.getItemAsync(KEY);
  if (!value) return null;
  try {
    const auth = JSON.parse(value);
    serverOrigin(auth.origin, __DEV__);
    if (!auth.token || !auth.identity?.csrf_token) throw new Error('Invalid session');
    return auth;
  } catch { await saveCredentials(null); return null; }
}
