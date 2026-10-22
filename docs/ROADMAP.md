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

1. **Catálogo monitorado.** Comando `caramelo watch <url> --every 30m` (CLI provisória até o bot da fase 5)
   que cadastra um anúncio para coleta. Semear algumas centenas de SKUs relevantes: GPUs, CPUs,
   SSDs, RAM, monitores e periféricos populares.
2. **Adapter Kabum** (entregue): lê a página pública do produto (dados embutidos do Next.js e
   JSON-LD), sem API. Só páginas de produto, que o `robots.txt` permite; ritmo baixo e User-Agent
   honesto. **Pendente:** ler os termos de uso do Kabum.
3. **Mercado Livre fica para depois**: a API não entrega preços (busca e itens dão 403, o catálogo
   vem sem oferta) e as páginas de produto redirecionam para uma verificação de conta anti-robô.
   Só vale retomar com acesso oficial ou feed de parceiros.
4. **Agendamento** (entregue na sub-branch `catalogo-monitorado`). Jobs periódicos do Procrastinate por fonte, com frequência adaptativa por
   anúncio: GPUs e ofertas relâmpago a cada poucos minutos, itens estáveis algumas vezes por dia.
5. **Boas maneiras com as lojas.** Limite de requisições por loja, pausa entre páginas, retentativa
   com espera crescente e um único worker por loja (lock do Procrastinate).
6. **Testes** dos adapters com páginas e respostas reais salvas como fixtures.

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
3. **Casamento de anúncios**: anúncio → produto pelo MPN/EAN quando houver; produto → família pelos
   atributos extraídos. Fila de "não casados" para revisar manualmente.
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

## Fase 8: Expansão e SaaS

- **Mais lojas**: Mercado Livre (se houver acesso oficial), Pichau, Terabyte, Amazon e AliExpress (canal separado).
- **Mais canais**: Discord, WhatsApp e e-mail com resumo diário.
- **Alertas pessoais**: `/alerta rtx 4070 < 3500` no privado do bot.
- **SaaS**: cadastro de outros donos de canal, cada um com seus canais, regras e tag de afiliado;
  painel web; cobrança. A coleta e o histórico continuam globais e compartilhados.
- Revisar a marca (BuscaPC × Buscapé, INPI) antes de investir em divulgação.
