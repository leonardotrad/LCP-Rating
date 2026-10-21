# -*- coding: utf-8 -*-
r"""
lcp_painel.py - exporta num arquivo so tudo que o painel do LCP Rating precisa.

Rode SEMPRE depois do lcp_rating.py. Ele junta a classificacao com as
estatisticas de exibicao (HS%, KAST, uso de sniper) e grava:

    base\lcp_painel.csv

Mande apenas esse arquivo. Ele e pequeno e contem tudo.

ORDEM COMPLETA quando entrarem demos novas:
    py lcp_run.py
    py lcp_base.py
    py lcp_dano.py
    py lcp_rating.py
    py lcp_painel.py
"""

import csv
import os
import sys

# apelido com caractere especial nao pode derrubar o script no terminal do Windows
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


PASTA_BASE = "base"
PASTA_SAIDAS = "saidas"
ARQ_RATING = os.path.join(PASTA_BASE, "lcp_rating.csv")
ARQ_RP = os.path.join(PASTA_BASE, "lcp_round_player.csv")
ARQ_PART = os.path.join(PASTA_BASE, "lcp_partidas.csv")
ARQ_DATAS = os.path.join(PASTA_BASE, "lcp_datas.csv")
ARQ_OUT = os.path.join(PASTA_BASE, "lcp_painel.csv")

SNIPERS = ("awp", "ssg08", "scar20", "g3sg1")

csv.field_size_limit(10 ** 7)


def f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def bo(v):
    return 1 if str(v).strip().lower() in ("true", "1", "1.0") else 0


def ler(c):
    with open(c, "r", encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


def main():
    for arq in (ARQ_RATING, ARQ_RP):
        if not os.path.exists(arq):
            print("Nao encontrei " + arq)
            print("Rode antes:  py lcp_base.py  ->  py lcp_dano.py  ->  py lcp_rating.py")
            sys.exit(1)

    rating = ler(ARQ_RATING)
    rp = ler(ARQ_RP)

    # estatisticas de exibicao por steamid
    ag = {}
    for r in rp:
        s = r.get("steamid", "")
        a = ag.setdefault(s, {"rnd": 0, "k": 0.0, "hs": 0.0, "d": 0.0, "as": 0.0, "kast": 0.0})
        a["rnd"] += 1
        a["k"] += f(r.get("kills"))
        a["hs"] += f(r.get("headshots"))
        a["d"] += f(r.get("deaths"))
        a["as"] += f(r.get("assists"))
        # KAST = matou, deu assistencia, sobreviveu ou foi trocado. A coluna
        # "kast" da base marcava tambem quem so morreu (dava 92% no grupo).
        a["kast"] += 1 if (f(r.get("kills")) > 0 or f(r.get("assists")) > 0
                           or not bo(r.get("died")) or f(r.get("deaths_traded")) > 0) else 0

    # uso de sniper (com a mesma fusao de contas do lcp_contas.py)
    try:
        from lcp_contas import CONTAS
    except ImportError:
        CONTAS = {}
    snip = {}
    tot_k = {}
    if os.path.isdir(PASTA_SAIDAS):
        for cod in os.listdir(PASTA_SAIDAS):
            p = os.path.join(PASTA_SAIDAS, cod, "data_kills.csv")
            if not os.path.exists(p):
                continue
            for r in ler(p):
                s = r.get("attacker_steamid")
                if not s:
                    continue
                if r.get("attacker_team") and r.get("attacker_team") == r.get("victim_team"):
                    continue
                s = CONTAS.get(s, s)
                wp = (r.get("weapon") or "").lower()
                tot_k[s] = tot_k.get(s, 0) + 1
                if any(x in wp for x in SNIPERS):
                    snip[s] = snip.get(s, 0) + 1

    # totais da base
    nparts = len(ler(ARQ_PART)) if os.path.exists(ARQ_PART) else ""
    nrounds = len(set((r["partida"], r["event_index"]) for r in rp))
    datas = []
    if os.path.exists(ARQ_DATAS):
        for r in ler(ARQ_DATAS):
            for v in r.values():
                t = str(v or "")
                if len(t) >= 10 and t[:4].isdigit() and t[4] == "-" and t[7] == "-":
                    datas.append(t[:10])
    datas = sorted(set(datas))

    saida = []
    for r in rating:
        s = r.get("steamid", "")
        a = ag.get(s, {"rnd": 1, "k": 0.0, "hs": 0.0, "d": 0.0, "as": 0.0, "kast": 0.0})
        linha = dict(r)
        linha["HS_pct"] = round(100 * a["hs"] / a["k"], 1) if a["k"] > 0 else ""
        linha["KAST_pct"] = round(100 * a["kast"] / a["rnd"], 1) if a["rnd"] else ""
        linha["APR"] = round(a["as"] / a["rnd"], 2) if a["rnd"] else ""
        tk = tot_k.get(s, 0)
        linha["sniper_pct"] = round(100 * snip.get(s, 0) / tk, 1) if tk else ""
        linha["sniper_kills"] = snip.get(s, 0)
        saida.append(linha)

    campos = list(rating[0].keys()) + ["HS_pct", "KAST_pct", "APR", "sniper_pct", "sniper_kills"]
    with open(ARQ_OUT, "w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=campos)
        w.writeheader()
        w.writerows(saida)

    print("=" * 70)
    print("LCP PAINEL - dados exportados")
    print("=" * 70)
    print()
    print("Gravado: " + ARQ_OUT)
    print("   jogadores: %d" % len(saida))
    print("   partidas na base: %s" % nparts)
    print("   rounds na base: %d" % nrounds)
    if datas:
        print("   periodo: %s a %s" % (datas[0], datas[-1]))
    print()
    print("Mande esse arquivo (base\\lcp_painel.csv) para gerar o painel.")


if __name__ == "__main__":
    main()
