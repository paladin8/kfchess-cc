/**
 * Analytics wrapper module
 *
 * Central wrapper around Amplitude. All other files import from here,
 * never from @amplitude/analytics-browser directly.
 * When no API key is set (dev/test), all calls are safe no-ops.
 */

import * as amplitude from '@amplitude/analytics-browser';
import { sessionReplayPlugin } from '@amplitude/plugin-session-replay-browser';

let initialized = false;

export function init(apiKey: string | undefined): void {
  if (!apiKey) return;

  const sessionReplay = sessionReplayPlugin();
  amplitude.add(sessionReplay);

  amplitude.init(apiKey, {
    minIdLength: 1,
    autocapture: { elementInteractions: true },
  });
  initialized = true;
}

export function identify(
  userId: string,
  properties: Record<string, string | null | undefined>,
): void {
  if (!initialized) return;

  amplitude.setUserId(userId);
  const identifyEvent = new amplitude.Identify();
  for (const [key, value] of Object.entries(properties)) {
    if (value != null) {
      identifyEvent.set(key, value);
    }
  }
  amplitude.identify(identifyEvent);
}

export function track(
  eventName: string,
  properties?: Record<string, unknown>,
): void {
  if (!initialized) return;
  amplitude.track(eventName, properties);
}

export function reset(): void {
  if (!initialized) return;
  amplitude.reset();
}
