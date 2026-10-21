# -*- coding: utf-8 -*-
r"""
lcp_parametros.py - exporta os numeros brutos de cada jogador em cada metrica.

O painel mostra os cinco pilares ja calculados. Este script mostra o que
tem por tras: os 20 numeros que alimentam os pilares, exatamente com as
mesmas contas que o lcp_rating.py usa.

Serve para conferencia e para explicar a tabela: da para olhar um jogador e
ver de onde veio cada pilar dele.


Gera: base\lcp_metricas.csv

Rode depois do lcp_rating.py:
    py lcp_parametros.py
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
ARQ_RP = os.path.join(PASTA_BASE, "lcp_round_player.csv")
ARQ_AP = os.path.join(PASTA_BASE, "lcp_apelidos.csv")
ARQ_RT = os.path.join(PASTA_BASE, "lcp_rating.csv")
ARQ_OUT = os.path.join(PASTA_BASE, "lcp_metricas.csv")

MIN_PARTIDAS = 4
MIN_ROUNDS = 60

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


def soma(rs, col):
    return sum(f(r.get(col)) for r in rs)


def div(a, b, casas=2):
    return round(a / b, casas) if b else ""


def main():
    if not os.path.exists(ARQ_RP):
        print("Nao encontrei " + ARQ_RP)
        print("Rode antes:  py lcp_base.py -> py lcp_contas.py -> py lcp_dano.py")
        sys.exit(1)

    linhas = ler(ARQ_RP)

    apelidos = {}
    if os.path.exists(ARQ_AP):
        for r in ler(ARQ_AP):
            if r.get("steamid"):
                apelidos[r["steamid"]] = r.get("apelido") or ""

    posicao = {}
    if os.path.exists(ARQ_RT):
        for r in ler(ARQ_RT):
            if r.get("steamid"):
                posicao[r["steamid"]] = (f(r.get("posicao")), r.get("LCP", ""))

    por_jog = {}
    por_part = {}
    nome_demo = {}
    for r in linhas:
        s = r.get("steamid", "")
        por_jog.setdefault(s, []).append(r)
        por_part.setdefault(s, set()).add(r.get("partida"))
        nome_demo.setdefault(s, r.get("player", ""))

    campos = [
        "posicao", "apelido", "steamid", "LCP",
        "ADR", "kills_por_round", "multi_kill_pct", "kills_desvantagem_pct",
        "utility_por_round", "cegados_por_round", "utility_ok_pct",
        "dano_utility_por_round", "trocado_ao_morrer_pct", "assistencias_por_round", "taxa_troca_pct_nota",
        "KD", "headshot_pct", "sobrevivencia_pct", "kast_pct", "morrer_primeiro_por_round",
        "first_kills_por_round", "entry_aproveitamento_pct", "entry_por_round", "entry_tr_por_round_tr",
        "entry_kill_tr_por_round",
        "taxa_troca_pct", "oportunidades_troca",
        "clutch_pct", "clutch_vencidos", "clutch_contados",
        "rounds", "partidas", "rounds_com_flash",
    ]

    saida = []
    for s, rs in por_jog.items():
        if len(rs) < MIN_ROUNDS or len(por_part[s]) < MIN_PARTIDAS:
            continue

        fl = [r for r in rs if bo(r.get("tem_flash"))]
        n = len(rs)
        mortes = soma(rs, "deaths")
        kills = soma(rs, "kills")
        jogadas = soma(rs, "util_thrown")
        tent = soma(rs, "entry_attempts")
        lado_t = [r for r in rs if r.get("time") == "T"]

        pos, lcp = posicao.get(s, ("", ""))

        saida.append({
            "posicao": int(pos) if pos else "",
            "apelido": apelidos.get(s) or nome_demo.get(s, s),
            "steamid": s,
            "LCP": lcp,
            "ADR": div(soma(rs, "damage"), n, 1),
            "kills_por_round": div(kills, n),
            "multi_kill_pct": div(100 * sum(bo(r.get("multi_kill")) for r in rs), n, 1),
            "kills_desvantagem_pct": div(100 * soma(rs, "kills_desvantagem"), soma(rs, "kills_modelo"), 1),
            "utility_por_round": div(jogadas, n),
            "cegados_por_round": div(soma(fl, "enemies_blinded"), len(fl)) if fl else "",
            "utility_ok_pct": div(100 * soma(fl, "util_ok"), soma(fl, "util_thrown"), 1) if fl else "",
            "dano_utility_por_round": div(soma(rs, "util_damage"), n, 1),
            "trocado_ao_morrer_pct": div(100 * soma(rs, "deaths_traded"), mortes, 1),
            "assistencias_por_round": div(soma(rs, "assists"), n),
            "taxa_troca_pct_nota": div(100 * soma(rs, "trade_feitas"), soma(rs, "trade_oport"), 1),
            "kast_pct": div(100 * sum(1 for r in rs if f(r.get("kills")) > 0 or f(r.get("assists")) > 0
                                      or not bo(r.get("died")) or f(r.get("deaths_traded")) > 0), n, 1),
            "morrer_primeiro_por_round": div(soma(rs, "entry_deaths"), n),
            "entry_tr_por_round_tr": div(soma(lado_t, "entry_attempts"), len(lado_t)),
            "taxa_troca_pct": div(100 * soma(rs, "trade_feitas"), soma(rs, "trade_oport"), 1),
            "oportunidades_troca": int(soma(rs, "trade_oport")),
            "KD": div(kills, mortes),
            "headshot_pct": div(100 * soma(rs, "headshots"), kills, 1),
            "sobrevivencia_pct": div(100 * (n - sum(bo(r.get("died")) for r in rs)), n, 1),
            "entry_aproveitamento_pct": div(100 * soma(rs, "entry_kills"), tent, 1),
            "first_kills_por_round": div(soma(rs, "entry_kills"), n),
            "entry_por_round": div(tent, n),
            "entry_kill_tr_por_round": div(soma(lado_t, "entry_kills"), len(lado_t)),
            "clutch_pct": div(100 * soma(rs, "clutch_venceu"), soma(rs, "clutch_conta"), 1),
            "clutch_vencidos": int(soma(rs, "clutch_venceu")),
            "clutch_contados": int(soma(rs, "clutch_conta")),
            "rounds": n,
            "partidas": len(por_part[s]),
            "rounds_com_flash": len(fl),
        })

    saida.sort(key=lambda r: (r["posicao"] if r["posicao"] != "" else 999))

    with open(ARQ_OUT, "w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=campos)
        w.writeheader()
        w.writerows(saida)

    print("=" * 70)
    print("LCP PARAMETROS - numeros brutos por jogador")
    print("=" * 70)
    print()
    print("Gravado: " + ARQ_OUT)
    print("   jogadores: %d" % len(saida))
    print()
    print("Mande esse arquivo para gerar a tabela de parametros.")


if __name__ == "__main__":
    main()