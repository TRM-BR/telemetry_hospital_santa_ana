import { FlaskConical } from 'lucide-react';

/**
 * Badge discreto exibido em toda a interface para deixar claro
 * que os dados são simulados (POC) — não integração real.
 */
export function MockDataBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-400/40 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold text-amber-700">
      <FlaskConical className="h-3 w-3" />
      POC — dados simulados
    </span>
  );
}
