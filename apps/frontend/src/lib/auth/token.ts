/**
 * Minimal in-memory token store used to attach Authorization headers to API
 * requests.  Call `setToken` after a successful Auth0 login; `clearToken` on
 * logout.  When no token is set, protected endpoints are reached without an
 * Authorization header — the backend gracefully accepts this when
 * `AUTH_ENABLED=False` (local dev / CI).
 */

let _token: string | null = null;

export function setToken(token: string): void {
	_token = token;
}

export function clearToken(): void {
	_token = null;
}

export function getToken(): string | null {
	return _token;
}

export function authHeaders(): Record<string, string> {
	return _token ? { Authorization: `Bearer ${_token}` } : {};
}
