import { Navigate } from 'react-router-dom';
import type { ReactElement } from 'react';
import type { UserRole } from '../types/auth';
import { useAuth } from '../hooks/useAuth';

interface RequireRoleProps {
  roles: UserRole[];
  children: ReactElement;
}

export function RequireRole({ roles, children }: RequireRoleProps) {
  const { role, isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="h-6 w-6 rounded-full border-2 border-primary border-t-transparent animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) return <Navigate to="/" replace />;
  if (role === null || !roles.includes(role)) return <Navigate to="/menu" replace />;

  return children;
}
