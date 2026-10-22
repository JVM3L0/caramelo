# Roadmap do Caramelo

Cada fase entrega algo que funciona sozinho e termina com um critério de pronto verificável.
As fases 1 a 5 formam o MVP: o BuscaPC publicando ofertas reais de forma automática.

| Fase | Nome                         | Resultado                                              |
|------|------------------------------|--------------------------------------------------------|
| 0    | Fundação ✅                  | Esqueleto, banco, fila e testes rodando em containers  |
| 1    | Coleta                       | Histórico de preços do Kabum crescendo                 |
| 2    | Catálogo                     | Anúncios agrupados por produto e por família (chip)    |
| 3    | Análise e detecção           | Regras de "desconto real" calibradas com dados         |
| 4    | Publicação                   | Ofertas saindo nos canais Geral e Alertas              |
| 5    | Admin pelo bot               | Operar o sistema pelo Telegram                         |
| 6    | Operação                     | Saber rápido quando algo quebra                        |
| 7    | Ligar o que foi adiado       | Afiliados, proxy, texto por LLM, card com gráfico      |
| 8    | Expansão e SaaS              | Mais lojas, mais canais, outros donos de canal         |

---

## Fase 0: Fundação ✅

- Projeto com uv, ruff, pyright e import-linter garantindo a arquitetura hexagonal.
- Domínio: `Price`, `PricePoint` (Pix e cartão separados), `ProductFamily → Product → Listing`,
  `RawOffer`, `Deal`, `Tenant`, `Channel`.
- Ports: `DealSource`, `UnitOfWork`/repositórios, `TaskQueue`, `Publisher`, `AffiliateLinker`,
  `CopyWriter`, `Clock`.
- Caso de uso `CollectSource` (grava toda observação no histórico).
- Postgres + Timescale (`price_points` como hypertable), Alembic, Procrastinate.
- `compose.yaml` com `db`, `migrate` e `worker`; testes unitários e de integração.

**Pronto quando:** `compose up` sobe tudo e `pytest` passa. ✔

## Fase 1: Coleta

Objetivo: começar a acumular histórico o quanto antes, porque a fase 3 depende de semanas de dados.

1. **Catálogo monitorado** (entregue em `0.2.0`): `caramelo watch <url> --every 30m` cadastra um
   anúncio (CLI provisória até o bot da fase 5), e o agendador coleta cada anúncio no seu intervalo.
2. **Adapter Kabum** (entregue em `0.2.1`): lê a página pública do produto (dados embutidos do
   Next.js e JSON-LD), sem API. Só páginas permitidas pelo `robots.txt`, ritmo baixo e User-Agent
   honesto. **Pendente:** ler os termos de venda do Kabum (`m.kabum.com.br/checkout/confirmacao/termos/`).
3. **Semear o catálogo** (entregue em `0.2.2`): `caramelo seed kabum hardware/placa-de-video-vga
   --pages 1 --every 2h` descobre os produtos de uma categoria. A página de categoria já traz os
   preços, então 1 requisição cobre até 60 produtos e grava o primeiro ponto de preço de cada um.
   As primeiras coleções são espalhadas ao longo do intervalo. Só produtos vendidos pelo próprio
   Kabum (marketplace fica de fora). **Falta:** rodar categoria por categoria (GPU, CPU, SSD, RAM,
   monitor, periféricos) e acompanhar a carga.
4. **Mercado Livre fica para depois**: a API não entrega preços (busca e itens dão 403, o catálogo
   vem sem oferta) e as páginas de produto redirecionam para uma verificação de conta anti-robô.
   Só vale retomar com acesso oficial ou feed de parceiros.
5. **Boas maneiras com as lojas** (entregue, requisito de projeto): todo contato com a loja passa
   pelo mesmo caminho, que garante:
   - pausa mínima entre requisições (`CARAMELO_REQUEST_MIN_INTERVAL`, 2 s), contando **cada salto
     de redirect**, e a URL final é lembrada para não repetir o salto;
   - um job por loja por vez (lock do Procrastinate), inclusive a descoberta;
   - em bloqueio (403, 429 ou página de verificação) a loja fica em **repouso** (30 min, ou o
     `Retry-After`, no máximo 6 h) sem nenhuma requisição, e o job **não** é repetido;
   - a página de verificação nunca é requisitada (o `robots.txt` a proíbe);
   - só caminhos de categoria simples (nada de busca, carrinho, `sort=` ou `?query=`), no máximo
     10 páginas por descoberta;
   - coletas espalhadas no tempo, e o `seed` mostra o custo estimado antes de enfileirar.
6. **Testes** dos adapters com páginas reais reduzidas, salvas como fixtures.

**Pronto quando:** o worker coleta sozinho, sem intervenção, por 7 dias seguidos, e cada anúncio
monitorado tem pontos de preço no período.

## Fase 2: Catálogo

Objetivo: poder dizer "a RTX 4070 Super mais barata do Brasil hoje", e não só "este SKU baixou".

1. **Taxonomia**: categorias (GPU, CPU, placa-mãe, RAM, SSD, fonte, gabinete, monitor, periféricos)
   como dados no banco.
