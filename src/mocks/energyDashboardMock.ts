import type {
  EnergyBar,
  EnergyDashboardResponse,
  EnergyLatest,
  EnergySeriesPoint,
} from '../types/energy';

const MIN_MS = 60 * 1000;
const HOUR_MS = 60 * MIN_MS;
const DAY_MS = 24 * HOUR_MS;
const TAU = Math.PI * 2;
const MOCK_EPOCH_MS = Date.UTC(2026, 0, 1, 0, 0, 0);

const SERIES_COLS = [
  'active_power_total_w',
  'reactive_power_total_var',
  'voltage_phase_a_v',
  'voltage_phase_b_v',
  'voltage_phase_c_v',
  'current_total_a',
  'power_factor_total',
  'active_energy_consumed_total_kwh',
  'active_energy_generated_total_kwh',
  'reactive_energy_generated_total_kvarh',
  'gsm_signal_rssi_dbm',
] as const;

type SeriesCol = (typeof SERIES_COLS)[number];

interface EnergyMockProfile {
  installationName: string;
  baseLoadW: number;
  minLoadW: number;
  maxLoadW: number;
  morningPeakW: number;
  afternoonPeakW: number;
  eveningPeakW: number;
  solarPeakW: number;
  reactiveBaseVar: number;
  weekendScale: number;
  consumedBaseKwh: number;
  generatedBaseKwh: number;
  reactiveBaseKvarh: number;
  averageDailyImportKwh: number;
  averageDailyExportKwh: number;
  averageDailyReactiveKvarh: number;
}

interface EnergyMockReading {
  t: number;
  deltaConsumedKwh: number;
  deltaGeneratedKwh: number;
  active_power_total_w: number;
  reactive_power_total_var: number;
  voltage_phase_a_v: number;
  voltage_phase_b_v: number;
  voltage_phase_c_v: number;
  current_total_a: number;
  power_factor_total: number;
  active_energy_consumed_total_kwh: number;
  active_energy_generated_total_kwh: number;
  reactive_energy_generated_total_kvarh: number;
  gsm_signal_rssi_dbm: number;
}

