import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import type { ReactElement } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { isAuthenticated } from './services/auth';
import { RequireRole } from './components/RequireRole';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
});

import Login from './pages/Login';
import Cadastro from './pages/Cadastro';
import CadastroConfirmar from './pages/CadastroConfirmar';
import EsqueciSenha from './pages/EsqueciSenha';
import RedefinirSenha from './pages/RedefinirSenha';
import Aprovacoes from './pages/Aprovacoes';
import MapPage from './pages/Map';
import Installation from './pages/Installation';
import Dashboard from './pages/Dashboard';
import Alerts from './pages/Alerts';
import Remotas from './pages/Remotas';
import WeatherDashboard from './pages/WeatherDashboard';
import EnergyDashboard from './pages/EnergyDashboard';
import NotFound from './pages/NotFound';
import { AppSidebar, AppSidebarProvider, useAppSidebar } from './components/AppSidebar';

function RequireAuth({ children }: { children: ReactElement }) {
  if (!isAuthenticated()) return <Navigate to="/" replace />;
  return children;
}

const PUBLIC_PATHS = ['/', '/cadastro', '/cadastro/confirmar', '/esqueci-senha', '/redefinir-senha'];

function AppContent() {
  const location = useLocation();
  const { width } = useAppSidebar();
  const isPublicPage = PUBLIC_PATHS.some(
    (p) => location.pathname === p || location.pathname.startsWith(p + '/'),
  );

  return (
    <>
      {!isPublicPage && <AppSidebar />}
      <div
        key={location.pathname}
        className="animate-page-enter"
        style={{
          marginLeft: isPublicPage ? 0 : width,
          transition: 'margin-left 500ms cubic-bezier(0.22,1,0.36,1)',
        }}
      >
        <Routes>
          {/* Public routes */}
          <Route path="/" element={<Login />} />
          <Route path="/cadastro" element={<Cadastro />} />
          <Route path="/cadastro/confirmar" element={<CadastroConfirmar />} />
          <Route path="/esqueci-senha" element={<EsqueciSenha />} />
          <Route path="/redefinir-senha" element={<RedefinirSenha />} />

          {/* Approvals — approver and admin only */}
          <Route
            path="/aprovacoes"
            element={
              <RequireRole roles={['approver', 'admin']}>
                <Aprovacoes />
              </RequireRole>
            }
          />

          {/* Protected routes — any authenticated user */}
          <Route
            path="/menu"
            element={
              <RequireAuth>
                <MapPage />
              </RequireAuth>
            }
          />
          <Route
            path="/instalacao/:id"
            element={
              <RequireAuth>
                <Installation />
              </RequireAuth>
            }
          />
          <Route
            path="/instalacao/:id/dashboard"
            element={
              <RequireAuth>
                <Dashboard />
              </RequireAuth>
            }
          />
          <Route
            path="/alertas"
            element={
              <RequireAuth>
                <Alerts />
              </RequireAuth>
            }
          />
          <Route
            path="/meteorologia"
            element={
              <RequireAuth>
                <WeatherDashboard />
              </RequireAuth>
            }
          />
          <Route
            path="/remotas"
            element={
              <RequireRole roles={['admin']}>
                <Remotas />
              </RequireRole>
            }
          />
          <Route
            path="/instalacao/:slug/energia"
            element={
              <RequireAuth>
                <EnergyDashboard />
              </RequireAuth>
            }
          />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </div>
    </>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppSidebarProvider>
          <AppContent />
        </AppSidebarProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
