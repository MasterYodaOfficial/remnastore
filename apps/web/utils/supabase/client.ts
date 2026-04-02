import { createClient } from '@supabase/supabase-js';
import { supabaseAnonKey, supabaseUrl } from '../runtime-config'

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
