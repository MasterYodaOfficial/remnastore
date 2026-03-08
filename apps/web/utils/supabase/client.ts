import { createClient } from '@supabase/supabase-js';
import { projectId, publicAnonKey } from './info';

const defaultSupabaseUrl = `https://${projectId}.supabase.co`;

export const supabaseUrl = (import.meta.env.VITE_SUPABASE_URL || defaultSupabaseUrl).replace(
  /\/+$/,
  ''
);
export const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || publicAnonKey;

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