2. **Extração de atributos por categoria** a partir do título, com regex e testes:
   - GPU: chip e VRAM (`RTX 4070 SUPER 12GB`);
   - CPU: modelo (`Ryzen 7 7800X3D`);
   - RAM: tipo, capacidade e frequência;
   - SSD: capacidade e interface (NVMe Gen3/Gen4, SATA);
   - monitor: tamanho, resolução e taxa de atualização.
3. **Casamento de anúncios**, em cascata, do mais confiável ao menos: EAN/GTIN, MPN (o Kabum não
   informa nenhum dos dois, mas o código do fabricante aparece no título), e por fim marca + modelo
   + atributos extraídos do título. Anúncio → produto → família.
   - **Só liga com confiança alta.** O ambíguo fica com `product_id` nulo e continua acumulando
     histórico: um casamento errado é pior que nenhum, porque gera falso "menor preço".
   - **Origem do vínculo** nos dados (`match_source`: `ean`, `mpn`, `title` ou `manual`, mais a
     confiança), para reprocessar só os vínculos fracos quando uma regra mudar.
   - **Fila de revisão** dos não casados e dos de baixa confiança, com correção manual que vale
     mais que a regra (no bot da fase 5).
   - Testes com títulos reais de várias categorias.
   - **Portas desde já**, com implementação simples: `AttributeExtractor` (título → atributos, por
     regras e regex) e `ProductLinker` (atributos → produto e família, com confiança), e uma
     `KnowledgeBase` lida de um arquivo versionado. A fase 7 troca ou acrescenta implementações
     sem mexer no domínio.
4. **Filtros de confiança**: descartar usado, recondicionado e kits inesperados. No Mercado Livre,
   aceitar só loja oficial ou vendedor com boa reputação.
5. **Métricas de custo-benefício**: R$/GB para SSD e RAM.

**Pronto quando:** pelo menos 90% dos anúncios monitorados estão ligados a uma família e os
filtros não deixam passar usados nem kits.

## Fase 3: Análise e detecção

Objetivo: definir com dados, e não no chute, o que é um desconto real.

1. **Agregados contínuos do Timescale**: mediana diária do preço no Pix por anúncio e por família.
   Política de compressão para o histórico antigo.
2. **Notebook de exploração** (pandas): como os preços oscilam por categoria, quantos alertas cada
   limiar geraria por dia, quantos "descontos" são inflados (preço sobe e depois "cai").
3. **Regras configuráveis como dados**, por exemplo:
   - preço abaixo da mediana de 30 ou 90 dias em X%;
   - menor preço em N dias;
   - possível erro de preço (queda brusca entre duas coletas);
   - mais barato entre as lojas para a mesma família.
4. **Caso de uso `DetectDeals`**, executado após cada coleta, que gera `Deal`s com os motivos
   ("menor preço em 90 dias") e uma pontuação.
5. Limiares separados para **Geral** (curado) e **Alertas** (mais permissivo).

**Pronto quando:** rodando as regras sobre o histórico, o volume diário de ofertas fica dentro do
alvo (por exemplo, 15 a 25 no Geral) e uma amostra revisada à mão não tem descontos falsos.

## Fase 4: Publicação

1. **Adapter `Publisher` do Telegram** (aiogram) e serviço `bot` no compose.
2. **Cadastro dos canais** Geral e Alertas (no início, num canal de teste privado).
3. **Roteamento**: quais ofertas vão para cada canal, de acordo com as regras da fase 3.
4. **Controle de volume**: não repostar a mesma oferta em 24 h (a menos que o preço caia mais),
   limite diário por canal e horário de silêncio.
5. **Texto** pelo `TemplateCopyWriter`, com motivo e comparação ("média de 30 dias: R$ X → -Y%").
6. **Expiração**: quando o preço volta a subir, editar a mensagem original para "❌ Encerrada".
7. **Modo de ensaio** (`dry_run`): gerar as mensagens sem enviar, para revisar antes de abrir.

**Pronto quando:** o canal de teste recebe ofertas automaticamente por uma semana sem duplicatas
e sem estourar o limite diário. Depois disso, publicar no BuscaPC de verdade.

## Fase 5: Admin pelo bot

- Bot privado, aceitando comandos só dos seus IDs de usuário do Telegram.
- Comandos: `/monitorar <url>`, `/parar <url>`, `/pausar` e `/retomar` (publicação),
  `/status` (última coleta por loja, falhas, posts do dia), `/ultimas` (últimas ofertas
  detectadas), `/regras` (ver e ajustar limiares).

**Pronto quando:** dá para operar o dia a dia sem abrir o banco nem o terminal.

## Fase 6: Operação

- Logs estruturados (JSON) com o contexto de coleta → detecção → publicação.
- **Detecção de quebra de scraper**: alerta no bot quando uma loja retorna zero ofertas, muitos
  erros ou muitos campos vazios. Esse é o problema mais comum em produção.
- Backup diário do banco (`pg_dump`) com teste de restauração.
- Painel de saúde simples no `/status`, mais métricas (Prometheus/Grafana) só se fizer falta.
- Decidir onde hospedar (VPS com Podman/compose é o caminho natural a partir do setup local).

