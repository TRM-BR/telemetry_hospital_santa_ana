// Constantes do Dashboard — independentes de mock.

import type { WindowKey } from '../types/telemetry';

export const WINDOW_OPTIONS: { value: WindowKey; label: string }[] = [
  { value: '1h', label: '1h' },
  { value: '6h', label: '6h' },
  { value: '24h', label: '24h' },
  { value: '7d', label: '7 dias' },
  { value: '30d', label: '30 dias' },
];

// Janela → horas (param `hours` do endpoint /dashboard)
export const WINDOW_TO_HOURS: Record<WindowKey, number> = {
  '1h': 1,
  '6h': 6,
  '24h': 24,
  '7d': 168,
  '30d': 720,
};

// Paleta de cores (triplets HSL) para uma linha por remota.
// Usada como `hsl(<triplet>)` pelo HistoryChart.
export const DEVICE_COLORS: string[] = [
  '217 91% 60%', // azul
  '142 71% 45%', // verde
  '38 92% 50%',  // âmbar
  '340 82% 52%', // rosa
  '262 83% 58%', // roxo
  '199 89% 48%', // ciano
];

// Paleta do dashboard do hospital, estilo Clima:
// linha 1 = azul da marca, linha 2 = âmbar (accent). HistoryChart aplica como
// `hsl(<valor>)`, então tanto 'var(--x)' quanto triplets HSL funcionam.
export const CHART_COLORS: string[] = [
  'var(--primary)',  // Grupo 1 — azul da marca
  'var(--accent)',   // Grupo 2 — âmbar (cor nova)
];
