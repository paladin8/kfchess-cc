/**
 * Application Configuration
 *
 * Centralized configuration for the client application.
 */

/**
 * Base URL for static assets (images, audio, video).
 * Points to the public S3 bucket.
 */
export const STATIC_URL = 'https://com-kfchess-public.s3.amazonaws.com/static';

/**
 * Helper to get a static asset URL.
 */
export function staticUrl(path: string): string {
  // Remove leading slash if present
  const cleanPath = path.startsWith('/') ? path.slice(1) : path;
  return `${STATIC_URL}/${cleanPath}`;
}