## Fase 7: Ligar o que foi adiado

Cada item é um adapter novo atrás de um port que já existe, sem mudar o domínio:

- **Links de afiliado**: inscrever-se nos programas (Mercado Livre, Kabum, Amazon...), criar
  `AffiliateLinker`s reais e uma tag por tenant.
- **Encurtador próprio** para medir cliques por oferta e por canal, alimentando a pontuação.
- **Proxy** (`CARAMELO_HTTP_PROXY`), se as lojas começarem a bloquear.
- **`CopyWriter` com LLM**: títulos mais chamativos por canal, mantendo o template como reserva.
- **Card de imagem** com o gráfico de preço de 90 dias.

### Vínculo avançado de produtos

Só depois que as regras da fase 2 estiverem rodando e a fila de revisão tiver exemplos reais.
Cada item é um adapter novo das portas `AttributeExtractor`, `ProductLinker` e `KnowledgeBase`.

1. **Normalização do título** (se ainda não estiver na fase 2): minúsculas e sem acento, letra
   separada de número (`RTX5050` → `rtx 5050`), unidades coladas (`8 GB` → `8gb`), palavras vazias
   removidas e tokens ordenados. Num teste com títulos reais, isso derrubou a distância entre
   escritas diferentes do mesmo produto de 22 e 19 para 0.
2. **Distância de Levenshtein por token**, sobre os campos extraídos (marca, linha, nome comercial)
   comparados com os apelidos da base de conhecimento, nunca sobre o título inteiro.
   - Tolerância por tipo de token: números, capacidades e sufixos de chip (`ti`, `super`, `xt`)
     exigem **distância 0**; palavras de marca ou de linha aceitam 1 edição a partir de 5 letras e
     2 a partir de 9; palavras de até 4 letras exigem 0 (`venus` não vira `ventus`).
   - Motivo: sobre o texto cru, produtos diferentes ficam mais perto que o mesmo produto escrito de
     outro jeito (RTX 4070 × 4070 Ti: distância 3; mesmo produto reescrito: 16 a 22).
   - Implementação: `rapidfuzz.distance.Levenshtein` (com Damerau para letras trocadas) ou a função
     `levenshtein()` do Postgres; `pg_trgm` para trazer candidatos com índice. **Conferir** se
     `fuzzystrmatch` e `pg_trgm` estão na imagem do TimescaleDB.
3. **Score composto** e três faixas de decisão: alta confiança liga sozinho, a faixa do meio vai
   para a fila de revisão e a baixa fica sem vínculo. Componentes: atributos duros iguais (senão
   descarta), EAN/MPN, marca, distância dos tokens e verificação de preço (item 6). Os limiares
   saem dos exemplos revisados, medindo os erros que cada um deixaria passar, e não de chute.
4. **Reconhecimento de entidades (NER)**: primeiro regras e dicionário, que cobrem bem um
   vocabulário fechado; um modelo próprio (por exemplo spaCy) ou um LLM com cache por título só se
   as regras pararem de evoluir. Os títulos corrigidos na fila de revisão viram os exemplos de
   treino.
5. **Base de conhecimento de especificações** (chips, linhas, MPN, EAN, apelidos e atributos):
   - nasce como arquivo versionado no repositório, com a **procedência** de cada dado (fonte e
     data da conferência), alimentado pelos chips que aparecem nos títulos reais e pelos produtos
     aprovados na fila de revisão;
   - fontes só depois de **ler os termos e a licença de cada uma** (dados abertos como o Wikidata,
     páginas oficiais dos fabricantes e as fichas das próprias lojas); sites de terceiros que
     proíbam coleta automatizada ficam de fora;
   - se uma importação automática compensar, vira um adapter novo no molde das lojas.
6. **Verificação por distância de preço**: um anúncio ligado a uma família cujo preço está muito
   longe da mediana dela (um suporte de GPU de R$ 41 numa família de R$ 2.000) é quase certamente
   um vínculo errado ou um acessório. Também serve à fase 3 para tirar acessórios do cálculo da
   mediana, e é barato o bastante para antecipar se fizer falta.
7. **Embeddings (`pgvector`)**: apenas como gerador de candidatos e para sinônimos e idiomas
   (`GPU` = `placa de vídeo`). Nunca decidem sozinhos, porque números e sufixos curtos mudam pouco o
   vetor (`4070` e `4070 Ti` ficam muito próximos).

## Fase 8: Expansão e SaaS

- **Mais lojas**: Mercado Livre (se houver acesso oficial), Pichau, Terabyte, Amazon e AliExpress (canal separado).
- **Mais canais**: Discord, WhatsApp e e-mail com resumo diário.
- **Alertas pessoais**: `/alerta rtx 4070 < 3500` no privado do bot.
- **SaaS**: cadastro de outros donos de canal, cada um com seus canais, regras e tag de afiliado;
  painel web; cobrança. A coleta e o histórico continuam globais e compartilhados.
- Revisar a marca (BuscaPC × Buscapé, INPI) antes de investir em divulgação.
