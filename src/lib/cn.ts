/** Junta classes CSS filtrando valores falsy. Sem dependências externas. */
export function cn(...classes: (string | boolean | null | undefined)[]): string {
  return classes.filter(Boolean).join(' ');
}
