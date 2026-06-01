type SessionLike = {
  access_token?: string | null;
};

type ResolvePendingSupabaseSessionOptions<T extends SessionLike> = {
  currentSession: T | null | undefined;
  getSession: () => Promise<T | null | undefined>;
  locationHref: string;
  waitMs?: number;
  pollMs?: number;
  sleep?: (ms: number) => Promise<void>;
};

const DEFAULT_OAUTH_SESSION_WAIT_MS = 4000;
const DEFAULT_OAUTH_SESSION_POLL_MS = 100;

const delay = (ms: number) =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, ms);
  });

export const hasPendingSupabaseOAuthCallback = (locationHref: string): boolean => {
  try {
    return new URL(locationHref).searchParams.has('code');
  } catch {
    return false;
  }
};

export async function resolvePendingSupabaseSession<T extends SessionLike>({
  currentSession,
  getSession,
  locationHref,
  waitMs = DEFAULT_OAUTH_SESSION_WAIT_MS,
  pollMs = DEFAULT_OAUTH_SESSION_POLL_MS,
  sleep = delay,
}: ResolvePendingSupabaseSessionOptions<T>): Promise<T | null> {
  if (currentSession?.access_token) {
    return currentSession;
  }

  if (!hasPendingSupabaseOAuthCallback(locationHref)) {
    return currentSession ?? null;
  }

  const normalizedPollMs = Math.max(1, pollMs);
  let remainingMs = Math.max(0, waitMs);

  while (remainingMs > 0) {
    const stepMs = Math.min(normalizedPollMs, remainingMs);
    await sleep(stepMs);
    remainingMs -= stepMs;

    const nextSession = (await getSession()) ?? null;
    if (nextSession?.access_token) {
      return nextSession;
    }
  }

  return null;
}
