# LCP Rating - estado atual do projeto

Documento de referência. Atualizado em 20/10/2026.
Leia inteiro antes de mexer em qualquer coisa do projeto.

---

## 1. O que é

Sistema em Python que lê demos de CS2 e produz um rating de jogadores na
escala 1.00, igual à lógica do rating da HLTV, onde **1.00 é a média do grupo**.

Finalidade imediata: orientar a escolha dos capitães no draft da **Lan Chácara
Papetti, edição Halloween, em 24/10/2026**. Não é um número pós-campeonato.

O dono do projeto não programa. Explicações em português, simples, passo a passo.

---

## 2. Base de dados atual

| | |
|---|---|
| Partidas | 40 |
| Rounds | 883 |
| Kills | 6.220 |
| Jogadores na base | 43 |
| Classificados | 33 |
| Período | 12/08 a 21/10/2026 |

Números depois do pente fino de 20-21/10 (sem aquecimento, pós-round e rounds
fantasmas). Origem: 26 partidas da FACEIT e 14 de servidor de LAN do
campeonato anterior.
As duas origens foram testadas e são estatisticamente compatíveis.

Critério para entrar na classificação: **4 partidas e 60 rounds no mínimo**.

Cinco partidas não têm registro de `player_blind`, então as métricas que
dependem de flash são restritas às 35 partidas íntegras.

---

## 3. A esteira, na ordem correta

Esta é a única ordem válida.

### Quando entram demos novas

```
py lcp_faceit.py       (opcional) datas e apelidos atuais pela API da FACEIT
py lcp_run.py          processa cada demo (15 scripts, ~37s por demo, ~25 min no total)
py lcp_trades.py       oportunidades de troca, le posicoes das demos (~2s por demo)
py lcp_base.py         consolida tudo numa base só
py lcp_contas.py       funde contas diferentes da mesma pessoa
py lcp_dano.py         corrige a coluna de dano
py lcp_rating.py       calcula confiabilidade, pilares e a nota
py lcp_painel.py       exporta os dados do painel
py lcp_painel_html.py  gera o painel do draft (HTML, PNG e PDF) em base\painel\
py lcp_parametros.py   exporta os números brutos por métrica
```

`lcp_base.py` refaz a base do zero, então `lcp_contas.py` e `lcp_dano.py`
precisam rodar depois dele, sempre, nessa ordem.

`lcp_run.py` pula partida já processada. Para reprocessar, tire as pastas de
dentro de `saidas` (mover para `_descartados/` é o jeito seguro). Leva ~25
minutos: avise antes de rodar. Depois rode `py lcp_trades.py --tudo`.

Conferência depois de reprocessar: `py lcp_fronteira.py` (kills na borda dos
rounds).

### Quando a correção é só na cadeia de leverage

```
py lcp_releverage.py   refaz round_state_probe, kill_leverage_probe e
                       kill_leverage_model sem reler as demos (~3 min)
```
Depois siga de `lcp_base.py` em diante.

### Os 15 scripts por demo, em ordem

lcp_parser, round_results, round_player_stats, round_player_context,
trade_parser, trade_events_builder, round_player_trade_context,
round_player_impact_context, round_state_probe, kill_leverage_probe,
kill_leverage_model, clutch_parser, duels_parser, utility_parser,
damage_parser.

Módulos de apoio, chamados pelos parsers: `round_classifier.py` (rounds) e
`entry_engine.py` (entry, usado pelo duels_parser). **Não apagar.**

`entry_parser.py` saiu em 20/10: o duels_parser grava o mesmo entry_rounds.csv
e ninguém lia o data_entry.csv.

---

## 4. Os parâmetros e o que justifica cada um

Nenhum peso foi escolhido por opinião. Cada métrica tem um número de
**confiabilidade**, medido por divisão em metades: os rounds do jogador são
separados em pares e ímpares e verifica-se se uma metade prevê a outra
(Spearman com correção de Spearman-Brown).

Por que não estabilidade entre partidas: o formato é MIX, os times mudam a
cada partida, e esse teste pune métricas boas.

