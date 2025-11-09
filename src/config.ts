import dotenv from 'dotenv';

// Load environment variables from .env file
dotenv.config();

/**
 * Defines the structure of the application configuration
 * @interface Config
 */
export interface Config {
    supabaseUrl: string;
    supabaseKey: string;
    port: number;
    isProduction: boolean;
}

/**
 * Loads and validates the application configuration from environment variables
 * @returns {Config} The application configuration
 * @throws {Error} If any required environment variables are missing
 */
export function loadConfig(): Config {
    const supabaseUrl = process.env.SUPABASE_URL;
    const supabaseKey = process.env.SUPABASE_KEY;
    const port = process.env.PORT ? parseInt(process.env.PORT, 10) : 8080;
    const isProduction = process.env.NODE_ENV === 'production';

    if (!supabaseUrl) {
        throw new Error('SUPABASE_URL is not defined in environment variables');
    }

    if (!supabaseKey) {
        throw new Error('SUPABASE_KEY is not defined in environment variables');
    }

    return { supabaseUrl, supabaseKey, port, isProduction };
}
