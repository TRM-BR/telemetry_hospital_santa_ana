import { ArrowRight } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface NavCardProps {
  icon: LucideIcon;
  title: string;
  description: string;
  delayMs?: number;
  onClick?: () => void;
}

export function NavCard({ icon: Icon, title, description, delayMs = 0, onClick }: NavCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group relative w-full overflow-hidden rounded-2xl border border-border bg-card p-5 text-left shadow-soft transition-all duration-300 ease-out hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-card animate-drop-in"
      style={{ animationDelay: `${delayMs}ms` }}
    >
      <span className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary-glow/0 via-primary-glow/0 to-primary-glow/10 opacity-0 transition-opacity duration-500 group-hover:opacity-100" />
      <div className="relative flex items-start justify-between gap-3">
        <div className="rounded-xl bg-gradient-to-br from-primary to-primary-glow p-2.5 text-primary-foreground shadow-soft">
          <Icon className="h-5 w-5" />
        </div>
        <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform duration-300 group-hover:translate-x-1 group-hover:text-primary" />
      </div>
      <p className="relative mt-4 text-base font-semibold text-foreground">{title}</p>
      <p className="relative mt-1 text-xs text-muted-foreground">{description}</p>
    </button>
  );
}

export default NavCard;
