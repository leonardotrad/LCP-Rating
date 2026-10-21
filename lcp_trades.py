# -*- coding: utf-8 -*-
r"""
lcp_trades.py - oportunidades de troca (trade) de cada jogador.

O QUE E UMA OPORTUNIDADE
Um companheiro morreu e o jogador estava vivo, perto dele. Grava a distancia
ate o companheiro (distancia) e ate o assassino (dist_matador). A partir dai:
  troca         o jogador matou quem matou o companheiro em ate 3 segundos
  falha         nao matou: o assassino seguiu vivo ou matou ele tambem
  outro_trocou  outro companheiro vingou antes; nao conta nem a favor nem contra

A distancia fica gravada em cada linha, entao o raio de "perto" e decidido no
lcp_base.py (RAIO_TROCA), sem precisar ler as demos de novo.

Le as posicoes dos jogadores direto da demo, so nos ticks das mortes
(~2 segundos por demo), e as mortes oficiais de saidas\<codigo>\data_kills.csv.

Gera: saidas\<codigo>\trade_oportunidades.csv

Gera tambem posicoes.csv (na mesma pasta), com a posicao de cada morte e
de cada bomba plantada. O lcp_base.py usa para o clutch: quem morre longe da
C4 plantada, sem ter matado ninguem, estava tentando guardar a arma.

Rode depois do lcp_run.py e antes do lcp_base.py:
    py lcp_trades.py
Pula partida ja feita. Para refazer tudo:  py lcp_trades.py --tudo
"""

import math
import os
import sys
from pathlib import Path

import pandas as pd
from demoparser2 import DemoParser

# apelido com caractere especial nao pode derrubar o script no terminal do Windows
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


PASTAS_DEMOS = [Path("fila") / "campeonato", Path("fila") / "calibracao", Path("demos")]
PASTA_SAIDA = Path("saidas")
ARQ = "trade_oportunidades.csv"
ARQ_POS = "posicoes.csv"

TICKRATE = 64.0        # o mesmo do trade_parser.py
JANELA = 3.0           # segundos para vingar


def oportunidades(demo, kills):
    p = DemoParser(str(demo))
    pos = p.parse_ticks(["X", "Y", "Z", "is_alive", "team_num"],
                        ticks=sorted(kills["tick"].astype(int).unique().tolist()))
    pos = pos.drop_duplicates(["tick", "name"])
    por_tick = {t: g.set_index("name") for t, g in pos.groupby("tick")}

    janela = JANELA * TICKRATE
    linhas = []

    for ri, mortes in kills.groupby("round_event_index"):
        mortes = mortes.sort_values("tick")

        for _, m in mortes.iterrows():
            t = int(m["tick"])
            vit = str(m["victim_name"])
            mat = str(m["attacker_name"])
            if t not in por_tick or vit not in por_tick[t].index or mat in ("", "nan", vit):
                continue

            agora = por_tick[t]
            v = agora.loc[vit]
            if mat in agora.index and agora.loc[mat, "team_num"] == v["team_num"]:
                continue  # morte por companheiro, nao tem troca

            # o que aconteceu com o assassino nos 3 segundos seguintes
            depois = mortes[(mortes["tick"] > t) & (mortes["tick"] <= t + janela)]
            vinganca = depois[depois["victim_name"].astype(str) == mat]
            vingador = str(vinganca.iloc[0]["attacker_name"]) if not vinganca.empty else None
            atraso = (int(vinganca.iloc[0]["tick"]) - t) / TICKRATE if not vinganca.empty else ""

            for nome, j in agora.iterrows():
                if nome == vit or j["team_num"] != v["team_num"] or not bool(j["is_alive"]):
                    continue

                dist = math.sqrt((j["X"] - v["X"]) ** 2 + (j["Y"] - v["Y"]) ** 2
                                 + (j["Z"] - v["Z"]) ** 2)
                dist_mat = ""
                if mat in agora.index:
                    e = agora.loc[mat]
                    dist_mat = round(math.sqrt((j["X"] - e["X"]) ** 2 + (j["Y"] - e["Y"]) ** 2
                                               + (j["Z"] - e["Z"]) ** 2))

                if vingador == nome:
                    res = "troca"
                elif vingador is not None:
                    res = "outro_trocou"
                else:
                    res = "falha"

                linhas.append({
                    "round_event_index": ri, "tick": t, "jogador": nome,
                    "vitima": vit, "matador": mat, "distancia": round(dist),
                    "dist_matador": dist_mat,
                    "resultado": res, "atraso": atraso,
                })

    return pd.DataFrame(linhas, columns=["round_event_index", "tick", "jogador", "vitima",
                                         "matador", "distancia", "dist_matador", "resultado",
                                         "atraso"])


def posicoes(demo):
    """Posicao (X, Y, Z) de cada morte e de cada bomba plantada."""
    p = DemoParser(str(demo))
    linhas = []
    for evento, nome in (("player_death", "morte"), ("bomb_planted", "bomba")):
        try:
            e = p.parse_event(evento, player=["X", "Y", "Z"])
        except Exception:
            continue
        if e is None or len(e) == 0:
            continue
        for _, r in e.iterrows():
            linhas.append({"evento": nome, "tick": int(r["tick"]),
                           "jogador": r.get("user_name"),
                           "X": r.get("user_X"), "Y": r.get("user_Y"), "Z": r.get("user_Z")})
    return pd.DataFrame(linhas, columns=["evento", "tick", "jogador", "X", "Y", "Z"])


def main():
    tudo = "--tudo" in sys.argv
    demos = {}
    for pasta in PASTAS_DEMOS:
        for d in pasta.glob("*.dem"):
            demos[d.stem] = d

    print("=" * 70)
    print("LCP TRADES - oportunidades de troca")
    print("=" * 70)

    feitas = puladas = 0
    sem_demo = []
    for pasta in sorted(PASTA_SAIDA.iterdir()):
        if not pasta.is_dir():
            continue
        destino = pasta / ARQ
        if destino.exists() and (pasta / ARQ_POS).exists() and not tudo:
            puladas += 1
            continue
        if pasta.name not in demos:
            sem_demo.append(pasta.name)
            continue
        arq_k = pasta / "data_kills.csv"
        if not arq_k.exists():
            continue

        kills = pd.read_csv(arq_k)
        tab = oportunidades(demos[pasta.name], kills)
        tab.to_csv(destino, index=False)
        posicoes(demos[pasta.name]).to_csv(pasta / ARQ_POS, index=False)
        feitas += 1
        r = tab["resultado"].value_counts().to_dict()
        print("  %-45s troca %4d  falha %4d  outro %4d" % (
            pasta.name[:45], r.get("troca", 0), r.get("falha", 0), r.get("outro_trocou", 0)))

    print()
    print("Feitas: %d   ja existiam: %d" % (feitas, puladas))
    if sem_demo:
        print("Sem demo encontrada (mantidas sem oportunidades):")
        for c in sem_demo:
            print("   " + c)


if __name__ == "__main__":
    main()
