import type { SeriesPoint } from '../types/telemetry';

export const SIGNAL_LOST_AFTER_MS = 3 * 60 * 60 * 1000;
export const SILENCE_GAP_MS = 60 * 60 * 1000;

export function isSignalLost(lastSeenUtc: string | null, nowMs = Date.now()): boolean {
  if (!lastSeenUtc) return true;
  return nowMs - Date.parse(lastSeenUtc) > SIGNAL_LOST_AFTER_MS;
}

export function fillSilenceWithZeros(
  points: SeriesPoint[],
  windowStartMs: number,
  nowMs: number,
  gapMs = SILENCE_GAP_MS,
): SeriesPoint[] {
  if (points.length === 0) {
    return [{ t: windowStartMs, v: 0 }, { t: nowMs, v: 0 }];
  }

  const sorted = [...points].sort((a, b) => a.t - b.t);
  const result: SeriesPoint[] = [];

  for (let i = 0; i < sorted.length; i++) {
    const p = sorted[i];
    if (i > 0) {
      const prev = sorted[i - 1];
      if (p.t - prev.t > gapMs) {
        result.push({ t: prev.t + 1, v: 0 });
        result.push({ t: p.t - 1, v: 0 });
      }
    }
    result.push(p);
  }

  const lastT = sorted[sorted.length - 1].t;
  if (nowMs - lastT > gapMs) {
    result.push({ t: lastT + 1, v: 0 });
    result.push({ t: nowMs, v: 0 });
  }

  return result;
}
