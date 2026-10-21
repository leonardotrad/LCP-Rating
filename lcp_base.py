"""
lcp_base.py - consolida todas as partidas processadas em uma base unica.

Le a pasta saidas e gera, na pasta base:
  lcp_kills.csv         uma linha por kill, com leverage na escala global
  lcp_round_player.csv  uma linha por jogador por round, com todas as metricas
  lcp_partidas.csv      indice das partidas
  lcp_jogadores.csv     cadastro de jogadores por steamid

Rode sempre que processar partidas novas:  py lcp_base.py
"""

import os
import sys
import glob
import warnings

from pathlib import Path

import numpy as np
import pandas as pd

# apelido com caractere especial nao pode derrubar o script no terminal do Windows
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


warnings.filterwarnings("ignore")

PASTA_SAIDA = "saidas"
PASTA_BASE = "base"

TIPOS_OFICIAIS = ["PISTOL", "NORMAL", "OVERTIME"]

RAIO_TROCA = 1000      # unidades do jogo; 88% das trocas acontecem dentro disso
RAIO_C4 = 1750         # raio de dano da explosao da C4 no CS2


def ler(caminho):
    try:
        if not os.path.exists(caminho):
            return pd.DataFrame()
        if os.path.getsize(caminho) < 5:
            return pd.DataFrame()
        return pd.read_csv(caminho)
    except Exception:
        return pd.DataFrame()


def ajustar_modelo(X, y):
    """Regressao logistica por Newton-Raphson, sem dependencias extras."""
    b = np.zeros(X.shape[1])

    for _ in range(60):
        p = 1.0 / (1.0 + np.exp(-(X @ b)))
        W = p * (1.0 - p)
        H = X.T @ (X * W[:, None])
        g = X.T @ (y - p)
        passo = np.linalg.solve(H + 1e-8 * np.eye(len(b)), g)
        b = b + passo

        if np.max(np.abs(passo)) < 1e-10:
            break

    return b


def sucesso_por_granada(throws, cegadas, dano):
    """Marca, granada por granada, se ela funcionou.

    Flash: cegou pelo menos um inimigo. HE e molotov: tiraram vida de pelo
    menos um inimigo. Cada cegada e cada dano vao para a ultima granada do
    mesmo tipo que o jogador jogou antes, no mesmo round (casa 99,5% dos
    eventos). A demo nao diz se uma smoke foi boa, entao toda smoke conta
    como acerto (decisao do dono do projeto: smoke e utility importante).
    Decoy sai da conta.

    Antes: bastava o jogador ter cegado alguem, inclusive companheiro, em
    qualquer momento do round para todas as flashes dele no round contarem.
    """
    t = throws.copy()
    t["acertou"] = (t["utility_type"] == "SMOKE").astype(int)

    efeitos = []
    if not cegadas.empty:
        e = cegadas[["round_index", "thrower", "tick"]].rename(columns={"thrower": "player"})
        e["utility_type"] = "FLASH"
        efeitos.append(e)
    if not dano.empty:
        efeitos.append(dano[["round_index", "attacker", "tick", "utility_type"]]
                       .rename(columns={"attacker": "player"}))
    if not efeitos:
        return t

    efeitos = pd.concat(efeitos, ignore_index=True)
    chave = ["round_index", "player", "utility_type"]
    grupos = {k: g["tick"].values for k, g in efeitos.groupby(chave)}

    for k, g in t.groupby(chave):
        if k not in grupos:
            continue
        ticks = g["tick"].values
        ordem = np.argsort(ticks)
        ticks_ord = ticks[ordem]
        for x in grupos[k]:
            pos = np.searchsorted(ticks_ord, x, side="right") - 1
            if pos >= 0:
                t.loc[g.index[ordem[pos]], "acertou"] = 1

    return t


guardaram_c4_total = [0]


