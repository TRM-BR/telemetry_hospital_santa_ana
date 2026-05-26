import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import type { ReactElement } from 'react';
import { isAuthenticated } from './services/auth';

import Login from './pages/Login';
import MapPage from './pages/Map';
import Installation from './pages/Installation';
import Dashboard from './pages/Dashboard';
import Alerts from './pages/Alerts';
import NotFound from './pages/NotFound';

function RequireAuth({ children }: { children: ReactElement }) {
  if (!isAuthenticated()) return <Navigate to="/" replace />;
  return children;
}

function AppRoutes() {
  const location = useLocation();
  return (
    <div key={location.pathname} className="animate-page-enter">
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
        <Route path="*" element={<NotFound />} />
      </Routes>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}

export default App;
