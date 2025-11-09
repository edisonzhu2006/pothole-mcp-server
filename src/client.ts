import { createClient } from '@supabase/supabase-js';

/**
 * Creates a new Supabase client instance.
 * @param {string} supabaseUrl The URL of the Supabase project.
 * @param {string} supabaseKey The API key for the Supabase project.
 * @returns {SupabaseClient} A new Supabase client instance.
 */
export function createSupabaseClient(supabaseUrl: string, supabaseKey: string) {
    return createClient(supabaseUrl, supabaseKey);
}