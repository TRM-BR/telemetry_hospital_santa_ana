import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import type { ReactElement } from 'react';
import { isAuthenticated } from './services/auth';

import Login from './pages/Login';
import MapPage from './pages/Map';
import Installation from './pages/Installation';
import Dashboard from './pages/Dashboard';
import Alerts from './pages/Alerts';
import Remotas from './pages/Remotas';
import WeatherDashboard from './pages/WeatherDashboard';
import NotFound from './pages/NotFound';
import { AppSidebar, AppSidebarProvider, useAppSidebar } from './components/AppSidebar';

function RequireAuth({ children }: { children: ReactElement }) {
  if (!isAuthenticated()) return <Navigate to="/" replace />;
  return children;
}

function AppContent() {
  const location = useLocation();
  const { width } = useAppSidebar();
  const isPublicPage = location.pathname === '/';

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
          <Route path="/" element={<Login />} />
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
              <RequireAuth>
                <Remotas />
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
    <BrowserRouter>
      <AppSidebarProvider>
        <AppContent />
      </AppSidebarProvider>
    </BrowserRouter>
  );
}

export default App;
