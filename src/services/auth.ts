import { api, clearToken, setToken } from './api';
import type { LoginResponse } from '../types/auth';

export { getToken, clearToken } from './api';

const USERNAME_KEY = 'hsa.auth.username';

export function isAuthenticated(): boolean {
  return Boolean(localStorage.getItem('hsa.auth.token'));
}

export function getUsername(): string {
  return localStorage.getItem(USERNAME_KEY) ?? '';
}

export async function login(identifier: string, password: string): Promise<void> {
  const data = await api<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ identifier, password }),
  });
  setToken(data.access_token);
  localStorage.setItem(USERNAME_KEY, identifier);
}

export async function register(
  username: string,
  email: string,
  password: string,
): Promise<void> {
  await api('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, email, password }),
  });
}

export async function registerConfirm(email: string, code: string): Promise<void> {
  await api('/auth/register/confirm', {
    method: 'POST',
    body: JSON.stringify({ email, code }),
  });
}

export async function forgotPassword(identifier: string): Promise<void> {
  await api('/auth/password/forgot', {
    method: 'POST',
    body: JSON.stringify({ identifier }),
  });
}

export async function verifyResetCode(identifier: string, code: string): Promise<void> {
  await api('/auth/password/verify-code', {
    method: 'POST',
    body: JSON.stringify({ identifier, code }),
  });
}

export async function resetPassword(
  identifier: string,
  code: string,
  newPassword: string,
): Promise<void> {
  await api('/auth/password/reset', {
    method: 'POST',
    body: JSON.stringify({ identifier, code, new_password: newPassword }),
  });
}

export function logout(queryClient?: { clear(): void }): void {
  clearToken();
  localStorage.removeItem(USERNAME_KEY);
  queryClient?.clear();
}