def coletar():
    situacoes = []
    kills = []
    rounds = []
    partidas = []
    identidades = []

    pastas = sorted(glob.glob(os.path.join(PASTA_SAIDA, "*")))

    for pasta in pastas:
        resumo = os.path.join(pasta, "resumo_partida.txt")

        if not os.path.exists(resumo):
            continue

        info = {}

        for linha in open(resumo, encoding="utf-8").read().strip().split("\n"):
            if "=" in linha:
                chave, valor = linha.split("=", 1)
                info[chave] = valor

        codigo = info.get("codigo", os.path.basename(pasta))
        tipo = info.get("tipo", "campeonato")
        mapa = info.get("mapa", "desconhecido")

        ident = ler(os.path.join(pasta, "player_identity.csv"))

        if ident.empty:
            print("  [PULADA] sem identidade: " + codigo[:30])
            continue

        ident["steamid"] = ident["steamid"].astype(str)
        ident = ident.drop_duplicates("player")
        ident["partida"] = codigo
        identidades.append(ident)

        mapa_nome = dict(zip(ident["player"], ident["steamid"]))

        lev = ler(os.path.join(pasta, "kill_win_probability_leverage.csv"))

        if not lev.empty:
            lev["partida"] = codigo
            lev["mapa"] = mapa
            lev["tipo"] = tipo
            kills.append(lev)

        rp = ler(os.path.join(pasta, "round_player_stats.csv"))

        if rp.empty:
            print("  [PULADA] sem round_player_stats: " + codigo[:30])
            continue

        rp = rp[rp["round_type"].isin(TIPOS_OFICIAIS)].copy()
        rp["steamid"] = rp["player"].map(mapa_nome).astype(str)
        rp["partida"] = codigo
        rp["mapa"] = mapa
        rp["tipo"] = tipo

        anexos = []

        duelos = ler(os.path.join(pasta, "duels_kills_raw.csv"))

        if not duelos.empty and "entry" in duelos.columns:
            ent = duelos[duelos["entry"] == True]

            anexos.append(
                ent.groupby(["round_index", "player"])
                .size().rename("entry_kills").reset_index()
            )

            anexos.append(
                ent.groupby(["round_index", "opponent"])
                .size().rename("entry_deaths").reset_index()
                .rename(columns={"opponent": "player"})
            )

        trades = ler(os.path.join(pasta, "trade_events.csv"))

        if not trades.empty:
            anexos.append(
                trades.groupby(["round_index", "trade_killer"])
                .size().rename("trade_kills").reset_index()
                .rename(columns={"trade_killer": "player"})
            )

            anexos.append(
                trades.groupby(["round_index", "player_traded"])
                .size().rename("deaths_traded").reset_index()
                .rename(columns={"player_traded": "player"})
            )

        suporte = ler(os.path.join(pasta, "utility_support.csv"))
        tem_flash = not suporte.empty
        companheiro = pd.DataFrame()

        if tem_flash:
            if "target_type" in suporte.columns:
                companheiro = suporte[suporte["target_type"] == "TEAM"]
                suporte = suporte[suporte["target_type"] != "TEAM"]

            anexos.append(
                suporte.groupby(["round_index", "thrower"])
                .agg(blind_time=("blind_duration", "sum"),
                     enemies_blinded=("victim", "size"))
                .reset_index().rename(columns={"thrower": "player"})
            )

            if not companheiro.empty:
                anexos.append(
                    companheiro.groupby(["round_index", "thrower"])
                    .size().rename("team_blinded").reset_index()
                    .rename(columns={"thrower": "player"})
                )

        # dano de utility: so em inimigo e so em vida, a mesma regra do ADR.
        # Antes somava armadura (30% do total) e dano em companheiro.
        dano_util = ler(os.path.join(pasta, "utility_damage.csv"))

        if not dano_util.empty:
            dano_util = dano_util[dano_util["attacker_team"] != dano_util["victim_team"]]
            dano_util = dano_util[dano_util["damage_health"] > 0]

            anexos.append(
                dano_util.groupby(["round_index", "attacker"])["damage_health"]
                .sum().rename("util_damage").reset_index()
                .rename(columns={"attacker": "player"})
            )

        throws = ler(os.path.join(pasta, "utility_throws.csv"))

        if not throws.empty:
            throws = sucesso_por_granada(throws, suporte if tem_flash else pd.DataFrame(),
                                         dano_util)
            # decoy nao conta como utility jogada
            throws = throws[throws["utility_type"] != "DECOY"]
            efetivas = throws["utility_type"].isin(["FLASH", "HE", "BURNER"])
            throws["util_efetiva"] = efetivas.astype(int)

            anexos.append(
                throws.groupby(["round_index", "player"])
                .agg(util_thrown=("weapon", "size"),
                     util_efetiva=("util_efetiva", "sum"),
                     util_ok=("acertou", "sum"))
                .reset_index()
            )

        # flash assist: a kill do companheiro saiu num inimigo que ele cegou
        eventos_util = ler(os.path.join(pasta, "utility_events.csv"))

        if not eventos_util.empty and "assistedflash" in eventos_util.columns:
            fa = eventos_util[
                (eventos_util["event_name"] == "player_death")
                & (eventos_util["assistedflash"].astype(str).str.lower() == "true")
                & eventos_util["assister_name"].notna()
            ]

            if not fa.empty:
                anexos.append(
                    fa.groupby(["round_index", "assister_name"])
                    .size().rename("flash_assists").reset_index()
                    .rename(columns={"assister_name": "player"})
                )

        clutch = ler(os.path.join(pasta, "clutch_debug.csv"))

        if not clutch.empty and "clutch_player" in clutch.columns:
            c = clutch.copy()
            c["clutch_situacao"] = 1
            c["clutch_vitoria"] = (c["result"] == "WIN").astype(int)
            c["clutch_adversarios"] = c["opponent_count"]

            # tentativa real = depois do inicio do clutch o jogador matou, morreu
            # ou defusou. Round em que ele so guardou nao conta. Mesma regra do
            # teste que mediu a confiabilidade dessa definicao (docs/ESTADO.md).
            dk = ler(os.path.join(pasta, "data_kills.csv"))
            pos = ler(os.path.join(pasta, "posicoes.csv"))
            c["clutch_tentativa"] = 0
            c["clutch_mortos"] = 0
            c["clutch_guardou_c4"] = 0

            if not dk.empty:
                faixas = (
                    dk.groupby("round_event_index")
                    .agg(ini=("round_tick_start", "first"), fim=("round_tick_end", "first"))
                )

                for i, linha in c.iterrows():
                    t = linha["clutch_tick"]
                    jog = str(linha["clutch_player"]).strip()
                    alvo = faixas[(faixas["ini"] <= t) & (t <= faixas["fim"])]

                    if alvo.empty:
                        continue

                    depois = dk[(dk["round_event_index"] == alvo.index[0]) & (dk["tick"] > t)]
                    inimigo = depois
                    if "attacker_team" in depois.columns:
                        inimigo = depois[depois["attacker_team"] != depois["victim_team"]]
                    matou = (inimigo["attacker_name"].astype(str).str.strip() == jog).sum()
                    morreu = (depois["victim_name"].astype(str).str.strip() == jog).any()
                    defusou = (str(linha["reason"]).strip() == "bomb_defused"
                               and str(linha["clutch_team"]).strip() == "CT")

                    # morreu sem matar ninguem, com a C4 plantada e longe dela:
                    # estava tentando guardar a arma (regra do dono do projeto).
                    guardou_c4 = False
                    if morreu and matou == 0 and not pos.empty:
                        ini, fim = alvo["ini"].iloc[0], alvo["fim"].iloc[0]
                        bombas = pos[(pos["evento"] == "bomba") & (pos["tick"] >= ini) & (pos["tick"] < fim)]
                        morte = pos[(pos["evento"] == "morte") & (pos["tick"] > t) & (pos["tick"] < fim)
                                    & (pos["jogador"].astype(str).str.strip() == jog)]
                        if not bombas.empty and not morte.empty:
                            b = bombas.iloc[0]
                            mo = morte.iloc[0]
                            if b["tick"] < mo["tick"]:
                                dist = ((mo["X"] - b["X"]) ** 2 + (mo["Y"] - b["Y"]) ** 2
                                        + (mo["Z"] - b["Z"]) ** 2) ** 0.5
                                guardou_c4 = dist > RAIO_C4

                    if guardou_c4:
                        c.at[i, "clutch_guardou_c4"] = 1
                    elif matou > 0 or morreu or defusou:
                        c.at[i, "clutch_tentativa"] = 1
                        c.at[i, "clutch_mortos"] = matou

            # clutch que conta (regra do dono do projeto): foi para cima ou
            # venceu. "Guardou a arma" (nao matou, nao morreu e perdeu) fica
            # de fora. A vitoria escondida (bomba explodiu) conta como vitoria.
            c["clutch_conta"] = ((c["clutch_tentativa"] == 1) | (c["clutch_vitoria"] == 1)).astype(int)
            guardaram_c4_total[0] += int(c["clutch_guardou_c4"].sum())
            for _, linha in c[c["clutch_conta"] == 1].iterrows():
                situacoes.append({
                    "partida": codigo, "round": int(linha["round_index"]) + 1,
                    "player": linha["clutch_player"],
                    "adv": int(min(max(linha["opponent_count"], 1), 5)),
                    "venceu": int(linha["clutch_vitoria"]),
                })

            anexos.append(
                c.groupby(["round_index", "clutch_player"])
                .agg(clutch_situacao=("clutch_situacao", "sum"),
                     clutch_vitoria=("clutch_vitoria", "sum"),
                     clutch_adversarios=("clutch_adversarios", "max"),
                     clutch_tentativa=("clutch_tentativa", "sum"),
                     clutch_mortos=("clutch_mortos", "sum"))
                .reset_index().rename(columns={"clutch_player": "player"})
            )

        for anexo in anexos:
            anexo["round"] = anexo["round_index"] + 1
            rp = rp.merge(
                anexo.drop(columns=["round_index"]),
                on=["round", "player"],
                how="left",
            )

        # kills de sniper por round, so informativo (estilo, nao qualidade)
        todas_kills = ler(os.path.join(pasta, "data_kills.csv"))

        if not todas_kills.empty and "weapon" in todas_kills.columns:
            sn = todas_kills[todas_kills["weapon"].astype(str).str.lower()
                             .str.contains("awp|ssg08|scar20|g3sg1")]
            sn = (sn.groupby(["round_event_index", "attacker_name"]).size()
                  .rename("sniper_kills").reset_index()
                  .rename(columns={"round_event_index": "event_index", "attacker_name": "player"}))
            rp = rp.merge(sn, on=["event_index", "player"], how="left")

        # oportunidades de troca (lcp_trades.py): companheiro morreu a ate
        # RAIO_TROCA unidades dele. "outro_trocou" nao conta nem a favor nem contra.
        oport = ler(os.path.join(pasta, "trade_oportunidades.csv"))

        if not oport.empty:
            # distancia ate cada companheiro que morre (sem raio): mede quem
            # joga longe do time. Usada para a funcao Lurker, so no lado TR.
            longe = (oport.groupby(["round_event_index", "jogador"])["distancia"]
                     .agg(lurk_soma="sum", lurk_n="size").reset_index()
                     .rename(columns={"round_event_index": "event_index", "jogador": "player"}))
            rp = rp.merge(longe, on=["event_index", "player"], how="left")

            oport = oport[(oport["distancia"] <= RAIO_TROCA) & (oport["resultado"] != "outro_trocou")]
            oport["feita"] = (oport["resultado"] == "troca").astype(int)
            oport = (oport.groupby(["round_event_index", "jogador"])
                     .agg(trade_oport=("feita", "size"), trade_feitas=("feita", "sum"))
                     .reset_index()
                     .rename(columns={"round_event_index": "event_index", "jogador": "player"}))
            rp = rp.merge(oport, on=["event_index", "player"], how="left")

        # time de cada jogador no round, lido no fim do freeze time
        # (round_player_context.py). E a fonte principal do time.
        ctx = ler(os.path.join(pasta, "round_player_context.csv"))

        if not ctx.empty and "team" in ctx.columns:
            ctx = ctx[["round", "player", "team"]].drop_duplicates(["round", "player"])
            rp = rp.merge(ctx.rename(columns={"team": "time_ctx"}), on=["round", "player"], how="left")

        rp["tem_flash"] = tem_flash
        rounds.append(rp)

        partidas.append({
            "partida": codigo,
            "tipo": tipo,
            "mapa": mapa,
            "rounds": rp["round"].nunique(),
            "jogadores": rp["steamid"].nunique(),
            "kills": len(lev),
            "tem_flash": tem_flash,
        })

    return kills, rounds, partidas, identidades, situacoes


