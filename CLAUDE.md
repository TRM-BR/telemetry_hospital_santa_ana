# Orientação para agentes (Claude Code) no repositório `telemetry`

Este projeto é uma plataforma de telemetria de água para prédios públicos,
em modelo **single-tenant replicado** (uma instância por prefeitura).

## Princípios não-negociáveis (V1)

1. **Bridge MQTT é camada pura de ingestão.** Conecta, recebe, grava em
   `raw_messages`. Não parsea, não calcula, não decide.
2. **ACK MQTT só depois do commit do RAW.** Critério único.
3. **Banco é fonte da verdade e fila inicial.** Sem Redis na V1.
4. **Workers fazem polling com `FOR UPDATE SKIP LOCKED`** + padrão de 2 transações
   (claim curta → processa fora da TX → grava resultado em outra TX curta).
5. **Cada worker tem watchdog interno.** Sem reconciler separado.
6. **Frontend operacional não calcula nada de telemetria.** Apenas exibe
   `derived_metrics` + `alert_state` via API orientada por tela.
7. **Visual do front é intocável.** Mudanças só em `services/`, `hooks/`,
   `lib/mappers/`, `types/`.
8. **Tudo em UTC no banco.** Conversão de fuso só em mappers do front.
9. **Endpoints e nomes em inglês.** Timestamp como ISO 8601 com `Z`.
10. **Customização por prefeitura vira config (`clients/<slug>.yaml`),
    nunca fork de código.**

## O que NÃO fazer

- Adicionar Redis Streams ou reconciler separado sem ADR aprovado.
- Trocar Paho por aiomqtt sem ADR aprovado.
- Calcular vazão/pressão/nível no React.
- Adicionar `if cidade == 'X':` no código — vira config.
- Usar prefixo `hydroforce_*` em código novo (só ao referenciar legado).
- Espalhar `if` de migração em componentes visuais — vai para `lib/mappers/`.
- Manter transação aberta durante parser ou cálculo.
- Usar `SELECT FOR UPDATE` sem `SKIP LOCKED`.
- Publicar telemetria com `retain=True` no MQTT (retain é só para status).
- Criar arquivos `.md` de documentação sem ser explicitamente solicitado.
- Commit de `.env`, segredos ou credenciais.

## Onde encontrar contexto

| Documento | Conteúdo |
|---|---|
| `docs/adr/` | Decisões arquiteturais registradas (5 ADRs iniciais) |
| `docs/architecture.md` | Desenho técnico V1 (a preencher) |
| `docs/audit-bridge-legacy.md` | Auditoria da bridge antiga (output da Fase 1) |
| `docs/inventory-frontend.md` | Mapa do front aprovado (output da Fase 2) |
| `docs/legacy-mapping.md` | Tabelas `hydroforce_*` → novas (output da Fase 4) |
| `docs/migration-plan.md` | Plano de cutover por fases |

## Padrão de workers (resumo obrigatório)

```text
TX1 (curta):
  SELECT id ... WHERE status IN ('pending','temporary_error')
   AND (last_attempt_at IS NULL OR last_attempt_at < now() - backoff(attempts))
   ORDER BY received_at_utc LIMIT 50 FOR UPDATE SKIP LOCKED;
  UPDATE ... SET status='processing', processing_since=now(),
                 worker_id='<self>', attempts=attempts+1;
COMMIT;

(processa fora de transação — parser/cálculo/avaliação)

TX2 (curta):
  INSERT INTO <destino> ... ON CONFLICT DO NOTHING;
  UPDATE <origem> SET status='done', error_message=NULL, processing_since=NULL
    WHERE id=<x> AND worker_id='<self>' AND status='processing';
  -- se rowcount=0, watchdog reclamou; ROLLBACK
COMMIT;
```

**Verificação de posse na TX2 (`AND worker_id='<self>'`)** é obrigatória —
defesa contra watchdog que reclamou o registro enquanto o worker original
ainda processava.

## Parâmetros operacionais (configuráveis por cliente)

| Parâmetro | Valor inicial |
|---|---|
| `batch_size` | 50 |
| `idle_seconds` (sem trabalho) | 5 |
| `stuck_threshold` (watchdog) | 5 min |
| `max_attempts` | 5 |
| Backoff entre tentativas | 1 min → 5 min → 15 min → 1 h → 6 h |

## Branches

- `main` — estável.
- `dev` — integração.
- Toda mudança nasce em `dev`. `main` só recebe estável.
- Tag de release em `main` a cada deploy importante.

## Nomenclatura (rígida)

- Repositório/codename: `telemetry`.
- Bancos: `telemetry_<slug_cidade>_<ambiente>` (ex.: `telemetry_barueri_prod`).
- Tabelas: neutras, sem prefixo (`raw_messages`, `parsed_measurements`, ...).
- Tópicos MQTT: `telemetry/<slug>/...`.
- Serviços Docker: `telemetry-api`, `telemetry-bridge`, `telemetry-worker-parse`.
- Variáveis env: `TELEMETRY_*`.
- Python imports: `from app...` (o pacote interno é `app/`, não `telemetry/`).

## Frontend

- Visual aprovado. **Não redesenhar** sem aprovação explícita.
- Stack mantida: React 18 + Vite + Tailwind + shadcn/ui + MUI + TanStack Query
  + Recharts + Leaflet.
- Token no localStorage: chave `hf_token` (mantida por compatibilidade com o
  legado, evita re-login no cutover).
- Datas vêm da API em **UTC ISO 8601** (`...Z`); mapper converte para fuso
  local conforme `branding.timezone`.

## API

- Endpoints em inglês (`/api/v1/telemetry/series`, não `/api/v1/telemetria/series`).
- Todos os timestamps na resposta em **UTC ISO 8601 com `Z`**.
- Endpoints orientados por tela — front nunca precisa orquestrar 10 chamadas
  para montar um dashboard.
- OpenAPI publicado em `/docs`.

## Legado

- Banco legado: `hydroforce_db` (MariaDB) — apenas leitura durante migração.
- Tabelas legadas: prefixo `hydroforce_*` — **não replicar esse prefixo** em
  código novo. Quando referenciar, prefixar com "legado:".
- Bridge legada (`comunication/bridge_dragino.py` no repo legado):
  referência para auditoria e extração de lógica, não para copy-paste.

## Estilo

- Python 3.12, type hints obrigatórios em funções públicas, ruff + mypy.
- TypeScript estrito no front.
- Mensagens de commit em português ou inglês — consistente dentro de uma série.
- Sem emojis em código (sem ressalvas para CLAUDE.md/README).

## Convenções de teste

- Golden tests para parsers: payloads MQTT reais em
  `backend/app/tests/fixtures/payloads/` produzem `ParsedResult` esperado
  em arquivos `.expected.json`.
- Workers testados com injeção de falha (matar processo entre TX1 e TX2,
  validar que watchdog devolve para `pending`).
- Sem testes E2E na V1 — homologação paralela contra o sistema legado é o
  critério de aceitação.
