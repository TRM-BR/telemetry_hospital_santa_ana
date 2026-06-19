import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { AlertItem } from '../types/alerts';
import { mockAlerts } from '../mocks/alertsMock';

const QUERY_KEY = ['alerts'] as const;

async function fetchAlerts(): Promise<AlertItem[]> {
  try {
    const token = localStorage.getItem('hsa.auth.token');
    const res = await fetch('/api/v1/alerts?active_only=false', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    // TODO: remover fallback quando motor de alertas estiver ativo
    return Array.isArray(json?.alerts) ? json.alerts : mockAlerts;
  } catch {
    return mockAlerts;
  }
}

async function setAlertViewed(id: string, viewed: boolean): Promise<void> {
  const token = localStorage.getItem('hsa.auth.token');
  const method = viewed ? 'POST' : 'DELETE';
  await fetch(`/api/v1/alerts/${id}/viewed`, {
    method,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

export function useAlerts() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchAlerts,
    staleTime: 30_000,
  });
}

export function useToggleAlertViewed() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, viewed }: { id: string; viewed: boolean }) =>
      setAlertViewed(id, viewed),
    onMutate: async ({ id, viewed }) => {
      await qc.cancelQueries({ queryKey: QUERY_KEY });
      const prev = qc.getQueryData<AlertItem[]>(QUERY_KEY);
      qc.setQueryData<AlertItem[]>(QUERY_KEY, (old) =>
        old?.map((a) => (a.id === id ? { ...a, viewed } : a)) ?? [],
      );
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(QUERY_KEY, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: QUERY_KEY }),
  });
}
