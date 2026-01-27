/**
 * Formatting utilities for display
 */

import { TIMING } from '../game/constants';

/**
 * Format a win reason for display.
 *
 * @param reason - The win reason from the server (e.g., "king_captured")
 * @returns Human-readable string (e.g., "King captured")
 */
export function formatWinReason(reason: string | null): string {
  if (!reason) return '';
  switch (reason) {
    case 'king_captured':
      return 'King captured';
    case 'checkmate':
      return 'Checkmate';
    case 'resignation':
      return 'Resignation';
    case 'timeout':
      return 'Timeout';
    case 'disconnect':
      return 'Disconnect';
    default:
      return reason.replace(/_/g, ' ');
  }
}

/**
 * Format ticks as a time string (MM:SS).
 *
 * @param ticks - Number of ticks
 * @returns Formatted time string
 */
export function formatDuration(ticks: number): string {
  const seconds = Math.floor(ticks / TIMING.TICKS_PER_SECOND);
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
}

/**
 * Format a date string for display.
 *
 * @param dateStr - ISO date string or null
 * @returns Formatted date and time string
 */
export function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'Unknown';
  const date = new Date(dateStr);
  return (
    date.toLocaleDateString() +
    ' ' +
    date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  );
}
