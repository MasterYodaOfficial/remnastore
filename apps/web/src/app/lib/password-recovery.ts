export const PASSWORD_RECOVERY_STORAGE_KEY = 'remnastore.password_recovery_active';

export type RecoverySession = { access_token: string; user: { id: string } };
type RecoveryBinding = { userId: string; sessionId: string };

let currentRecoveryToken: string | null = null;

function recoveryStorage(): Storage | null {
  try { return typeof window === 'undefined' ? null : window.sessionStorage; }
  catch { return null; }
}

function readBinding(): RecoveryBinding | null {
  try {
    const binding = JSON.parse(recoveryStorage()?.getItem(PASSWORD_RECOVERY_STORAGE_KEY) ?? 'null');
    return binding && typeof binding.userId === 'string' && typeof binding.sessionId === 'string'
      ? binding : null;
  } catch { return null; }
}

function sessionId(session: RecoverySession): string | null {
  try {
    const payload = session.access_token.split('.')[1];
    const value = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
    return typeof value.session_id === 'string' && value.session_id ? value.session_id : null;
  } catch { return null; }
}

export function rememberPasswordRecovery(session: RecoverySession): void {
  currentRecoveryToken = session.access_token;
  const id = sessionId(session);
  if (id) {
    try {
      recoveryStorage()?.setItem(PASSWORD_RECOVERY_STORAGE_KEY, JSON.stringify({ userId: session.user.id, sessionId: id }));
    } catch { /* In-memory proof still allows this page to finish. */ }
  } else {
    try { recoveryStorage()?.removeItem(PASSWORD_RECOVERY_STORAGE_KEY); }
    catch { /* In-memory proof is sufficient for the current page. */ }
  }
}

export function forgetPasswordRecovery(): void {
  currentRecoveryToken = null;
  try { recoveryStorage()?.removeItem(PASSWORD_RECOVERY_STORAGE_KEY); }
  catch { /* Storage can be disabled. */ }
}

export function isPasswordRecoverySession(session: RecoverySession | null): boolean {
  if (!session?.access_token) return false;
  if (currentRecoveryToken === session.access_token) return true;
  const binding = readBinding();
  // This is a UI binding, not JWT verification. Supabase validates the session.
  return Boolean(binding && binding.userId === session.user.id && binding.sessionId === sessionId(session));
}

export function hasPasswordRecoveryIntent(href?: string): boolean {
  try {
    const url = new URL(href ?? window.location.href);
    const hash = new URLSearchParams(url.hash.slice(1));
    return url.searchParams.get('auth_action') === 'reset-password'
      || url.searchParams.get('type') === 'recovery' || hash.get('type') === 'recovery'
      || Boolean(recoveryStorage()?.getItem(PASSWORD_RECOVERY_STORAGE_KEY));
  } catch { return false; }
}

export function readRecoveryStartup(href: string, storedVerifier: string | null) {
  const url = new URL(href);
  const hash = new URLSearchParams(url.hash.slice(1));
  let verifier: unknown = storedVerifier;
  try { verifier = JSON.parse(storedVerifier ?? 'null'); } catch { /* Accept plain storage too. */ }
  const pkceRecovery = url.searchParams.has('code') && typeof verifier === 'string'
    && verifier.endsWith('/PASSWORD_RECOVERY');
  return {
    intent: hasPasswordRecoveryIntent(href) || pkceRecovery,
    pkceRecovery,
    callbackError: [url.searchParams, hash].some(params => params.has('error') || params.has('error_code')),
  };
}
