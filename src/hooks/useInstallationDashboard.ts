import { useQuery } from '@tanstack/react-query';
import { api } from '../services/api';
import type { InstallationDashboardResponse } from '../types/telemetry';

async function fetchInstallationDashboard(slug: string, hours: number): Promise<InstallationDashboardResponse> {
  return api<InstallationDashboardResponse>(
    `/installations/${slug}/dashboard?hours=${hours}`,
  );
}

export function useInstallationDashboard(slug: string, hours = 24) {
  return useQuery({
    queryKey: ['installation-dashboard', slug, hours],
    queryFn: () => fetchInstallationDashboard(slug, hours),
    refetchInterval: 30_000,
    staleTime: 25_000,
    enabled: slug.length > 0,
  });
}