Leitura: forte ≥ 0,70 · boa ≥ 0,50 · fraca ≥ 0,30 · ruim abaixo disso.

### Pesos dos pilares

```python
PESOS_PILARES = {"Impact": 0.40, "Teamplay": 0.22, "Efficiency": 0.20, "Entry": 0.18}
```

**Os pesos oficiais ficam em `pesos/oficial.json`** (fonte da verdade desde
21/10; as tabelas abaixo podem estar defasadas). Para testar outra distribuição:
`py lcp_rating.py --pesos pesos/teste.json` e `py lcp_painel_html.py --teste`
(painel em `base/painel_teste/`). Depois rode `py lcp_rating.py` de novo para
voltar ao oficial.

Distribuição oficial de 21/10: Impact 40% (ADR 40, Kills/round 25, Multi-kill
20, Kills em desvantagem 15) · Teamplay 25% (Dano de utility 25, Assistências
25, Cegados 20, Contribuição de utility 10, Utility bem-sucedida 10, Taxa de
troca 10, Ser trocado 0) · Efficiency 10% (K/D 30, KAST 25, Sobrevivência 20,
Headshot 15, Morrer primeiro 10) · Entry 25% (First kills 50, Aproveitamento
40, Volume de entry de TR 5, Entry kill de TR 5).

Os pesos dos pilares e os pesos dentro de cada pilar são **escolha nossa**.
Confiabilidades abaixo: base de 21/10, depois do pente fino.
A confiabilidade só ajusta esses pesos para cima ou para baixo.

### Impact - 40% da nota

| Métrica | Peso no pilar | Confiabilidade |
|---|---|---|
| ADR | 40% | 0,781 |
| Kills por round | 25% | 0,810 |
| Multi-kill (rounds com 2+ kills) | 20% | 0,776 |
| Kills em desvantagem (parte das kills feitas com o time em menor número, inclui a que empata) | 15% | 0,570 |

Kills em desvantagem entrou em 20/10 no lugar do Leverage (ver 10.2).

### Teamplay - 22% da nota

| Métrica | Peso no pilar | Confiabilidade |
|---|---|---|
| Contribuição de utility (granadas por round, sem decoy) | 20% | 0,897 |
| Inimigos cegados por round | 15% | 0,905 (exige flash) |
| Utility bem-sucedida | 15% | 0,827 (exige flash) |
| Dano de utility por round | 15% | 0,624 |
| Ser trocado ao morrer | 15% | 0,781 |
| Assistências por round | 20% | 0,549 |

Utility bem-sucedida: flash que cegou inimigo, HE ou molotov que tirou vida de
inimigo, e **toda smoke** (a demo não diz se a smoke foi boa; decisão do dono
do projeto: smoke é utility importante e não pode punir). Decoy fica fora.

### Efficiency - 20% da nota

| Métrica | Peso no pilar | Confiabilidade |
|---|---|---|
| K/D | 15% | 0,821 |
| Headshot % | 25% | 0,746 |
| Sobrevivência | 25% | 0,728 |
| KAST (matou, assistência, sobreviveu ou foi trocado) | 20% | 0,560 |
| Morrer primeiro no round, **conta contra** | 15% | 0,656 |

K/D caiu de 35% para 15% em 20/10, por decisão do dono do projeto: matar não é
o único objetivo, e o K/D tem correlação 0,96 com Kills por round, que já está
no Impact. Morrer primeiro só no CT foi testado (0,426) e ficou pior que o geral.

### Entry - 18% da nota

| Métrica | Peso no pilar | Confiabilidade |
|---|---|---|
| Aproveitamento de entry | 40% | 0,606 |
| Volume de entry | 25% | 0,875 |
| Volume de entry de TR (primeiro duelo no TR ÷ rounds de TR) | 20% | 0,745 |
| Entry kill de TR (primeira kill no TR ÷ rounds de TR) | 15% | 0,677 |

O lado TR soma 35% do pilar, 5,6% da nota. Volume de entry conta a primeira
morte como participação; quem morre primeiro perde na Efficiency (acima), então
o efeito líquido de morrer primeiro é pequeno para quem entra muito.

