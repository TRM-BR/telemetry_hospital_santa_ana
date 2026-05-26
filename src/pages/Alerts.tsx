import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Droplets } from 'lucide-react';
import { alerts } from '../mocks/hospitalSantaAnaMock';
import AlertsList from '../components/dashboard/AlertsList';

const Alerts = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen w-full bg-secondary">
      <header className="sticky top-0 z-30 border-b border-border bg-card/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-3 sm:px-8">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-smooth hover:text-foreground hover:border-primary/40"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Voltar
          </button>

          <div className="flex items-center gap-3 text-primary">
            <img
              src="/santana-coat.png"
              alt="Brasão"
              className="h-10 w-10 object-contain"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
            />
            <div className="leading-tight hidden sm:block">
              <p className="text-[9px] uppercase tracking-[0.22em] text-muted-foreground">Santana de Parnaíba</p>
              <p className="text-[12px] font-semibold text-foreground">Alertas</p>
            </div>
          </div>

          <div className="hidden sm:flex items-center gap-2">
            <span className="text-[9px] uppercase tracking-[0.22em] text-muted-foreground">Powered by</span>
            <span className="inline-flex items-center gap-1 font-display text-sm text-primary">
              <Droplets className="h-3.5 w-3.5" />
              Verth
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-8 sm:px-8 sm:py-10">
        <div className="mb-6">
          <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Hospital Santa Ana</p>
          <h1 className="mt-1 text-3xl font-bold text-foreground">Alertas e eventos</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Vazamentos, picos de consumo e eventos do dispositivo.
          </p>
        </div>

        <AlertsList alerts={alerts} title="Todos os eventos" />
      </main>
    </div>
  );
};

export default Alerts;
