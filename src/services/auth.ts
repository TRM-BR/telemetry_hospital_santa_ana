// Autenticação simples baseada em localStorage.
// Credenciais aceitas: admin / admin

const TOKEN_KEY = 'hsa.auth.token';
const USERNAME_KEY = 'hsa.auth.username';

const VALID_USER = 'admin';
const VALID_PASS = 'admin';

export function login(username: string, password: string): boolean {
  if (username === VALID_USER && password === VALID_PASS) {
    localStorage.setItem(TOKEN_KEY, btoa(`${username}:${Date.now()}`));
    localStorage.setItem(USERNAME_KEY, username);
    return true;
  }
  return false;
}

export function isAuthenticated(): boolean {
  return Boolean(localStorage.getItem(TOKEN_KEY));
}

export function getUsername(): string {
  return localStorage.getItem(USERNAME_KEY) ?? '';
}

export function logout(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
}