### Clutch - FORA da nota (decisão de 21/10)
O LCP voltou a quatro pilares: Impact 40%, Teamplay 22%, Efficiency 20%,
Entry 18%. O clutch virou coluna informativa: **% de clutches convertidos**
(`Clutch_pct`, `Clutch_vencidos`, `Clutch_total` no lcp_rating.csv).

Só conta quem foi para cima (matou, morreu ou defusou) ou venceu, inclusive
escondido com a bomba explodindo. Não conta quem guardou a arma: não matou,
não morreu e perdeu, ou morreu sem matar ninguém longe da C4 plantada (fora
do raio de 1.750 unidades; 27 casos). Chance média de vencer na base (em
`base/lcp_clutch_chance.csv`): 1v1 54%, 1v2 24%, 1v3 7%, 1v4 2%, 1v5 0%.

Nenhuma versão de clutch passou no teste de confiabilidade (~20 clutches por
jogador). Reavaliar com ~70 partidas se quiser devolver à nota.

### Entry - first kill (21/10)
Entraram First kills por round (35%, 0,741); Aproveitamento 30%, Volume de
entry de TR 20%, Entry kill de TR 15%. Saiu o Volume de entry geral.

### Função (nomes do CS, 21/10)
AWPer (20%+ das kills de sniper) > Lurker (distância até o companheiro que
morre no TR 1 desvio acima da média, confiab. 0,837, e entra pouco no TR) >
Entry / Support (pilar Entry / Teamplay é o destaque do próprio perfil) >
Rifler (o resto). IGL fora: liderança não aparece na demo.

### Mecanismos de proteção

- **Encolhimento bayesiano**: quem tem pouca amostra é puxado para a média do
  grupo. `prior = 10 + 40 × (1 − confiabilidade)`. Métrica menos confiável
  encolhe mais. (`PRIOR_PISO = 10`, `PRIOR_BASE = 40`)
- **Peso efetivo**: dentro do pilar, o peso de cada métrica é multiplicado pela
  confiabilidade dela e renormalizado.
- **Escala**: `ESPALHAMENTO = 0,11`, o desvio padrão alvo da nota, igual ao
  do rating da HLTV.
- **Marca de amostra pequena**: menos de 6 partidas recebe aviso na tabela.
- A confiabilidade é medida dentro do `lcp_rating.py` a cada execução, então
  o modelo se recalibra sozinho quando entram demos novas.

### Escala dos pilares (corrigido em 20/10)

Pilares e nota usam **o mesmo fator de escala**, então a nota é exatamente a
média ponderada dos cinco pilares mostrados. Conferido nos 33 jogadores,
diferença máxima de 0,007, só arredondamento.

### Função do jogador

Compara o jogador com o **próprio perfil**, não com o grupo: o pilar mais
acima da média dos pilares dele, se a diferença for ≥ 0,22. Senão,
"Equilibrado". **Clutch não entra nessa conta**: não é função de time, e por ser
uma métrica só, com pouca amostra, encolhe muito para a média. Com ele, 11
jogadores, quase todos os mais fracos, viravam "Clutcher".

---

## 5. Métricas descartadas, e por quê

| Métrica | Motivo |
|---|---|
| Trade kills | Confiabilidade −0,063. Fazer a troca é oportunidade, não característica. *Ser trocado* é, e ficou. |
| Saldo de entry | 0,296. Substituído por Volume + Aproveitamento. |
| Conversão de clutch (binária) | 0,135. Ganhar ou perder o clutch mede mais sorte do que jogador. Saiu também da tabela em 20/10. |
| Regularidade entre partidas | A versão por variação deu 0,05. A versão por presença deu até 0,774, **mas tem correlação 0,95 com o ADR**. É o ADR com outro nome. |
| IGL | Liderança não aparece na demo. O número ranqueava alto quem não tem perfil de IGL. |

Regularidade continua no `lcp_rating.py` só como coluna informativa, fora da nota.

---

## 6. Bugs encontrados e corrigidos

Cada um com a evidência que provou o diagnóstico. Não reabra sem evidência nova.

