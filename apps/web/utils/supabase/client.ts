import { createClient } from '@supabase/supabase-js';

function requireEnv(name: string, value: string | undefined): string {
  const normalized = value?.trim();
  if (!normalized) {
    throw new Error(`Missing required frontend env: ${name}`);
  }
  return normalized;
}

export const supabaseUrl = requireEnv(
  'VITE_SUPABASE_URL',
  import.meta.env.VITE_SUPABASE_URL
).replace(/\/+$/, '');

export const supabaseAnonKey = requireEnv(
  'VITE_SUPABASE_ANON_KEY',
  import.meta.env.VITE_SUPABASE_ANON_KEY
);

const storage = typeof window !== 'undefined' ? window.localStorage : undefined;

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
    flowType: 'pkce',
    storage,
  },
});
