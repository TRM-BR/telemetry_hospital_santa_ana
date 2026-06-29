// Tipos da API /installations/{slug}/energy/dashboard

export interface EnergySeriesPoint {
  t: number;  // epoch ms UTC
  v: number;
}

export interface EnergyBar {
  t: number;            // epoch ms do início do bucket UTC
  consumed_kwh: number; // delta consumo ativo ≥ 0 → barra para baixo no gráfico
  generated_kwh: number;// delta geração ativa ≥ 0 → barra para cima no gráfico
}

export interface EnergyLatest {
  active_power_total_w: number | null;
  reactive_power_total_var: number | null;
  voltage_phase_a_v: number | null;
  voltage_phase_b_v: number | null;
  voltage_phase_c_v: number | null;
  current_total_a: number | null;
  power_factor_total: number | null;
  active_energy_consumed_total_kwh: number | null;
  active_energy_generated_total_kwh: number | null;
  reactive_energy_generated_total_kvarh: number | null;
  delta_active_energy_consumed_kwh: number | null;
  delta_active_energy_generated_kwh: number | null;
  gsm_signal_rssi_dbm: number | null;
  collected_at_utc: string | null;
}

export interface EnergyDashboardResponse {
  installation_slug: string;
  installation_name: string;
  hours: number;
  last_seen_utc: string | null;  // UTC ISO 8601 Z
  online: boolean;
  latest: EnergyLatest;
  series: Record<string, EnergySeriesPoint[]>;
  bars: EnergyBar[];
}

// Janelas de tempo reaproveitadas do dashboard
export type EnergyWindowKey = '1h' | '6h' | '24h' | '7d' | '30d';

export const ENERGY_WINDOW_TO_HOURS: Record<EnergyWindowKey, number> = {
  '1h': 1,
  '6h': 6,
  '24h': 24,
  '7d': 168,
  '30d': 720,
};

export const ENERGY_WINDOW_OPTIONS: { value: EnergyWindowKey; label: string }[] = [
  { value: '1h',  label: '1h' },
  { value: '6h',  label: '6h' },
  { value: '24h', label: '24h' },
  { value: '7d',  label: '7 dias' },
  { value: '30d', label: '30 dias' },
];
