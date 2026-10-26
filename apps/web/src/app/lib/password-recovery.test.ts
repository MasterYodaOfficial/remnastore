// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';

let recovery: typeof import('./password-recovery');
const session = (id: string, user = 'user-1', nonce = 'first') => ({
  access_token: `${btoa('{}')}.${btoa(JSON.stringify({ session_id: id, nonce }))}.signature`,
  user: { id: user },
});

beforeEach(async () => {
  window.sessionStorage.clear();
  vi.resetModules();
  recovery = await import('./password-recovery');
});

describe('password recovery intent and session binding', () => {
  it('captures the PKCE recovery type before the SDK removes its verifier', () => {
    const startup = recovery.readRecoveryStartup('https://app.test/?code=opaque', JSON.stringify('verifier/PASSWORD_RECOVERY'));
    expect(startup).toEqual({ intent: true, pkceRecovery: true, callbackError: false });
    expect(recovery.isPasswordRecoverySession(session('ordinary'))).toBe(false);
  });

  it('does not treat URL intent, an OAuth code, or a legacy marker as session proof', () => {
    expect(recovery.hasPasswordRecoveryIntent('https://app.test/?auth_action=reset-password')).toBe(true);
    expect(recovery.readRecoveryStartup('https://app.test/?code=oauth', JSON.stringify('ordinary-verifier')).intent).toBe(false);
    window.sessionStorage.setItem(recovery.PASSWORD_RECOVERY_STORAGE_KEY, '1');
    expect(recovery.hasPasswordRecoveryIntent('https://app.test/')).toBe(true);
    expect(recovery.isPasswordRecoverySession(session('ordinary'))).toBe(false);
  });

  it('keeps recovery over reload and token refresh, but not over a different login', async () => {
    recovery.rememberPasswordRecovery(session('recovery-session'));
    const stored = window.sessionStorage.getItem(recovery.PASSWORD_RECOVERY_STORAGE_KEY);
    expect(stored).not.toContain('signature');
    vi.resetModules();
    const reloaded = await import('./password-recovery');
    expect(reloaded.isPasswordRecoverySession(session('recovery-session', 'user-1', 'refreshed'))).toBe(true);
    expect(reloaded.isPasswordRecoverySession(session('another-session'))).toBe(false);
    expect(reloaded.isPasswordRecoverySession(session('recovery-session', 'another-user'))).toBe(false);
    reloaded.forgetPasswordRecovery();
    expect(reloaded.isPasswordRecoverySession(session('recovery-session'))).toBe(false);
    expect(window.sessionStorage.getItem(reloaded.PASSWORD_RECOVERY_STORAGE_KEY)).toBeNull();
  });

  it('recognizes failure even if a code and verifier exist', () => {
    expect(recovery.readRecoveryStartup('https://app.test/?auth_action=reset-password&code=expired&error_code=otp_expired', JSON.stringify('verifier/PASSWORD_RECOVERY')).callbackError).toBe(true);
  });
});