### 6.1 ADR contava só o golpe letal
`round_player_stats.py` gravava em `damage` apenas o dano do tiro que matou.
A soma dos golpes letais reproduzia a coluna com 0,2% de erro.

Efeito: o ADR virou reflexo da contagem de kills, e o pilar mais pesado
passou a contar kill duas vezes. A perda era desigual: de 24% a 108% por jogador.

Correção: `lcp_dano.py` reconstrói a vida da vítima tiro por tiro a partir de
`saidas/<codigo>/data_damage.csv`, descarta dano em companheiro e sobrescreve
só a coluna `damage` de `base/lcp_round_player.csv`.
**Erro contra o placar oficial da FACEIT: de 42% para 0,6%.**

### 6.2 A kill que decide o round ia para o round seguinte
`round_classifier.py` publicava `tick_start` igual ao tick de `round_end` do
round anterior. Como os consumidores filtram por `tick >= tick_start`, a kill
final caía no round seguinte. Zero kills no tick de fim, 391 no tick de início,
e todas as 366 que tinham round anterior batiam exatamente com o fim dele.
324 vítimas apareciam mortas duas vezes no mesmo round.

Efeito: o entry ficava errado em 67% dos rounds. Multi-kill, clutch e leverage também.

Correção: o round publicado vai de `fim_anterior + 1` até `fim_real + 1`
(borda superior exclusiva). Conferido: 6403 = 6403 kills, zero divergência.

Resultado: Volume de entry de 0,664 para 0,855.

Nota: o round faca não é contabilizado. A kill de fronteira não era do round
faca: era uma por round, ~16 por partida.

### 6.3 clutch_parser quebrava com KeyError: 'player'
A lista de jogadores vinha do roster de um único round. Quando o parser não
devolvia nada naquele tick, a tabela saía sem colunas e o script estourava
numa função de impressão, depois do trabalho feito, perdendo os CSVs.

Correção: roster tentado em até dez rounds, com os nomes das mortes como último
recurso; tabela sempre com as colunas certas; **gravação antes das impressões**.
Validação com números fixos de uma partida antiga trocada por checagem interna.

### 6.4 kill_leverage_probe quebrava com IntCastingNaNError
`prepare()` converte com `errors="coerce"` e `add_exact_state()` fazia
`.astype(int)` direto.

Correção: `descartar_rounds_incompletos()` descarta o round inteiro quando falta
contagem de vivos, e avisa. Não preenche com zero: criaria um estado "0v0" falso.
Não descarta linha isolada: quebraria a validação de sequência do round.

### 6.5 round_state_probe não achava o time nas partidas de LAN
Nas partidas de LAN a coluna `team` vem **vazia** nos primeiros rounds. Nas da
FACEIT ela funciona em 100% dos rounds.

Correção: três caminhos, round, depois `event_index`, depois o time daquele
jogador naquele half, por maioria. O half de cada round é registrado **antes**
de qualquer descarte. Só preenche o que falta, nunca sobrescreve.

Resultado: Leverage de 0,313 para 0,725. Kills da cadeia de 5.900 para 6.298.

### 6.6 Utility bem-sucedida e dano de utility (corrigido em 20/10)
- Smoke e decoy (29% das granadas) nunca podiam dar certo, mas entravam na
  divisão. Agora a conta usa só flash, HE e molotov (`util_efetiva`).
- Flash que só cegou companheiro contava como sucesso (49% das cegadas são em
  companheiro).
- O sucesso era marcado por round: cegou alguém, todas as flashes do round
  contavam. Agora é granada por granada: cada cegada ou dano vai para a última
  granada do mesmo tipo jogada antes pelo jogador (casa 99,5% dos eventos).
  Função `sucesso_por_granada()` no `lcp_base.py`.
- Dano de utility somava armadura (30%) e dano em companheiro (2%). Agora só
  vida e só inimigo, a mesma regra do ADR. Média de 5,79 para 3,98 por round.

### 6.7 KAST do painel (corrigido em 20/10)
A coluna `kast` da base marca quem matou, deu assistência ou **morreu**: dava
92,5% no grupo. O `lcp_painel.py` agora calcula o KAST de verdade (matou,
assistência, sobreviveu ou foi trocado): de 54% a 80%, média 70%.
A coluna `kast` do round_player_stats continua errada, mas nada mais a usa
(o lcp_base.py recalcula a dele).

