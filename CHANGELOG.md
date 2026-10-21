# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). Cada fase do
[roadmap](docs/ROADMAP.md) corresponde a uma versão.

## [0.2.0] - Em andamento (fase 1: coleta)

### Adicionado
- Catálogo monitorado: cada anúncio tem intervalo de coleta próprio (`collect_interval`) e data da
  próxima coleta (`next_collect_at`).
- Comando `caramelo watch <url> --every 30m` para monitorar um produto (faz a primeira coleta na hora).
- Job periódico `schedule_due_collections` (a cada minuto) que cria jobs de coleta em lotes por loja,
  com lock por loja para coletar uma por vez. Retentativa com espera exponencial.
- `Throttle`: intervalo mínimo entre requisições à mesma loja (`CARAMELO_REQUEST_MIN_INTERVAL`).
- CI no GitHub Actions: ruff, pyright, import-linter e pytest (incluindo integração).

### Alterado
- `DealSource` agora busca produtos específicos (`fetch(external_ids)`) e reconhece URLs da própria
  loja (`external_id_from_url`). `CollectSource` virou `CollectListings`.
- `TaskQueue.enqueue` aceita `lock`.
- A coluna `listings.monitored` foi substituída pelo agendamento.

## [0.1.0] - 2026-10-21 (fase 0: fundação)

### Adicionado
- Esqueleto hexagonal, domínio, ports, persistência em Postgres + TimescaleDB, fila Procrastinate,
  compose com `db`, `migrate` e `worker`, testes unitários e de integração.
