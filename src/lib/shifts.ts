const SP_TZ = 'America/Sao_Paulo';

export function todaySaoPaulo(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: SP_TZ }).format(new Date());
}