### 6.8 Pente fino de 20/10 - erros da cadeia por demo

Achados por regras que os números precisam obedecer (cada round com 10
jogadores, 5 por time, ninguém morre duas vezes no round, um entry por round,
vencedor do round no tick do round_end). Corrigidos e reprocessados.

1. **Aquecimento contado como round 1** (`round_classifier.py`). O round 1
   começava no tick 0 quando o aquecimento não tem round_end: até 107 kills
   num round 1 (fippi com 36 kills). Agora o round começa no
   `round_freeze_end`, nunca antes do "ao vivo".
2. **Kill do pós-round ia para o round seguinte** (`round_classifier.py`).
   125 kills: jogador morrendo duas vezes no round, entry falso (a primeira
   "kill" era a exit frag do round anterior), multi-kill e clutch errados.
   Com o início no freeze_end, kill de pós-round fica fora de qualquer round.
3. **Vencedor do round deslocado** (`round_results.py`). Casava pelo campo
   `round` do evento, que não zera após restart/aquecimento: em 37 de 39
   partidas cada round recebia o resultado do anterior. Agora casa pelo tick.
   Era a causa do modelo de vitória com 0,55 de acerto (10.1).
4. **Suicídio e kill em companheiro contavam como kill**
   (`round_player_stats.py`, `lcp_parser.py`). 88 suicídios e 29 kills em
   companheiro. O data_kills.csv ganhou `attacker_team` e `victim_team`.
5. **Entry** (`entry_engine.py`): valia a primeira morte de qualquer tipo; no
   suicídio o jogador ganhava entry kill e entry death. Agora é a primeira
   kill entre inimigos. Usava `<= tick_end` com borda exclusiva.
6. **Prorrogação ignorada** em `entry_engine.py`, `trade_parser.py` e
   `utility_parser.py` (só PISTOL e NORMAL). Os 29 rounds de prorrogação
   tinham zero entry, trade e granada, mas contavam na divisão "por round".
7. **Time do jogador lido no tick errado** (utility_parser,
   round_player_context): era lido no início do round antigo, logo depois do
   round_end anterior. No round 13 (troca de lado) os times saíam invertidos
   e no round 1 de LAN ninguém tinha time. Resolvido pelo item 1.
8. **Time na base** (`lcp_base.py`): vinha das kills e da maioria do half,
   com "times" de 3 a 8 jogadores. Agora vem do round_player_context.
9. **AWP% do painel** ignorava a fusão de contas e contava kill em companheiro.
10. **Scripts finais travavam** ao imprimir apelido com caractere especial no
    terminal do Windows (o lcp_base.py terminava com erro depois de gravar).
11. **lcp_run.py** copiava os CSVs de cada demo e deixava cópia na raiz, que
    ia para `csvs_anteriores/`. Foi assim que CSV de jogador foi para o
    GitHub. Agora move, e a raiz fica limpa.

### 6.9 Outros, já resolvidos antes
- `round_poststart` incompleto em 7 de 11 demos. `round_classifier.py` foi
  reescrito ancorado em `round_end`.
- Nome de demo fixo no código de 5 scripts.
- 150 kills fixas no código de `kill_leverage_probe` e `kill_leverage_model`.
- Definição de troca: o companheiro mata o assassino exato, em até 3 segundos.
- `is_round_winner` False em todas as linhas.
- Escala dos pilares diferente da escala da nota.

---

## 7. Identidade dos jogadores

Jogador é identificado por **steamid**, não por apelido. 16 jogadores da base
têm mais de um apelido.

`lcp_faceit.py` consulta a FACEIT e usa o apelido atual de cada conta.
A chave da API mora só no `.env`.

`lcp_contas.py` funde contas diferentes da mesma pessoa. A tabela fica em
`base/lcp_contas.csv` (colunas secundaria, principal, nome), fora do GitHub
porque tem steamid. Hoje: a conta do Flk^ é fundida na do Flkk.

