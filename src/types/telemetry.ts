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
