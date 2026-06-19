// ============================================================
// MOCK CENTRALIZADO — Hospital Santa Ana
// Estrutura espelha o backend real (séries com timestamps unix).
// ============================================================

import type {
  Installation,
  TankGroup,
  ContextReservoir,
  SeriesPoint,
  DashboardSnapshot,
  InstallationMetrics,
  WindowKey,
} from '../types/telemetry';

// ── Instalação principal ────────────────────────────────────
export const installations: Installation[] = [
  {
    id: 'hospital-santa-ana',
    name: 'Hospital Santa Ana',
    address: 'R. Prof. Edgar de Moraes, 707 — Campo da Vila, Santana de Parnaíba — SP',
    lat: -23.4395,
    lng: -46.9173,
    status: 'online',
  },
];

// ── Bounds aproximados de Santana de Parnaíba ───────────────
export const santanaBounds = {
  north: -23.420,
  south: -23.460,
  west:  -46.940,
  east:  -46.895,
};

// ── Grupos de caixas superiores (monitorados) ───────────────
export const tankGroups: TankGroup[] = [
  {
    id: 'grupo-1',
    name: 'Grupo 1',
    tanks: 4,
    capacityPerTankLiters: 10_000,
    totalCapacityLiters: 40_000,
    levelPct: 78,
    status: 'online',
    estimatedAutonomyHours: 38,
  },
  {
    id: 'grupo-2',
    name: 'Grupo 2',
    tanks: 4,
    capacityPerTankLiters: 10_000,
    totalCapacityLiters: 40_000,
    levelPct: 64,
    status: 'online',
    estimatedAutonomyHours: 30,
  },
];

// ── Reservatórios de recalque (contexto hidráulico) ─────────
export const contextReservoirs: ContextReservoir[] = [
  { id: 'recalque-1', name: 'Recalque 1', capacityLiters: 40_000 },
  { id: 'recalque-2', name: 'Recalque 2', capacityLiters: 40_000 },
];

// ── Helpers para gerar séries ───────────────────────────────
const HOUR_MS = 60 * 60 * 1000;
const MIN_MS  = 60 * 1000;

interface WindowSpec { points: number; stepMs: number; }

const windowSpecs: Record<WindowKey, WindowSpec> = {
  '1h':  { points: 60,  stepMs: 1 * MIN_MS },     // 1h, ponto a cada 1 min
  '6h':  { points: 72,  stepMs: 5 * MIN_MS },     // 6h, ponto a cada 5 min
  '24h': { points: 96,  stepMs: 15 * MIN_MS },    // 24h, ponto a cada 15 min
  '7d':  { points: 168, stepMs: 1 * HOUR_MS },    // 7d, ponto a cada 1 h
  '30d': { points: 180, stepMs: 4 * HOUR_MS },    // 30d, ponto a cada 4 h
};

// Curva senoidal calibrada com picos manhã (7h-10h) e noite (18h-21h)
function flowCurve(hour: number, base: number, peakMorning: number, peakEvening: number): number {
  const h = hour % 24;
  const morningPeak = Math.exp(-Math.pow((h - 8) / 1.7, 2)) * peakMorning;
  const eveningPeak = Math.exp(-Math.pow((h - 19) / 2.0, 2)) * peakEvening;
  const lunchPeak   = Math.exp(-Math.pow((h - 13) / 1.4, 2)) * (peakMorning * 0.4);
  return base + morningPeak + eveningPeak + lunchPeak;
}

// Curva de nível: cai durante consumo e enche lentamente
function levelCurve(hour: number, baseline: number, amplitude: number, offset = 0): number {
  const h = (hour + offset) % 24;
  const dip1 = Math.exp(-Math.pow((h - 8) / 2.0, 2)) * amplitude;       // dip manhã
  const dip2 = Math.exp(-Math.pow((h - 19) / 2.2, 2)) * (amplitude * 0.7);  // dip noite
  return baseline - dip1 - dip2;
}

function pressureCurve(hour: number, base: number, range: number): number {
  const h = hour % 24;
  // Pressão sobe quando consumo cai (madrugada) e cai quando consumo sobe
  const drop = Math.exp(-Math.pow((h - 8) / 2.0, 2)) * range +
               Math.exp(-Math.pow((h - 19) / 2.2, 2)) * (range * 0.8);
  return base - drop;
}

/**
 * Gera uma série temporal com `points` pontos terminando em "agora",
 * espaçados `stepMs`. O gerador recebe a hora (0..24) e devolve o valor.
 */
