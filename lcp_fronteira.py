# -*- coding: utf-8 -*-
r"""
lcp_fronteira.py - confere se o parser esta perdendo kills na borda dos rounds.

O round_classifier conta as kills de cada round com a regra dele e grava esse
numero em round_results.csv, na coluna kill_events. O lcp_parser atribui as
kills aos rounds por conta propria e grava em data_kills.csv.

Se os dois numeros nao baterem, o parser esta perdendo ou duplicando kill na
fronteira dos rounds. Este script compara os dois, partida por partida.

Rode de dentro de C:\LCP-Rating:
    py lcp_fronteira.py
"""

import csv
import os
import sys

# apelido com caractere especial nao pode derrubar o script no terminal do Windows
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


PASTA_SAIDAS = "saidas"
OFICIAIS = {"PISTOL", "NORMAL", "OVERTIME"}

csv.field_size_limit(10 ** 7)


def f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def ler(c):
    with open(c, "r", encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


def main():
    if not os.path.isdir(PASTA_SAIDAS):
        print("Nao encontrei a pasta " + PASTA_SAIDAS)
        sys.exit(1)

    print("=" * 92)
    print("LCP FRONTEIRA - kills contadas pelo classificador x kills atribuidas pelo parser")
    print("=" * 92)
    print()
    print("%-46s %9s %9s %8s" % ("partida", "classif.", "parser", "difer."))
    print("-" * 92)

    tot_c = tot_p = 0
    tot_warm = 0
    tot_no_inicio = tot_no_fim = 0
    problemas = []

    for cod in sorted(os.listdir(PASTA_SAIDAS)):
        rr = os.path.join(PASTA_SAIDAS, cod, "round_results.csv")
        dk = os.path.join(PASTA_SAIDAS, cod, "data_kills.csv")
        if not (os.path.exists(rr) and os.path.exists(dk)):
            continue

        rounds = ler(rr)
        kills = ler(dk)

        oficiais = [r for r in rounds if r.get("round_type") in OFICIAIS]
        c = sum(int(f(r.get("kill_events"))) for r in oficiais)
        p = len(kills)

        tot_c += c
        tot_p += p

        for k in kills:
            t = f(k.get("tick"))
            ini = f(k.get("round_tick_start"))
            fim = f(k.get("round_tick_end"))
            if t == ini:
                tot_no_inicio += 1
            if t == fim - 1:
                tot_no_fim += 1

        warm = sum(int(f(r.get("kill_events"))) for r in rounds
                   if r.get("round_type") not in OFICIAIS)
        tot_warm += warm

        if c != p:
            problemas.append((cod, c, p, warm))
            print("%-46s %9d %9d %+8d" % (cod[:46], c, p, p - c))

    print("-" * 92)
    print("%-46s %9d %9d %+8d" % ("TOTAL", tot_c, tot_p, tot_p - tot_c))
    print()
    print("Partidas com divergencia: %d" % len(problemas))
    print("Kills que o classificador pos em round de aquecimento: %d" % tot_warm)
    print()
    print("Posicao das kills dentro das bordas publicadas pelo parser:")
    print("   no primeiro tick do round (tick == tick_start): %d" % tot_no_inicio)
    print("   no ultimo tick do round (tick == tick_end - 1): %d" % tot_no_fim)
    print()
    if tot_p == tot_c:
        print("OK: o parser atribuiu exatamente as kills que o classificador contou.")
    elif tot_p < tot_c:
        print("PROBLEMA: o parser esta PERDENDO %d kill(s) na fronteira." % (tot_c - tot_p))
    else:
        print("PROBLEMA: o parser esta DUPLICANDO %d kill(s) na fronteira." % (tot_p - tot_c))


if __name__ == "__main__":
    main()