Trava: se as duas contas aparecerem juntas na mesma partida, recusa a fusão.

Steamid diferente prova conta diferente, não pessoa diferente.

---

## 8. O campeonato

Draft em 24/10/2026. Vinte jogadores, quatro capitães.

Capitães: **Remember, Marlon, Stez1n, mmt**.

Dezoito dos vinte estão na base. **Hoycc** e **Rozinelz** não aparecem em
nenhuma demo e saem na tabela com traço. **gutex** não joga esta edição.

| Lista oficial | Base |
|---|---|
| Remember | Rememberr |
| Marlon | elbelano |
| mmt | m4mute |
| Kaiqqq | kaiqzikaaaaa |
| RustyGG | Rusty-GG |
| Flk^ | Flkk |
| squad | squaaaaad |
| fippi | fipibet |
| xitAL0. | xitAL0zin |
| blackw0w | blackwow |
| Taleszeraa | taleszera |
| tGk | _tGKzinn |
| t4m | WaspA_fps |
| Papettinho | Papettinhoo |
| Saci de patinete | SACI DE PATINETE |
| Jornassss | jornassss1 |

A classificação concorda quase inteiramente com os tiers da organização: os
quatro capitães nas quatro primeiras posições, o Tier A em 5º, os dois Tier E
fechando a tabela. Discordâncias: **fippi** (Tier B, 6º) e **RustyGG** (Tier B, 13º).

---

## 9. Entregas

**Desatualizadas desde 20/10** (feitas com quatro pilares; refazer com o Clutch):

- Painel do draft (PNG e PDF), 20 jogadores com nota, pilares e números brutos.
  Dados novos já em `base/lcp_painel.csv`.
- Documento de metodologia (PNG e PDF), para leigos. A versão já enviada aos
  organizadores diz que clutch não conta na nota: **avisar da mudança**.
- Tabela de parâmetros (PNG e PDF). Dados novos em `base/lcp_metricas.csv`
  (colunas `clutch_mortos_por_tentativa` e `clutch_tentativas`).

---

## 10. Em aberto

### 10.1 Modelo de probabilidade de vitória - RESOLVIDO em 21/10
O acerto de 0,55 vinha do vencedor do round deslocado (6.8, item 3). Depois da
correção: **0,775**. O Leverage continua fora da nota (10.2).

### 10.9 Baiter - FEITO em 21/10 (fora do LCP)
Coluna "Baiter" (0 a 100, posição no grupo) no lcp_rating.csv e no painel,
com três indicadores: Nunca abre no TR, Sempre sobra no TR e Não vingou.
"Bait recompensado" saiu: é trade kill (correlação −0,75 com Não vingou), o
oposto de baiter. Rótulos: 80+ Baiter raiz, 60+ Suspeito, 40+ Normal,
20+ Inocente, abaixo de 20 Kamikaze.

Testes:
Confiabilidade dos indicadores: Nunca abre no TR 0,787; Sempre sobra no TR
(último vivo) 0,644; Bait recompensado (vingou estando atrás) 0,524; Não vingou
(falha de troca perto) 0,516; Ficou pra trás no TR 0,242; Guardou (vivo em
round perdido sem dano) 0,209. Script de teste fora do projeto.

"Não vingou" passar no teste (0,516) significa que a taxa de troca com
oportunidade agora funciona, depois do pente fino: candidata ao Teamplay.

### 10.8 Clutch ficou fraco depois do pente fino (21/10) - DECIDIDO: 10%
Sem kill de aquecimento e de pós-round, a confiabilidade de "Adversários
mortos por tentativa real" caiu de 0,525 para **0,320** (fraca). Parte do
sinal anterior era kill que não acontecia em clutch de verdade. O sistema já
encolhe mais o pilar por isso, mas ele segue com 10% da nota. Opções: manter,
reduzir o peso ou voltar para quatro pilares.

### 10.2 Leverage - SUBSTITUÍDO em 20/10
Variava só 7% entre os jogadores. Trocado por Kills em desvantagem, que só
conta os vivos de cada lado e não depende do modelo. A coluna `leverage_medio`
continua na base, fora da nota.