function buildSeries(
  spec: WindowSpec,
  generator: (hour: number, idx: number) => number,
  jitter = 0,
): SeriesPoint[] {
  const now = Date.now();
  const start = now - spec.points * spec.stepMs;
  const result: SeriesPoint[] = [];
  for (let i = 0; i < spec.points; i++) {
    const t = start + i * spec.stepMs;
    const d = new Date(t);
    const hour = d.getHours() + d.getMinutes() / 60;
    const base = generator(hour, i);
    const noise = jitter ? (Math.sin(i * 1.7) + Math.cos(i * 0.3)) * jitter * 0.5 : 0;
    result.push({ t, v: +(base + noise).toFixed(2) });
  }
  return result;
}

/**
 * Constrói um snapshot completo do dashboard para uma janela.
 * Inclui séries de nível, vazão (2 grupos) e pressão (2 grupos).
 */
export function buildDashboardSnapshot(windowKey: WindowKey = '24h'): DashboardSnapshot {
  const spec = windowSpecs[windowKey];

  // Nível médio: combinação dos dois grupos (G1: 78%, G2: 64%) → média ~71
  const nivel = buildSeries(spec, (h) => levelCurve(h, 75, 14, 0), 0.8);
  // Vazão 1: base 60 L/min, picos manhã/noite
  const vazao1 = buildSeries(spec, (h) => Math.max(0, flowCurve(h, 50, 90, 70)), 4);
  // Vazão 2: base 45 L/min, picos menores
  const vazao2 = buildSeries(spec, (h) => Math.max(0, flowCurve(h, 40, 70, 55)), 3);
  // Pressão 1: 3.5 MCA base
  const pressao1 = buildSeries(spec, (h) => pressureCurve(h, 3.6, 0.9), 0.05);
  // Pressão 2: 3.2 MCA base
  const pressao2 = buildSeries(spec, (h) => pressureCurve(h, 3.3, 0.8), 0.05);

  const last = (arr: SeriesPoint[]) => (arr.length ? arr[arr.length - 1].v : 0);

  const nivelAtual = +last(nivel).toFixed(1);
  const vazao1Atual = +last(vazao1).toFixed(2);
  const vazao2Atual = +last(vazao2).toFixed(2);
  const consumoAtual = +((vazao1Atual + vazao2Atual) / 1000 * 60).toFixed(2); // L/min → m³/h
  const consumoMedio = +(
    [...vazao1, ...vazao2].reduce((s, p) => s + p.v, 0) /
    (vazao1.length + vazao2.length) / 1000 * 60
  ).toFixed(2);

  const estado: DashboardSnapshot['estado'] =
    nivelAtual >= 70 ? 'Confortável' :
    nivelAtual >= 40 ? 'Atenção'    :
    nivelAtual > 0   ? 'Crítico'    : 'Sem leitura';

  const autonomiaDias = consumoAtual > 0
    ? +(Math.max(0, (nivelAtual / 100) * 80_000 / (consumoAtual * 1000) / 24)).toFixed(1)
    : 0;

  return {
    nivelAtual,
    estado,
    autonomiaDias,
    consumoMedio,
    consumoAtual,
    vazao1: vazao1Atual,
    vazao2: vazao2Atual,
    pressao1: +last(pressao1).toFixed(2),
    pressao2: +last(pressao2).toFixed(2),
    ultimaLeitura: new Date(nivel.length ? nivel[nivel.length - 1].t : Date.now()),
    series: { nivel, vazao1, vazao2, pressao1, pressao2 },
  };
}

/**
 * Métricas resumidas pra página de Installation (hero + KPIs).
 */
export function buildInstallationMetrics(): InstallationMetrics {
  const snap = buildDashboardSnapshot('24h');
  // Spark: últimos 12 pontos de nível (suaviza pra o card)
  const spark = snap.series.nivel.slice(-12).map((p) => p.v);
  const sumVazao = snap.vazao1 + snap.vazao2; // L/min
  // Consumo "hoje": integra vazão da janela 24h
  const consumoHoje = +(
    [...snap.series.vazao1, ...snap.series.vazao2].reduce((s, p) => s + p.v, 0) /
    (snap.series.vazao1.length + snap.series.vazao2.length) *
    24 * 60 / 1000
  ).toFixed(2);

  // Variação vs dia anterior (mock fixo positivo)
  const variacaoPct = 8.4;

  // Total no mês (mock)
  const totalMes = +(consumoHoje * 22).toFixed(1);

  return {
    consumoHoje,
    variacaoPct,
    vazao: +sumVazao.toFixed(1),
    pressao: snap.pressao1,
    totalMes,
    anomalias: 2,
    nivel: snap.nivelAtual,
    spark,
    ultimaLeituraMin: 2,
  };
}

export const WINDOW_OPTIONS: { value: WindowKey; label: string }[] = [
  { value: '1h',  label: '1h' },
  { value: '6h',  label: '6h' },
  { value: '24h', label: '24h' },
  { value: '7d',  label: '7 dias' },
  { value: '30d', label: '30 dias' },
];
