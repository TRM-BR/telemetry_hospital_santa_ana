export const SIGNAL_LOST_AFTER_MS = 3 * 60 * 60 * 1000;

export function isSignalLost(lastSeenUtc: string | null, nowMs = Date.now()): boolean {
  if (!lastSeenUtc) return true;
  return nowMs - Date.parse(lastSeenUtc) > SIGNAL_LOST_AFTER_MS;
}
