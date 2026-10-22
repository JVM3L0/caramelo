# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). A versão minor
identifica a fase do [roadmap](docs/ROADMAP.md) (`0.2.x` = fase 1) e cada sub-branch sobe o patch.

## [0.2.2] - Semear o catálogo (fase 1: coleta)

### Adicionado
- `caramelo seed <loja> <categoria> [--pages N] [--every 2h]`: descobre os produtos de uma categoria
  e os coloca em monitoramento, executado pelo worker. Mostra antes o custo estimado em requisições.
  A página de categoria já traz os preços (1 requisição para até 60 produtos), então o primeiro
  ponto de preço de cada produto não custa nada a mais. As primeiras coletas são espalhadas ao longo
  do intervalo e produtos já monitorados mantêm o seu agendamento.
- `DealSource.discover(category, max_pages)` e o caso de uso `SeedCatalog`.
- Kabum: leitura de páginas de categoria (só produtos vendidos pelo próprio KaBuM!; preço de
  campanha ativa no lugar do preço base; item com `quantity` 0 conta como esgotado).
- **Rate limit:** repouso da loja após bloqueio (30 min ou `Retry-After`, no máximo 6 h), sem
  requisições durante o repouso; categorias validadas (nada que o `robots.txt` proíba) e limite de
  10 páginas por descoberta; novas configurações `CARAMELO_SEED_COLLECT_INTERVAL` e
  `CARAMELO_SOURCE_BLOCK_COOLDOWN`.

### Alterado
- Cada salto de redirect passa pelo `Throttle` (antes o `httpx` seguia sozinho e o ritmo real era o
  dobro do configurado), e a URL final do produto é lembrada para não repetir o salto. Um redirect
  para a página de verificação não é mais seguido, porque o `robots.txt` a proíbe.
- Falhas que não adianta repetir (`retryable = False`: bloqueio, layout quebrado e categoria
  inválida) não são mais tentadas de novo pela fila.

### Documentação
- Roadmap: portas `AttributeExtractor`, `ProductLinker` e `KnowledgeBase` na fase 2, e o vínculo
  avançado de produtos (Levenshtein por token, score composto, NER, base de conhecimento e
  embeddings) planejado para a fase 7.

## [0.2.1] - Kabum (fase 1: coleta)

### Adicionado
- Integração com o Kabum (`adapters/sources/kabum.py`): lê a página pública do produto
  (`/produto/<código>`), com preço no Pix, preço no cartão, parcelas e estoque. Identifica o bot
  honestamente (`CarameloBot`) e passa pelo `Throttle`. Bloqueios (403, 429 ou a página de
  verificação) viram erro e o job tenta de novo; produto removido (404) é ignorado.

### Alterado
- O MVP passou a usar o **Kabum** como primeira loja: a API do Mercado Livre não entrega preços
  (busca e itens retornam 403, catálogo vem sem oferta) e as páginas dele exigem verificação de conta.

## [0.2.0] - Catálogo monitorado (fase 1: coleta)

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
