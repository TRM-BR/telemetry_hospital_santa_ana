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
  level_pct: number | null;
  level_m: number | null;
  current_ma: number | null;
  battery_v: number | null;
  signal: number | null;
  voltage_v: number | null;
}

export type FillReferenceSource =
  | 'estimated_daily_max_p90'
  | 'provisional_p90'
  | 'provisional_observed_max'
  | 'none';

export type FillReferenceConfidence = 'high' | 'low' | 'none';

export interface DashDevice {
  device_id: number;
  imei: string;
  label: string | null;
  model: string | null;
  status: string | null;
  last_seen_utc: string | null;
  active: boolean;
  latest: DashDeviceLatest;
  // séries por métrica: level_pct, level_m, current_ma
  series: Record<string, SeriesPoint[]>;
  // referência de 100% operacional (cheio estimado, read-time, não persistido)
  fill_reference_m: number | null;
  fill_reference_source: FillReferenceSource;
  fill_reference_confidence: FillReferenceConfidence;
  fill_reference_day_count: number;
}

export interface InstallationDashboardResponse {
  installation_slug: string;
  installation_name: string;
  hours: number;
  last_seen_utc: string | null;
  device_count: number;
  active_count: number;
  devices: DashDevice[];
}