def main():
    print("=" * 70)
    print("LCP BASE - consolidacao das partidas")
    print("=" * 70)
    print()

    kills, rounds, partidas, identidades, situacoes = coletar()
    guardaram_c4 = guardaram_c4_total[0]

    if not rounds:
        print("Nenhuma partida encontrada em " + PASTA_SAIDA)
        return

    os.makedirs(PASTA_BASE, exist_ok=True)

    k = pd.concat(kills, ignore_index=True)
    m = pd.concat(rounds, ignore_index=True)
    p = pd.DataFrame(partidas)
    ident = pd.concat(identidades, ignore_index=True)

    # ---- modelo unico de probabilidade de vitoria ----
    X = np.column_stack([
        np.ones(len(k)),
        k["own_alive_before"].astype(float),
        k["enemy_alive_before"].astype(float),
    ])
    y = k["killer_team_won"].astype(float).values

    beta = ajustar_modelo(X, y)

    def prob(own, inimigo):
        z = beta[0] + beta[1] * own + beta[2] * inimigo
        return 1.0 / (1.0 + np.exp(-z))

    k["prob_antes"] = prob(k["own_alive_before"], k["enemy_alive_before"])
    k["prob_depois"] = prob(k["own_alive_after"], k["enemy_alive_after"])
    k["leverage"] = k["prob_depois"] - k["prob_antes"]

    acerto = ((1.0 / (1.0 + np.exp(-(X @ beta))) > 0.5).astype(float) == y).mean()

    print("Modelo global de probabilidade de vitoria")
    print("  intercepto      " + str(round(beta[0], 4)))
    print("  vivos proprios  " + str(round(beta[1], 4)))
    print("  vivos inimigos  " + str(round(beta[2], 4)))
    print("  kills usadas    " + str(len(k)))
    print("  acerto          " + str(round(acerto, 3)))
    print()

    # ---- identidade e time ----
    idmap = ident.drop_duplicates(["partida", "player"])[["partida", "player", "steamid"]]
    idmap["steamid"] = idmap["steamid"].astype(str)

    ka = k.merge(
        idmap, left_on=["partida", "attacker"], right_on=["partida", "player"], how="left"
    )

    # kill em desvantagem: na hora da kill o time dele tinha menos vivos que o
    # adversario. Inclui a kill que empata (4v5 -> 4v4). Nao depende do modelo
    # de probabilidade, so da contagem de vivos.
    ka["kill_desvantagem"] = (
        ka["own_alive_before"].astype(float) < ka["enemy_alive_before"].astype(float)
    ).astype(int)

    lev_round = (
        ka.groupby(["steamid", "partida", "round"])
        .agg(leverage_medio=("leverage", "mean"),
             kills_desvantagem=("kill_desvantagem", "sum"),
             kills_modelo=("kill_desvantagem", "size"))
        .reset_index()
    )
    lev_round["steamid"] = lev_round["steamid"].astype(str)

    m["steamid"] = m["steamid"].astype(str)
    m = m.merge(lev_round, on=["steamid", "partida", "round"], how="left")

    lado_a = k[["partida", "round", "attacker", "attacker_team"]].rename(
        columns={"attacker": "player", "attacker_team": "time"})
    lado_b = k[["partida", "round", "victim", "victim_team"]].rename(
        columns={"victim": "player", "victim_team": "time"})

    lados = pd.concat([lado_a, lado_b]).dropna().drop_duplicates(
        ["partida", "round", "player"])

    m = m.merge(lados, on=["partida", "round", "player"], how="left")

    # o time lido no fim do freeze vale mais que o deduzido pelas kills; as
    # kills e a maioria do half so cobrem o que faltar. Antes era o contrario
    # e havia "times" de 3 a 8 jogadores no mesmo round.
    if "time_ctx" in m.columns:
        m["time"] = m["time_ctx"].fillna(m["time"])
        m = m.drop(columns=["time_ctx"])

    preenche = (
        m.dropna(subset=["time"])
        .groupby(["partida", "half", "player"])["time"]
        .agg(lambda s: s.mode().iloc[0]).rename("time_half").reset_index()
    )

    m = m.merge(preenche, on=["partida", "half", "player"], how="left")
    m["time"] = m["time"].fillna(m["time_half"])
    m = m.drop(columns=["time_half"])
    m["venceu_round"] = (m["time"] == m["winner"])

    # ---- clutch na regra do dono do projeto ----
    # Cada clutch que conta vale (venceu - chance de vencer aquela situacao),
    # com a chance medida na propria base: 1v1 ~0,5, 1v2 ~0,23, 1v3 ~0,06...
    # Ganhar 1v3 vale ~+0,94; perder 1v1 vale ~-0,5; perder 1v4 quase nao pesa.
    if situacoes:
        sit = pd.DataFrame(situacoes)
        print("Clutches que contam: %d  (morreu guardando longe da C4: %d)"
              % (len(sit), guardaram_c4))
        chance = sit.groupby("adv")["venceu"].mean()
        sit["esperado"] = sit["adv"].map(chance)
        print("Chance de vencer o clutch: " + ", ".join(
            "1v%d %.2f" % (k, v) for k, v in chance.items()))
        chance.rename("chance").rename_axis("adversarios").reset_index().to_csv(
            os.path.join(PASTA_BASE, "lcp_clutch_chance.csv"), index=False)
        sit = (sit.groupby(["partida", "round", "player"])
               .agg(clutch_conta=("venceu", "size"), clutch_venceu=("venceu", "sum"),
                    clutch_esperado=("esperado", "sum"))
               .reset_index())
        m = m.merge(sit, on=["partida", "round", "player"], how="left")

    # ---- limpeza e derivadas ----
    zerar = ["entry_kills", "entry_deaths", "trade_kills", "deaths_traded",
             "util_thrown", "util_ok", "blind_time", "enemies_blinded", "util_damage",
             "clutch_situacao", "clutch_vitoria", "clutch_adversarios",
             "clutch_tentativa", "clutch_mortos", "clutch_conta", "clutch_venceu",
             "clutch_esperado",
             "util_efetiva", "team_blinded", "flash_assists", "sniper_kills",
             "kills_desvantagem", "kills_modelo", "trade_oport", "trade_feitas",
             "lurk_soma", "lurk_n"]

    for coluna in zerar:
        if coluna not in m.columns:
            m[coluna] = np.nan
        m[coluna] = m[coluna].fillna(0)

    m.loc[~m["tem_flash"], ["blind_time", "enemies_blinded", "team_blinded"]] = np.nan

    m["entry_attempts"] = m["entry_kills"] + m["entry_deaths"]

    m["kast"] = (
        (m["kills"] > 0) | (m["assists"] > 0) |
        (m["deaths"] == 0) | (m["deaths_traded"] > 0)
    ).astype(float)

    # ---- cadastro de jogadores ----
    jog = m.groupby("steamid").agg(
        apelido=("player", lambda s: s.value_counts().index[0]),
        partidas=("partida", "nunique"),
        rounds=("round", "size"),
        adr=("damage", "mean"),
        kr=("kills", "mean"),
    ).reset_index().sort_values("rounds", ascending=False)

    outros = (
        m.groupby("steamid")["player"].agg(lambda s: sorted(set(s)))
        .rename("apelidos").reset_index()
    )

    jog = jog.merge(outros, on="steamid", how="left")

    arquivo_apelidos = Path(PASTA_BASE) / "lcp_apelidos.csv"

    if arquivo_apelidos.exists():
        atuais = pd.read_csv(arquivo_apelidos, dtype={"steamid": str})
        atuais = atuais.dropna(subset=["steamid", "apelido"])
        atuais = atuais.drop_duplicates("steamid")
        mapa_atual = dict(zip(atuais["steamid"], atuais["apelido"]))

        jog["apelido_nas_demos"] = jog["apelido"]
        jog["apelido"] = jog["steamid"].map(mapa_atual).fillna(jog["apelido"])

        trocados = int((jog["apelido"] != jog["apelido_nas_demos"]).sum())
        print("Apelidos atualizados pela FACEIT: " + str(trocados))
    else:
        print("Sem base/lcp_apelidos.csv - rode lcp_faceit.py para atualizar apelidos.")


    # ---- gravacao ----
    k.to_csv(os.path.join(PASTA_BASE, "lcp_kills.csv"), index=False)
    m.to_csv(os.path.join(PASTA_BASE, "lcp_round_player.csv"), index=False)
    p.to_csv(os.path.join(PASTA_BASE, "lcp_partidas.csv"), index=False)
    jog.to_csv(os.path.join(PASTA_BASE, "lcp_jogadores.csv"), index=False)

    print("Partidas: " + str(len(p)) +
          "  (campeonato " + str((p["tipo"] == "campeonato").sum()) +
          ", calibracao " + str((p["tipo"] == "calibracao").sum()) + ")")
    print("Rounds: " + str(int(p["rounds"].sum())) + "  |  Kills: " + str(len(k)))
    print("Jogadores: " + str(len(jog)))
    print("Linhas jogador x round: " + str(len(m)))
    print("Cobertura de time: " + str(round(m["time"].notna().mean(), 3)))
    print("Taxa de vitoria (esperado ~0,5): " + str(round(m["venceu_round"].mean(), 3)))

    sem_flash = p[~p["tem_flash"]]

    if len(sem_flash):
        print()
        print("ATENCAO: " + str(len(sem_flash)) + " partidas sem dados de flash:")
        for _, linha in sem_flash.iterrows():
            print("   " + linha["mapa"] + "  " + linha["partida"][:30])

    duplicados = jog[jog["apelidos"].apply(len) > 1]

    if len(duplicados):
        print()
        print("Jogadores com mais de um apelido:")
        for _, linha in duplicados.iterrows():
            print("   " + linha["steamid"] + ": " + ", ".join(linha["apelidos"]))

    print()
    print("Arquivos gravados em: " + os.path.abspath(PASTA_BASE))


if __name__ == "__main__":
    main()