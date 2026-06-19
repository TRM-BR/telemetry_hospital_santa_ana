export type AlertSeverity = 'info' | 'attention' | 'critical';
export type AlertStatus = 'active' | 'resolved';

export interface AlertItem {
  id: string;
  severity: AlertSeverity;
  status: AlertStatus;
  title: string;
  description: string;
  installation_name: string;
  rule_key: string;
  first_triggered_at: string;
  last_triggered_at: string;
  resolved_at?: string | null;
  viewed: boolean;
  recommendation?: string;
  relevant_data?: Record<string, unknown>;
}