### 10.7 Taxa de troca com oportunidade (testada em 20/10)
Definição do dono do projeto: companheiro morreu perto do jogador; se ele mata
o assassino em até 3s é troca, senão é falha. Se outro companheiro vingou
antes, não conta. `lcp_trades.py` lê as posições direto das demos.

Ruído em todos os recortes: raio de 500, 750, 1000, 1500 e sem raio
(−0,49 a 0,02); exigindo também o assassino a até 750/1000/1200 unidades do
jogador (−0,77 a −0,23). Com ~160 oportunidades e ~22 trocas por jogador, a
diferença entre jogadores some no acaso. Fica **fora da nota**, só como coluna
informativa (`taxa_troca_pct`, raio de 1000, `RAIO_TROCA` no `lcp_base.py`).
Reavaliar com mais partidas.

"Oportunidades de troca por round" é muito confiável (0,880), mas mede estar
perto de companheiro que morre, que não é claramente bom ou ruim.

### 10.6 Candidatos testados em 20/10
Mesma divisão em metades das outras métricas. "Repete" = maior correlação com
uma métrica que já está na nota.

| Candidato | Confiab. | Repete | Leitura |
|---|---|---|---|
| Assistências por round | 0,636 | 0,57 (Utility ok) | **adotado** no Teamplay |
| KAST real | 0,646 | 0,74 (K/D) | **adotado** na Efficiency |
| Kills em desvantagem / kills | 0,628 | 0,45 | **adotado** no Impact |
| Entry kill de TR | 0,526 | 0,72 (Volume de entry) | **adotado** no Entry |
| Volume de entry de TR | 0,743 | 0,74 | **adotado** no Entry |
| Flash assist por round | 0,690 | 0,85 (Cegados) | repete Cegados |
| Tempo de cegueira causado | 0,887 | 0,98 (Cegados) | é o Cegados com outro nome |
| Cegar companheiro por round | 0,901 | 0,95 (Cegados) | mede só quantas flashes joga |
| Cegadas em companheiro ÷ cegadas | 0,477 | 0,34 | fraca |
| Saldo de dano por round | 0,862 | 0,96 (ADR) | é o ADR com outro nome |
| Rounds com 3+ kills | 0,761 | 0,86 (K/D) | repete |
| Morrer primeiro por round | 0,535 | 0,67 (Volume de entry) | **adotado** na Efficiency, contra |
| Saldo de entry de TR | −0,029 | | ruído |
| Smokes por round | 0,930 | 0,81 (Contribuição) | repete; smoke entrou na Utility ok |
| Morte de entry trocada | −0,023 | | ruído, descartar |
| Aproveitamento de entry de TR | −0,193 | | ruído, descartar |
| Trade kills por round | 0,182 | | continua ruim |
| Uso de sniper | 0,875 | 0,36 | estilo, só informativo |

Colunas novas na base para isso: `util_efetiva`, `team_blinded`,
`flash_assists`, `sniper_kills`, `kills_desvantagem`, `kills_modelo`,
`trade_oport`, `trade_feitas` (`lcp_base.py`) e `damage_received` (`lcp_dano.py`).

### 10.3 Clutch voltou para a nota - FEITO em 20/10
Decisão do dono do projeto: definição F, quinto pilar, 10%. Conversão de clutch
retirada da tabela. Ver seção 4. Falta refazer as entregas da seção 9.

### 10.4 Cinco partidas sem registro de flash
Gravação incompleta, não é bug de parser.

### 10.5 Limpeza do projeto - FEITA em 20/10
46 scripts sem uso, `backup_original/`, `csvs_anteriores/`, `resgate/` e os
CSVs soltos na raiz foram movidos para `_descartados/` (fora do git). As
saídas antigas das demos estão em `_descartados/saidas_antigas/`. Conferir e
apagar a pasta quando quiser.

Ficam na raiz só a esteira (seção 3), `lcp_faceit.py`, `lcp_releverage.py` e
`lcp_fronteira.py`. `base.rar` e `saidas.rar` são backups antigos, não foram
mexidos.

Pendente: um arquivo único de configuração para os pesos.
