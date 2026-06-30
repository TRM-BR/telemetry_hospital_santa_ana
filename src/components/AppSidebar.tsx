import { useState, createContext, useContext } from 'react';
import type { ReactNode } from 'react';
import { LogOut, Map as MapIcon, AlertTriangle, Radio, Pin, CheckSquare, Zap } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { cn } from '../lib/cn';
import { logout } from '../services/auth';
import { useAuth } from '../hooks/useAuth';
import { TOP_BAR_HEIGHT_PX } from '../constants/layout';

const SIDEBAR_COLLAPSED = 80;
const SIDEBAR_EXPANDED = 256;

interface AppSidebarContextType {
  expanded: boolean;
  pinned: boolean;
  setExpanded: (v: boolean) => void;
  setPinned: (v: boolean) => void;
  width: number;
}

const AppSidebarContext = createContext<AppSidebarContextType | undefined>(undefined);

export function AppSidebarProvider({ children }: { children: ReactNode }) {
  const [expanded, setExpanded] = useState(false);
  const [pinned, setPinned] = useState(false);
  const isOpen = expanded || pinned;

  return (
    <AppSidebarContext.Provider
      value={{
        expanded,
        pinned,
        setExpanded,
        setPinned,
        width: isOpen ? SIDEBAR_EXPANDED : SIDEBAR_COLLAPSED,
      }}
    >
      {children}
    </AppSidebarContext.Provider>
  );
}

export function useAppSidebar(): AppSidebarContextType {
  const ctx = useContext(AppSidebarContext);
  if (!ctx) throw new Error('useAppSidebar must be used within AppSidebarProvider');
  return ctx;
}

const BASE_NAV_ITEMS = [
  { to: '/menu',                        label: 'Menu',    Icon: MapIcon       },
  { to: '/remotas',                     label: 'Remotas', Icon: Radio         },
  { to: '/instalacao/escola/energia',   label: 'Energia', Icon: Zap           },
  // { to: '/meteorologia', label: 'Clima', Icon: CloudRain  },
  { to: '/alertas',                     label: 'Avisos',  Icon: AlertTriangle },
] as const;

const APPROVER_NAV_ITEMS = [
  { to: '/aprovacoes', label: 'Aprovações', Icon: CheckSquare },
] as const;

export function AppSidebar() {
  const { expanded, pinned, setExpanded, setPinned, width } = useAppSidebar();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { role } = useAuth();
  const isOpen = expanded || pinned;

  const navItems = [
    ...BASE_NAV_ITEMS,
    ...(role === 'approver' || role === 'admin' ? APPROVER_NAV_ITEMS : []),
  ];

  function handleLogout() {
    logout(queryClient);
    navigate('/', { replace: true });
  }

  return (
    <aside
      className={cn(
        'fixed left-0 top-0 h-screen z-50 bg-card border-r border-border flex flex-col overflow-hidden',
        'transition-[width] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]',
      )}
      style={{ width }}
      onMouseEnter={() => !pinned && setExpanded(true)}
      onMouseLeave={() => !pinned && setExpanded(false)}
    >
      {/* Header */}
      <div
        className="p-4 border-b border-border flex flex-col items-center gap-2"
        style={{ minHeight: TOP_BAR_HEIGHT_PX }}
      >
        <div className="flex items-center justify-center w-full">
          <img
            src="/brasao_santana_de_parnaiba.webp"
            alt="Brasão"
            className={cn(
              'object-contain transition-all duration-500',
              isOpen ? 'h-10 w-10' : 'h-8 w-8',
            )}
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
          />
        </div>
        <div
          className={cn(
            'text-center transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] overflow-hidden',
            isOpen ? 'opacity-100 max-h-20' : 'opacity-0 max-h-0 pointer-events-none',
          )}
        >
          <p className="text-[13px] font-semibold text-foreground leading-tight">Hospital Santa Ana</p>
          <p className="text-[9px] uppercase tracking-[0.22em] text-muted-foreground leading-tight">
            Santana do Parnaíba
          </p>
        </div>
        <div className={cn('w-full flex justify-center', isOpen ? 'mt-1' : 'mt-0')}>
          <button
            onClick={() => setPinned(!pinned)}
            className="p-1 hover:bg-secondary rounded transition-colors"
            title={pinned ? 'Desafixar' : 'Afixar'}
          >
            <Pin
              className={cn(
                'h-3.5 w-3.5 transition-transform duration-300',
                pinned ? 'text-primary fill-primary rotate-45' : 'text-muted-foreground/70',
              )}
            />
          </button>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-2 p-4">
        {navItems.map(({ to, label, Icon }) => {
          const active = location.pathname === to || location.pathname.startsWith(to + '/');
          return (
            <button
              key={to}
              onClick={() => navigate(to)}
              className={cn(
                'w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors duration-300',
                active
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
              )}
              title={label}
            >
              <Icon className="h-5 w-5 flex-shrink-0" />
              <span
                className={cn(
                  'text-sm font-medium whitespace-nowrap transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]',
                  isOpen ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-2 pointer-events-none',
                )}
              >
                {label}
              </span>
            </button>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-border">
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-secondary text-muted-foreground hover:text-foreground transition-colors"
          title="Sair"
        >
          <LogOut className="h-5 w-5 flex-shrink-0" />
          <span
            className={cn(
              'text-sm font-medium whitespace-nowrap transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]',
              isOpen ? 'opacity-100 translate-x-0' : 'opacity-0 -translate-x-2 pointer-events-none',
            )}
          >
            Sair
          </span>
        </button>
      </div>
    </aside>
  );
}

export { SIDEBAR_COLLAPSED, SIDEBAR_EXPANDED };
