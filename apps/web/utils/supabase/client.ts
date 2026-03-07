import { createClient } from '@supabase/supabase-js';
import { projectId, publicAnonKey } from './info';

const defaultSupabaseUrl = `https://${projectId}.supabase.co`;

export const supabaseUrl = (import.meta.env.VITE_SUPABASE_URL || defaultSupabaseUrl).replace(
  /\/+$/,
  ''
);
export const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || publicAnonKey;

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
