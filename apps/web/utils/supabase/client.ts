import { createClient } from '@supabase/supabase-js';
import { supabaseAnonKey, supabaseUrl } from '../runtime-config'
import {
  forgetPasswordRecovery, isPasswordRecoverySession, readRecoveryStartup,
  rememberPasswordRecovery,
} from '../../src/app/lib/password-recovery';

const storage = typeof window !== 'undefined' ? window.localStorage : undefined;
const storageKey = `sb-${new URL(supabaseUrl).hostname.split('.')[0]}-auth-token`;
let storedVerifier: string | null = null;
try { storedVerifier = storage?.getItem(`${storageKey}-code-verifier`) ?? null; }
catch { /* The SDK handles unavailable persistent storage. */ }
// Capture BEFORE the SDK exchanges the code and removes its verifier/URL code.
export const passwordRecoveryStartup = readRecoveryStartup(
  typeof window === 'undefined' ? 'https://localhost/' : window.location.href, storedVerifier
);

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
    flowType: 'pkce',
    storage,
    storageKey,
  },
});

let pendingRecoveryExchange = passwordRecoveryStartup.pkceRecovery && !passwordRecoveryStartup.callbackError;
supabase.auth.onAuthStateChange((event, session) => {
  if (session && (event === 'PASSWORD_RECOVERY' || (event === 'SIGNED_IN' && pendingRecoveryExchange))) {
    pendingRecoveryExchange = false;
    rememberPasswordRecovery(session);
  } else if (event === 'SIGNED_OUT') {
    pendingRecoveryExchange = false;
    forgetPasswordRecovery();
  }
});
void supabase.auth.initialize().then(({ error }) => {
  if (error) pendingRecoveryExchange = false;
});

export async function getPasswordRecoverySession() {
  const initialized = await supabase.auth.initialize();
  if (initialized.error || passwordRecoveryStartup.callbackError) return null;
  const { data: { session }, error } = await supabase.auth.getSession();
  if (error || !isPasswordRecoverySession(session) || !session) return null;
  const result = await supabase.auth.getUser(session.access_token);
  if (result.error) {
    if (result.error.status === 401 || ['session_not_found', 'session_expired', 'bad_jwt', 'refresh_token_not_found'].includes(result.error.code ?? '')) return null;
    throw result.error;
  }
  return result.data.user?.id === session.user.id && isPasswordRecoverySession(session) ? session : null;
}
