// Tipos do domínio — Hospital Santa Ana

export type InstallationStatus = 'online' | 'alert' | 'offline';
export type AlertSeverity = 'info' | 'attention' | 'critical';

export interface Installation {
  id: string;
  name: string;
  address: string;
  lat: number;
  lng: number;
  status: InstallationStatus;
}

export interface SeriesPoint {
  t: number;   // unix ms
  v: number;
}

export interface InstallationMetrics {
  consumoHoje: number;
  variacaoPct: number;
  vazao: number;
  pressao: number;
  totalMes: number;
  anomalias: number;
  nivel: number;
  spark: number[];
  ultimaLeituraMin: number;
}

export interface TankGroup {
  id: string;
  name: string;
  tanks: number;
  capacityPerTankLiters: number;
  totalCapacityLiters: number;
  levelPct: number;
  status: InstallationStatus;
  estimatedAutonomyHours: number;
}

export interface ContextReservoir {
  id: string;
  name: string;
  capacityLiters: number;
}

export interface DashboardSnapshot {
  nivelAtual: number;
  estado: 'Confortável' | 'Atenção' | 'Crítico' | 'Sem leitura';
  autonomiaDias: number;
  consumoMedio: number;
  consumoAtual: number;
  vazao1: number;
  vazao2: number;
  pressao1: number;
  pressao2: number;
  ultimaLeitura: Date;
  series: {
    nivel: SeriesPoint[];
    vazao1: SeriesPoint[];
    vazao2: SeriesPoint[];
    pressao1: SeriesPoint[];
    pressao2: SeriesPoint[];
  };
}

export interface Alert {
  id: string;
  severity: AlertSeverity;
  message: string;
  timeLabel: string;
}

export type WindowKey = '1h' | '6h' | '24h' | '7d' | '30d';
export type FilterMode = 'janela' | 'periodo';

// ── Respostas reais da API (/installations/{slug}/dashboard) ────────────────

export interface DashDeviceLatest {
  // Headline nominal (level_pct = percentual nominal, não escala do sensor)
  level_pct: number | null;
  level_m: number | null;
  current_ma: number | null;
  battery_v: number | null;
  signal: number | null;
  voltage_v: number | null;
  // Campos explícitos nominais
  nivel_m: number | null;
  percentual: number | null;
  volume_tank_l: number | null;
  volume_group_l: number | null;
  faltante_tank_l: number | null;
  faltante_group_l: number | null;
  altura_faltante_m: number | null;
  // Compat
  volume_l: number | null;       // = volume_group_l
  faltante_l: number | null;     // = faltante_group_l
  // Campo técnico: % da escala bruta do sensor (0–4 m), apenas diagnóstico
  sensor_level_pct?: number | null;
}

export interface DashDevice {
  device_id: number;
  imei: string;
  label: string | null;
  model: string | null;
  status: string | null;
  last_seen_utc: string | null;
  active: boolean;
  latest: DashDeviceLatest;
  series: Record<string, SeriesPoint[]>;
  group_name?: string | null;
  group_capacity_l?: number | null;
  tank_count?: number | null;
}

export interface ShiftWindow {
  label: string;
  start: string;  // "HH:MM"
  end: string;    // "HH:MM"
}

export interface GroupConsumption {
  index: number;
  label: string;
  m3: number;
  share: number;
}

export interface ConsumptionSummary {
  total_m3: number;
  window: ShiftWindow;
  groups: GroupConsumption[];
}

export interface InstallationDashboardResponse {
  installation_slug: string;
  installation_name: string;
  hours: number;
  last_seen_utc: string | null;
  device_count: number;
  active_count: number;
  devices: DashDevice[];
  volume_total_l: number;
  faltante_total_l: number;
  capacidade_total_l: number;
  consumption_summary?: ConsumptionSummary | null;
}
