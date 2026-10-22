# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/). A versão minor
identifica a fase do [roadmap](docs/ROADMAP.md) (`0.2.x` = fase 1) e cada sub-branch sobe o patch.

## [0.2.4] - CI mais rápido (fase 1: coleta)

### Alterado
- CI em **três jobs paralelos** (lint, tipos e arquitetura; testes unitários; testes de integração).
  O tempo total passa a ser o do mais lento, em vez da soma de tudo, e os testes unitários dão
  retorno em segundos sem esperar o banco.
- `actions/setup-python` antes do `uv`: o runner já traz o Python 3.13, então o `uv` não baixa uma
  cópia a cada execução. Cache de `~/.npm`, onde o pyright guarda o que baixa num runner frio.
- `concurrency`: um push novo na mesma branch ou PR cancela a execução anterior.
- Testes de integração: **um único container do TimescaleDB por execução** (antes, um por módulo),
  com um banco migrado para cada módulo. A imagem tem ~1,9 GB, então puxá-la e iniciá-la é a parte
  cara; a preparação do segundo módulo caiu de 4,2 s para 0,2 s.

## [0.2.3] - Dashboard no terminal (fase 1: coleta)

### Adicionado
- `caramelo dashboard [--refresh 5]`: painel no terminal (Textual), **somente leitura**: lê o banco e
  nunca fala com a loja, então olhar o painel não gera nenhuma requisição.
  - **Visão geral:** por loja, o estado (coletando, atrasado, parado, aguardando), anúncios
    monitorados, esgotados, última e próxima coleta, pontos de preço, atrasados e a carga estimada em
    requisições por hora; e a fila de jobs (pendentes, em execução, falhas e o mais antigo pendente).
  - **Anúncios:** tabela com preço no Pix e no cartão, uma **tendência** (mini-gráfico dos últimos
    preços, verde se caiu e vermelho se subiu), a variação contra a coleta anterior (▼ verde,
    ▲ vermelho), estoque, número de coletas e idade. Busca por nome (`/`), filtro de estoque (`e`),
    só mudanças de preço (`m`) e ordem (`o`: recentes, menor preço, maiores quedas, nome).
  - **Histórico** (Enter num anúncio): gráfico do preço no Pix e no cartão dos últimos 30 dias, em
    degraus (o preço de uma loja fica fixo até mudar), com menor, mediana, maior e preço atual, o
    quanto o atual está abaixo ou acima da mediana, e a lista das últimas coletas. Coletas esgotadas
    não entram no gráfico.
  - **Atividade da coleta** na Visão geral: pontos de preço por hora nas últimas 24 h, com as horas
    vazias, para ver se o worker está regular.
  - Se o banco cair, mostra o aviso e mantém os últimos dados na tela.
- Gráficos com `textual-plotext`; o resumo do histórico (`summarize`) é uma função pura da camada de
  aplicação, que a fase 3 pode reaproveitar para a mediana de "desconto real".
- Portas de leitura `DashboardQueries` e `QueueStatistics` (camada de aplicação), com adapters em
  SQL (`adapters/persistence/dashboard.py`) e no Procrastinate (`adapters/queue/stats.py`). Uma
  interface web futura reaproveita as mesmas consultas.
- Configuração `CARAMELO_DASHBOARD_REFRESH_SECONDS` (5).
- Os logs do painel vão para `~/.local/state/caramelo/dashboard.log` (só avisos e erros). Antes, o
  nível INFO do CLI escrevia no terminal e podia desenhar linhas por cima da interface.

### Corrigido
- **Estoque na leitura de categorias do Kabum.** O `quantity` da listagem é o estoque da *campanha*,
  não do produto: os itens fora de campanha vêm com 0 e continuam à venda (a página do produto os
  mostra como disponíveis). A 0.2.2 os marcava como esgotados. Agora vale o `available`, e uma
  campanha esgotada (`quantityAvailable` 0) volta ao preço base. Os pontos já gravados com o erro
  (a primeira coleta de produtos sem campanha) continuam no histórico.

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
