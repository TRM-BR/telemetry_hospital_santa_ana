import { useQuery } from '@tanstack/react-query';
import { api, getToken } from '../services/api';
import type { UserMe, UserRole } from '../types/auth';

interface AuthState {
  user: UserMe | null;
  role: UserRole | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

export function useAuth(): AuthState {
  const hasToken = Boolean(getToken());

  const { data: user, isLoading } = useQuery<UserMe>({
    queryKey: ['auth', 'me'],
    queryFn: () => api<UserMe>('/auth/me'),
    enabled: hasToken,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  return {
    user: user ?? null,
    role: (user?.role as UserRole) ?? null,
    isAuthenticated: !!user,
    isLoading: hasToken ? isLoading : false,
  };
}
