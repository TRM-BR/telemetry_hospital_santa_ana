// ============================================================
// Tipos base — Hospital Santa Ana POC
// Centralizados aqui para facilitar troca futura por API real
// ============================================================

export type SystemStatus = 'normal' | 'attention' | 'critical';
export type AlertSeverity = 'info' | 'attention' | 'critical';

export interface Installation {
  name: string;
  city: string;
  poc: true;
  referenceDailyConsumptionM3: number;
  monitoredCapacityLiters: number;
  lastReadingLabel: string;
  lastReadingSimulatedAt: string;
  status: SystemStatus;
}

export interface ContextReservoir {
  id: string;
  name: string;
  capacityLiters: number;
  monitored: false;
  label: string;
}

export interface TankGroup {
  id: string;
  name: string;
  tanks: number;
  capacityPerTankLiters: number;
  totalCapacityLiters: number;
  monitored: true;
  levelPct: number;
  status: SystemStatus;
  estimatedAutonomyHours: number;
}

export interface HourlyPoint {
  hour: string;   // "00:00", "01:00" ...
  value: number;
}

export interface MockSeries {
  levelG1Hourly: HourlyPoint[];
  levelG2Hourly: HourlyPoint[];
  estimatedFlowM3Hourly: HourlyPoint[];
}

export interface Alert {
  id: string;
  severity: AlertSeverity;
  message: string;
  timeLabel: string;
}

export interface HospitalMockData {
  installation: Installation;
  contextReservoirs: ContextReservoir[];
  tankGroups: TankGroup[];
  series: MockSeries;
  alerts: Alert[];
}
