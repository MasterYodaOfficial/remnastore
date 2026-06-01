import { describe, expect, it, vi } from 'vitest';

import {
  hasPendingSupabaseOAuthCallback,
  resolvePendingSupabaseSession,
} from './browser-auth';

describe('hasPendingSupabaseOAuthCallback', () => {
  it('detects a Supabase PKCE callback code in the URL', () => {
    expect(hasPendingSupabaseOAuthCallback('https://lk.myquickcloud.ru/?code=oauth-code')).toBe(true);
  });

  it('ignores URLs without a callback code', () => {
    expect(hasPendingSupabaseOAuthCallback('https://lk.myquickcloud.ru/login')).toBe(false);
  });
});

describe('resolvePendingSupabaseSession', () => {
  it('returns the current session immediately when it already exists', async () => {
    const currentSession = { access_token: 'live-token' };
    const getSession = vi.fn(async () => null);

    await expect(
      resolvePendingSupabaseSession({
        currentSession,
        getSession,
        locationHref: 'https://lk.myquickcloud.ru/',
      })
    ).resolves.toBe(currentSession);

    expect(getSession).not.toHaveBeenCalled();
  });

  it('does not poll when there is no OAuth callback in the URL', async () => {
    const getSession = vi.fn(async () => ({ access_token: 'new-token' }));

    await expect(
      resolvePendingSupabaseSession({
        currentSession: null,
        getSession,
        locationHref: 'https://lk.myquickcloud.ru/',
      })
    ).resolves.toBeNull();

    expect(getSession).not.toHaveBeenCalled();
  });

  it('waits for the exchanged OAuth session before giving up', async () => {
    const resolvedSession = { access_token: 'oauth-token' };
    const getSession = vi
      .fn<() => Promise<{ access_token: string } | null>>()
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(resolvedSession);
    const sleep = vi.fn(async () => undefined);

    await expect(
      resolvePendingSupabaseSession({
        currentSession: null,
        getSession,
        locationHref: 'https://lk.myquickcloud.ru/?code=oauth-code',
        waitMs: 200,
        pollMs: 100,
        sleep,
      })
    ).resolves.toBe(resolvedSession);

    expect(sleep).toHaveBeenCalledTimes(2);
    expect(getSession).toHaveBeenCalledTimes(2);
  });

  it('returns null after the wait window expires without a session', async () => {
    const getSession = vi.fn(async () => null);
    const sleep = vi.fn(async () => undefined);

    await expect(
      resolvePendingSupabaseSession({
        currentSession: null,
        getSession,
        locationHref: 'https://lk.myquickcloud.ru/?code=oauth-code',
        waitMs: 250,
        pollMs: 100,
        sleep,
      })
    ).resolves.toBeNull();

    expect(sleep).toHaveBeenCalledTimes(3);
    expect(getSession).toHaveBeenCalledTimes(3);
  });
});
