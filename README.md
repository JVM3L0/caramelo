# Caramelo 🐕

Farejador de promoções: coleta preços em vários e-commerces, separa desconto real de desconto
falso pelo histórico de preços e publica as ofertas em canais (Telegram primeiro).

O primeiro canal é o **BuscaPC**, focado em componentes e periféricos de PC. A plataforma nasce
preparada para virar SaaS (`tenant_id` e canais como dados desde o início).

O plano completo está em [docs/ROADMAP.md](docs/ROADMAP.md).

## Stack

Python 3.13 · uv · PostgreSQL 16 + TimescaleDB · SQLAlchemy 2 + Alembic · Procrastinate (fila de
jobs no próprio Postgres) · httpx + selectolax · aiogram (a partir da fase 4) · Podman ou Docker.

## Rodando

```bash
cp .env.example .env          # opcional
podman compose up -d --build  # ou: docker compose up -d --build
podman compose logs -f worker
```

Sobem três serviços:

| Serviço   | O que faz                                                        |
|-----------|------------------------------------------------------------------|
| `db`      | Postgres + TimescaleDB, publicado em `127.0.0.1:5432`            |
| `migrate` | Aplica as migrations do Alembic e o schema da fila, depois sai   |
| `worker`  | Executa os jobs em segundo plano (coleta, detecção, publicação)  |

## Desenvolvimento

```bash
uv sync                       # cria .venv com as dependências
uv run pytest                 # testes (os de integração sobem um container do Timescale)
uv run pytest -m "not integration"
uv run ruff check . && uv run ruff format .
uv run pyright
uv run lint-imports           # garante as regras da arquitetura
uv run alembic revision -m "descricao"   # nova migration (com o db rodando)
```

Os testes de integração usam testcontainers. Com Podman, exporte antes:
`DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock` e `TESTCONTAINERS_RYUK_DISABLED=true`
(com `systemctl --user enable --now podman.socket`).

## Uso

```bash
# monitorar um produto (a loja é reconhecida pela URL; requer a integração da loja, fase 1)
podman compose run --rm worker watch https://... --every 30m
```

O worker roda um job a cada minuto que cria as coletas dos anúncios vencidos, em lotes por loja.
Variáveis úteis: `CARAMELO_DEFAULT_COLLECT_INTERVAL` (padrão `1h`) e
`CARAMELO_REQUEST_MIN_INTERVAL` (pausa entre requisições à mesma loja, em segundos).

## Contribuindo

Fluxo: `develop → main`. Cada fase do roadmap tem uma branch `phase/<X.Y.Z>-<slug>` criada a partir de
`develop`; o trabalho é feito em sub-branches `<tipo>/<X.Y.Z>-<slug>` (`feat`, `fix`, `chore`, `docs`,
`refactor`, `test`) que entram na branch da fase por PR. Ao fim da fase, a branch da fase entra em
`develop` e é criada a tag `vX.Y.Z`; `main` recebe `develop` quando a fase está estável.

- A versão pertence à fase: sobe uma vez no `pyproject.toml`; as sub-branches só adicionam linhas ao
  `CHANGELOG.md`.
- Antes do PR: `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run lint-imports && uv run pytest`.

## Arquitetura

Hexagonal (ports & adapters) num monólito modular:

```
src/caramelo/
  domain/        entidades e regras puras (sem dependências externas)
  application/   casos de uso + ports (interfaces) que eles usam
  adapters/      implementações dos ports: persistence, queue, http, affiliate, copywriting...
  entrypoints/   composição (container), configuração e CLI (`caramelo migrate|worker`)
```

As regras são verificadas pelo `lint-imports`:

- as camadas só dependem das de baixo (`entrypoints → adapters → application → domain`);
- `domain` e `application` não importam bibliotecas de infraestrutura;
- um adapter não importa outro, então cada um pode ser trocado isoladamente.

Pontos de troca já previstos:

| Port              | Implementação atual          | Troca futura                     |
|-------------------|------------------------------|----------------------------------|
| `TaskQueue`       | Procrastinate (Postgres)     | Redis + arq, se a fila apertar   |
| `AffiliateLinker` | `passthrough` (link original)| Programas de afiliado por tenant |
| `CopyWriter`      | `template`                   | Texto gerado por LLM             |
| Cliente HTTP      | sem proxy                    | `CARAMELO_HTTP_PROXY`            |
| `DealSource`      | —                            | Kabum, Mercado Livre (fase 1)    |
| `Publisher`       | —                            | Telegram (fase 4)                |
