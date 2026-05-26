// ============================================================
// MOCK CENTRALIZADO — Hospital Santa Ana (POC)
// ============================================================
// ATENÇÃO: todos os dados aqui são SIMULADOS para demonstração.
// Não refletem integração real com sensores ou sistemas externos.
// Substitua as exportações por chamadas de API quando disponível.
// ============================================================

import type { HospitalMockData } from '../types/telemetry';

// Gera rótulos horários para 24h (00:00 … 23:00)
function makeHours(): string[] {
  return Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`);
}

const HOURS = makeHours();

// ── Nível Grupo 1 (%): dip matinal (6–10h), recuperação à tarde ──
const LEVEL_G1_VALUES = [
  82, 81, 81, 80, 80, 79,   // 00–05
  76, 72, 70, 72, 74, 75,   // 06–11
  76, 77, 78, 78, 77, 76,   // 12–17
  75, 74, 75, 76, 77, 78,   // 18–23
];

// ── Nível Grupo 2 (%): dip matinal + vespertino, recuperação parcial ──
const LEVEL_G2_VALUES = [
  70, 69, 68, 68, 67, 66,   // 00–05
  62, 57, 55, 58, 61, 63,   // 06–11
  65, 66, 66, 65, 64, 61,   // 12–17
  58, 56, 59, 61, 63, 64,   // 18–23
];

// ── Vazão estimada (m³/h): picos às 6–10h e 18–21h; soma ≈ 46 m³ ──
const FLOW_VALUES = [
  0.8, 0.7, 0.7, 0.7, 0.8, 1.1,   // 00–05
  3.4, 4.1, 3.7, 2.6, 2.1, 1.8,   // 06–11
  1.9, 1.9, 1.7, 1.5, 1.5, 1.7,   // 12–17
  2.7, 3.1, 2.8, 2.1, 1.4, 1.2,   // 18–23
]; // Soma ≈ 46,0 m³

export const hospitalSantaAnaMock: HospitalMockData = {
  // ── Instalação ──────────────────────────────────────────────
  installation: {
    name: 'Hospital Santa Ana',
    city: 'Santana de Parnaíba',
    poc: true,
    referenceDailyConsumptionM3: 46.11,
    monitoredCapacityLiters: 80_000,
    lastReadingLabel: 'Última leitura simulada',
    lastReadingSimulatedAt: '26/05/2026 09:17',
    status: 'attention',  // G2 abaixo do nível ideal
  },

  // ── Reservatórios de recalque (NÃO monitorados) ─────────────
  contextReservoirs: [
    {
      id: 'recalque-1',
      name: 'Recalque 1',
      capacityLiters: 40_000,
      monitored: false,
      label: 'Não monitorado nesta etapa',
    },
    {
      id: 'recalque-2',
      name: 'Recalque 2',
      capacityLiters: 40_000,
      monitored: false,
      label: 'Não monitorado nesta etapa',
    },
  ],

  // ── Grupos de caixas superiores (MONITORADOS) ───────────────
  tankGroups: [
    {
      id: 'grupo-1',
      name: 'Grupo 1',
      tanks: 4,
      capacityPerTankLiters: 10_000,
      totalCapacityLiters: 40_000,
      monitored: true,
      levelPct: 78,
      status: 'normal',
      estimatedAutonomyHours: 38,
    },
    {
      id: 'grupo-2',
      name: 'Grupo 2',
      tanks: 4,
      capacityPerTankLiters: 10_000,
      totalCapacityLiters: 40_000,
      monitored: true,
      levelPct: 64,
      status: 'attention',   // abaixo do nível ideal de 70%
      estimatedAutonomyHours: 30,
    },
  ],

  // ── Séries temporais 24h (simuladas) ────────────────────────
  series: {
    levelG1Hourly: HOURS.map((hour, i) => ({
      hour,
      value: LEVEL_G1_VALUES[i],
    })),
    levelG2Hourly: HOURS.map((hour, i) => ({
      hour,
      value: LEVEL_G2_VALUES[i],
    })),
    estimatedFlowM3Hourly: HOURS.map((hour, i) => ({
      hour,
      value: FLOW_VALUES[i],
    })),
  },

  // ── Alertas simulados ────────────────────────────────────────
  alerts: [
    {
      id: 'alert-001',
      severity: 'attention',
      message: 'Grupo 2 abaixo do nível ideal — 64% (mínimo recomendado: 70%)',
      timeLabel: 'há 12 min',
    },
    {
      id: 'alert-002',
      severity: 'info',
      message: 'Consumo acima da média no período da manhã (6h–10h)',
      timeLabel: 'há 1h 42 min',
    },
    {
      id: 'alert-003',
      severity: 'info',
      message: 'Última leitura simulada recebida com sucesso',
      timeLabel: 'há 1 min',
    },
  ],
};
