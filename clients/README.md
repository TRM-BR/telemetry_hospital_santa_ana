# clients/ — Configuração por prefeitura

Esta pasta contém um arquivo YAML por instância (prefeitura) do
sistema. Cada arquivo descreve **todas** as diferenças entre uma
prefeitura e outra: branding, banco, broker, credenciais, retenção,
limiares de alerta default.

## Regra de ouro

> Se você precisa editar código Python ou React para adicionar uma
> nova cidade, o design falhou. Toda customização entra como YAML aqui.

## Arquivos especiais

| Arquivo | Conteúdo |
|---|---|
| `_schema.yaml` | Esquema canônico (com comentários) descrevendo todos os campos suportados. Versionado. |
| `_example.yaml` | Exemplo completo preenchido para servir de template. Versionado. |
| `<slug>.yaml` | Arquivo real de uma prefeitura. **Não versionado** — contém segredos referenciados via env. |

`<slug>.yaml` está no `.gitignore`. Apenas `_schema.yaml` e `_example.yaml` ficam no repositório.

## Como adicionar uma nova prefeitura

1. Copiar `_example.yaml` → `<slug>.yaml` (ex.: `barueri.yaml`).
2. Preencher os campos da nova prefeitura.
3. Senhas e segredos **não** vão no YAML — vão em `.env.<slug>` na
   VPS de destino, com `chmod 600`.
4. Validar com `python -m app.config.validate clients/<slug>.yaml`
   (a implementar na Fase 4).
5. Provisionar o banco `telemetry_<slug>_prod` no PostgreSQL.
6. Rodar `alembic upgrade head` apontando para o banco novo.
7. Build do front: `VITE_CLIENT_SLUG=<slug> npm run build`.
8. Deploy via `ops/scripts/deploy.sh <slug>` (a implementar).

## Convenção do `<slug>`

- **Lowercase, ASCII, sem espaços, sem hífens** (use underscore se precisar).
- Idealmente, igual ao nome da prefeitura sem acentos.
- Exemplos válidos: `barueri`, `osasco`, `santo_andre`, `cidadex`.
- Exemplos inválidos: `Barueri`, `barueri-sp`, `barueri sp`.

## Estrutura esperada

Ver `_schema.yaml`.