function round(value: number, decimals = 2): number {
  const factor = 10 ** decimals;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function hourOfDay(ts: number): number {
  const d = new Date(ts);
  return d.getHours() + d.getMinutes() / 60;
}

function dayOfYear(ts: number): number {
  const d = new Date(ts);
  const start = new Date(d.getFullYear(), 0, 0).getTime();
  return Math.floor((d.getTime() - start) / DAY_MS);
}

function cyclicBump(hour: number, center: number, width: number): number {
  const diff = Math.abs(hour - center);
  const wrapped = Math.min(diff, 24 - diff);
  return Math.exp(-Math.pow(wrapped / width, 2));
}

function profileForSlug(slug: string): EnergyMockProfile {
  const normalized = slug.toLowerCase().replace(/[-_]+/g, ' ');
  if (normalized.includes('hospital')) {
    return {
      installationName: 'Hospital Santa Ana',
      baseLoadW: 28_000,
      minLoadW: 18_000,
      maxLoadW: 62_000,
      morningPeakW: 18_000,
      afternoonPeakW: 10_000,
      eveningPeakW: 14_000,
      solarPeakW: 24_000,
      reactiveBaseVar: 3_400,
      weekendScale: 0.94,
      consumedBaseKwh: 154_800,
      generatedBaseKwh: 6_420,
      reactiveBaseKvarh: 38_600,
      averageDailyImportKwh: 820,
      averageDailyExportKwh: 7,
      averageDailyReactiveKvarh: 255,
    };
  }

  return {
    installationName: 'Escola Municipal',
    baseLoadW: 6_200,
    minLoadW: 2_700,
    maxLoadW: 36_000,
    morningPeakW: 15_800,
    afternoonPeakW: 10_600,
    eveningPeakW: 4_600,
    solarPeakW: 28_500,
    reactiveBaseVar: 820,
    weekendScale: 0.58,
    consumedBaseKwh: 12_480,
    generatedBaseKwh: 2_960,
    reactiveBaseKvarh: 4_320,
    averageDailyImportKwh: 185,
    averageDailyExportKwh: 34,
    averageDailyReactiveKvarh: 58,
  };
}

function stepMsForHours(hours: number): number {
  if (hours <= 1) return MIN_MS;
  if (hours <= 6) return 5 * MIN_MS;
  if (hours <= 24) return 15 * MIN_MS;
  if (hours <= 168) return HOUR_MS;
  return 4 * HOUR_MS;
}

function barStepMsForHours(hours: number): number {
  if (hours <= 1) return 5 * MIN_MS;
  if (hours <= 6) return 15 * MIN_MS;
  if (hours <= 24) return HOUR_MS;
  if (hours <= 168) return 6 * HOUR_MS;
  return DAY_MS;
}

function weekdayScale(ts: number, weekendScale: number): number {
  const day = new Date(ts).getDay();
  if (day === 0) return weekendScale * 0.9;
  if (day === 6) return weekendScale;
  return 1;
}

function loadWatts(ts: number, profile: EnergyMockProfile): number {
  const h = hourOfDay(ts);
  const minuteIndex = Math.floor(ts / MIN_MS);
  const dayScale = weekdayScale(ts, profile.weekendScale);

  const morning = profile.morningPeakW * cyclicBump(h, 8.2, 1.75);
  const afternoon = profile.afternoonPeakW * cyclicBump(h, 14.1, 2.45);
  const evening = profile.eveningPeakW * cyclicBump(h, 18.6, 2.1);
  const hvac = profile.baseLoadW * 0.08 * Math.sin(((h - 11) / 24) * TAU);
  const operationalNoise =
    Math.sin(minuteIndex * 0.043) * profile.baseLoadW * 0.025 +
    Math.cos(minuteIndex * 0.011) * profile.baseLoadW * 0.018;

  return clamp(
    (profile.baseLoadW + morning + afternoon + evening + hvac + operationalNoise) * dayScale,
    profile.minLoadW,
    profile.maxLoadW,
  );
}

function solarWatts(ts: number, profile: EnergyMockProfile): number {
  const h = hourOfDay(ts);
  if (h < 6.1 || h > 18.4) return 0;

  const daylight = Math.sin(((h - 6.1) / 12.3) * Math.PI);
  const cloudCover =
    0.84 +
    Math.sin(dayOfYear(ts) * 0.27) * 0.07 +
    Math.sin(Math.floor(ts / HOUR_MS) * 1.19) * 0.08 +
    Math.cos(Math.floor(ts / (3 * HOUR_MS)) * 0.71) * 0.05;

  return profile.solarPeakW * Math.pow(Math.max(0, daylight), 1.35) * clamp(cloudCover, 0.62, 1.04);
}

function powerFactor(ts: number, loadW: number, profile: EnergyMockProfile): number {
  const h = hourOfDay(ts);
  const loadRatio = clamp(loadW / profile.maxLoadW, 0, 1);
  const motorStartPenalty = 0.012 * cyclicBump(h, 7.6, 1.1) + 0.008 * cyclicBump(h, 17.8, 1.4);
  const drift = Math.sin(Math.floor(ts / (15 * MIN_MS)) * 0.41) * 0.004;
  return clamp(0.968 - loadRatio * 0.045 - motorStartPenalty + drift, 0.895, 0.988);
}

function voltageAvg(ts: number, loadW: number, profile: EnergyMockProfile): number {
  const h = hourOfDay(ts);
  const loadRatio = clamp(loadW / profile.maxLoadW, 0, 1);
  const minuteIndex = Math.floor(ts / MIN_MS);
  return (
    220.8 +
    Math.sin(((h - 3.5) / 24) * TAU) * 1.2 -
    loadRatio * 2.1 +
    Math.sin(minuteIndex * 0.029) * 0.35
  );
}

function buildReadings(profile: EnergyMockProfile, hours: number): EnergyMockReading[] {
  const stepMs = stepMsForHours(hours);
  const pointCount = Math.floor((hours * HOUR_MS) / stepMs) + 1;
  const now = Math.floor(Date.now() / MIN_MS) * MIN_MS;
  const start = now - (pointCount - 1) * stepMs;
  const daysSinceEpoch = (start - MOCK_EPOCH_MS) / DAY_MS;

  let consumedTotal = profile.consumedBaseKwh + daysSinceEpoch * profile.averageDailyImportKwh;
  let generatedTotal = profile.generatedBaseKwh + daysSinceEpoch * profile.averageDailyExportKwh;
  let reactiveTotal = profile.reactiveBaseKvarh + daysSinceEpoch * profile.averageDailyReactiveKvarh;

  const readings: EnergyMockReading[] = [];

  for (let i = 0; i < pointCount; i += 1) {
    const t = start + i * stepMs;
    const loadW = loadWatts(t, profile);
    const solarW = solarWatts(t, profile);
    const gridW = loadW - solarW;
    const pf = powerFactor(t, loadW, profile);
    const voltage = voltageAvg(t, loadW, profile);
    const phaseDrift = Math.sin(Math.floor(t / (7 * MIN_MS)) * 0.37);

    const reactiveVar = Math.abs(gridW) * Math.tan(Math.acos(pf)) + profile.reactiveBaseVar;
    const currentA = Math.abs(gridW) / (Math.sqrt(3) * voltage * Math.max(pf, 0.72));
    const gsm = clamp(
      -82 + Math.sin(Math.floor(t / (30 * MIN_MS)) * 0.53) * 4 + Math.cos(Math.floor(t / HOUR_MS) * 0.31) * 2,
      -93,
      -72,
    );

    let deltaConsumedKwh = 0;
    let deltaGeneratedKwh = 0;
    if (i > 0) {
      const dtHours = stepMs / HOUR_MS;
      deltaConsumedKwh = Math.max(gridW, 0) * dtHours / 1000;
      deltaGeneratedKwh = Math.max(-gridW, 0) * dtHours / 1000;
      consumedTotal += deltaConsumedKwh;
      generatedTotal += deltaGeneratedKwh;
      reactiveTotal += reactiveVar * dtHours / 1000;
    }

    readings.push({
      t,
      deltaConsumedKwh: round(deltaConsumedKwh, 4),
      deltaGeneratedKwh: round(deltaGeneratedKwh, 4),
      active_power_total_w: round(gridW, 1),
      reactive_power_total_var: round(reactiveVar, 1),
      voltage_phase_a_v: round(voltage + 0.7 + phaseDrift * 0.18, 1),
      voltage_phase_b_v: round(voltage - 1.1 - phaseDrift * 0.14, 1),
      voltage_phase_c_v: round(voltage + 0.2 + phaseDrift * 0.11, 1),
      current_total_a: round(currentA, 2),
      power_factor_total: round(pf, 3),
      active_energy_consumed_total_kwh: round(consumedTotal, 3),
      active_energy_generated_total_kwh: round(generatedTotal, 3),
      reactive_energy_generated_total_kvarh: round(reactiveTotal, 3),
      gsm_signal_rssi_dbm: Math.round(gsm),
    });
  }

  return readings;
}

function buildSeries(readings: EnergyMockReading[]): Record<SeriesCol, EnergySeriesPoint[]> {
  const series: Record<SeriesCol, EnergySeriesPoint[]> = {
    active_power_total_w: [],
    reactive_power_total_var: [],
    voltage_phase_a_v: [],
    voltage_phase_b_v: [],
    voltage_phase_c_v: [],
    current_total_a: [],
    power_factor_total: [],
    active_energy_consumed_total_kwh: [],
    active_energy_generated_total_kwh: [],
    reactive_energy_generated_total_kvarh: [],
    gsm_signal_rssi_dbm: [],
  };

  for (const reading of readings) {
    for (const col of SERIES_COLS) {
      series[col].push({ t: reading.t, v: reading[col] });
    }
  }

  return series;
}

function buildBars(readings: EnergyMockReading[], hours: number): EnergyBar[] {
  const barStepMs = barStepMsForHours(hours);
  const buckets = new Map<number, { consumed: number; generated: number }>();

  for (const reading of readings) {
    const bucket = Math.floor(reading.t / barStepMs) * barStepMs;
    const acc = buckets.get(bucket) ?? { consumed: 0, generated: 0 };
    acc.consumed += reading.deltaConsumedKwh;
    acc.generated += reading.deltaGeneratedKwh;
    buckets.set(bucket, acc);
  }

  return Array.from(buckets.entries())
    .sort(([a], [b]) => a - b)
    .map(([t, value]) => ({
      t,
      consumed_kwh: round(value.consumed, 3),
      generated_kwh: round(value.generated, 3),
    }));
}

function latestFromReading(reading: EnergyMockReading): EnergyLatest {
  const voltageAvgValue = (reading.voltage_phase_a_v + reading.voltage_phase_b_v + reading.voltage_phase_c_v) / 3;

  return {
    active_power_total_w: reading.active_power_total_w,
    reactive_power_total_var: reading.reactive_power_total_var,
    voltage_phase_a_v: reading.voltage_phase_a_v,
    voltage_phase_b_v: reading.voltage_phase_b_v,
    voltage_phase_c_v: reading.voltage_phase_c_v,
    voltage_avg_v: round(voltageAvgValue, 1),
    current_total_a: reading.current_total_a,
    power_factor_total: reading.power_factor_total,
    active_energy_consumed_total_kwh: reading.active_energy_consumed_total_kwh,
    active_energy_generated_total_kwh: reading.active_energy_generated_total_kwh,
    reactive_energy_generated_total_kvarh: reading.reactive_energy_generated_total_kvarh,
    delta_active_energy_consumed_kwh: reading.deltaConsumedKwh,
    delta_active_energy_generated_kwh: reading.deltaGeneratedKwh,
    gsm_signal_rssi_dbm: reading.gsm_signal_rssi_dbm,
    collected_at_utc: new Date(reading.t).toISOString(),
  };
}

export function buildEnergyDashboardMock(slug: string, hours: number): EnergyDashboardResponse {
  const profile = profileForSlug(slug);
  const readings = buildReadings(profile, hours);
  const latestReading = readings[readings.length - 1];
  const lastSeenUtc = new Date(latestReading.t).toISOString();

  return {
    installation_slug: slug,
    installation_name: profile.installationName,
    hours,
    last_seen_utc: lastSeenUtc,
    online: true,
    latest: latestFromReading(latestReading),
    series: buildSeries(readings),
    bars: buildBars(readings, hours),
  };
}
