const SP_TZ = 'America/Sao_Paulo';
const MIN_PER_DAY = 1440;

function mod(value: number, base: number): number {
  return ((value % base) + base) % base;
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

export function parseTimeToMinutes(time: string): number {
  const match = /^(\d{1,2}):(\d{2})$/.exec(time);
  if (!match) return 0;
  const h = Number(match[1]);
  const m = Number(match[2]);
  if (!Number.isFinite(h) || !Number.isFinite(m)) return 0;
  return mod(h * 60 + m, MIN_PER_DAY);
}

export function getSaoPauloMinuteOfDay(nowMs: number): number {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: SP_TZ,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    hourCycle: 'h23',
  }).formatToParts(new Date(nowMs));

  const hour = Number(parts.find((p) => p.type === 'hour')?.value ?? 0);
  const minute = Number(parts.find((p) => p.type === 'minute')?.value ?? 0);
  const second = Number(parts.find((p) => p.type === 'second')?.value ?? 0);

  return hour * 60 + minute + second / 60;
}

function relDayLabel(dayOffset: number): string {
  if (dayOffset === -1) return 'Ontem';
  if (dayOffset === 0) return 'Hoje';
  if (dayOffset === 1) return 'Amanhã';
  return dayOffset < 0 ? 'Ontem' : 'Amanhã';
}

function fmtAbsMin(absMin: number): string {
  const totalMins = mod(absMin, MIN_PER_DAY);
  const h = Math.floor(totalMins / 60);
  const m = totalMins % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

function absToRangeText(startAbs: number, endAbs: number): string {
  const startDay = Math.floor(startAbs / MIN_PER_DAY);
  const endDay = Math.floor(endAbs / MIN_PER_DAY);
  const startTime = fmtAbsMin(startAbs);
  const endTime = fmtAbsMin(endAbs);
  if (startDay === endDay) {
    return `${relDayLabel(startDay)} ${startTime} → ${endTime}`;
  }
  return `${relDayLabel(startDay)} ${startTime} → ${relDayLabel(endDay)} ${endTime}`;
}

export interface ShiftPeriodState {
  label: string;
  rangeText: string;
  isCurrent: boolean;
  fill: number;
}

export interface ShiftDisplayState {
  period1: ShiftPeriodState;
  period2: ShiftPeriodState;
}

/**
 * Returns display state for both shift periods.
 *
 * live=true  (Janela / ao vivo): rangeText usa Ontem/Hoje/Amanhã + isCurrent pelo relógio SP.
 * live=false (Período histórico): rótulos estáticos, isCurrent=false, fill=0.
 *
 * Barra (fill): turno ativo = progresso de tempo [0,1]; turno anterior = 1 (completo).
 */
export function getShiftDisplayState(opts: {
  now: number;
  shiftStart: string;
  shiftEnd: string;
  live: boolean;
}): ShiftDisplayState {
  const { now, shiftStart, shiftEnd, live } = opts;

  if (!live) {
    return {
      period1: { label: '1º TURNO', rangeText: `${shiftStart} → ${shiftEnd}`, isCurrent: false, fill: 0 },
      period2: { label: '2º TURNO', rangeText: `${shiftEnd} → ${shiftStart}`, isCurrent: false, fill: 0 },
    };
  }

  const startMin = parseTimeToMinutes(shiftStart);
  const endMin = parseTimeToMinutes(shiftEnd);

  if (startMin === endMin) {
    return {
      period1: { label: '1º TURNO', rangeText: `Hoje ${shiftStart} → ${shiftEnd}`, isCurrent: true, fill: 0 },
      period2: { label: '2º TURNO', rangeText: '—', isCurrent: false, fill: 0 },
    };
  }

  const dur1 = mod(endMin - startMin, MIN_PER_DAY) || MIN_PER_DAY;
  const dur2 = MIN_PER_DAY - dur1;
  const nowMin = getSaoPauloMinuteOfDay(now);

  // Find which segment contains nowMin by testing P1 and P2 instances for days -1, 0, 1.
  // P1[d]: [d*1440+startMin, d*1440+startMin+dur1)
  // P2[d]: [d*1440+endMin,   d*1440+endMin+dur2)
  let activePeriod: 1 | 2 = 1;
  let activeStart = 0;
  let activeDur = dur1;

  search: for (const period of [1, 2] as const) {
    const segOrigin = period === 1 ? startMin : endMin;
    const segDur = period === 1 ? dur1 : dur2;
    for (const d of [-1, 0, 1]) {
      const s = d * MIN_PER_DAY + segOrigin;
      if (s <= nowMin && nowMin < s + segDur) {
        activePeriod = period;
        activeStart = s;
        activeDur = segDur;
        break search;
      }
    }
  }

  const fillActive = clamp01((nowMin - activeStart) / activeDur);

  // Non-active = segment immediately before the active one.
  const otherDur = activePeriod === 1 ? dur2 : dur1;
  const otherEnd = activeStart;
  const otherStart = otherEnd - otherDur;

  const p1Start = activePeriod === 1 ? activeStart : otherStart;
  const p1End = activePeriod === 1 ? activeStart + dur1 : otherEnd;
  const p2Start = activePeriod === 2 ? activeStart : otherStart;
  const p2End = activePeriod === 2 ? activeStart + dur2 : otherEnd;
  const p1Fill = activePeriod === 1 ? fillActive : 1;
  const p2Fill = activePeriod === 2 ? fillActive : 1;

  return {
    period1: {
      label: '1º TURNO',
      rangeText: absToRangeText(p1Start, p1End),
      isCurrent: activePeriod === 1,
      fill: p1Fill,
    },
    period2: {
      label: '2º TURNO',
      rangeText: absToRangeText(p2Start, p2End),
      isCurrent: activePeriod === 2,
      fill: p2Fill,
    },
  };
}
