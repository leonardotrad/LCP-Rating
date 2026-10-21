# -*- coding: utf-8 -*-
r"""
lcp_contas.py - junta contas diferentes da MESMA pessoa.

POR QUE ISSO EXISTE
O sistema identifica jogador por steamid, porque apelido muda. Mas uma
pessoa pode ter mais de uma conta Steam. Nesse caso o steamid tambem muda,
e o jogador aparece dividido em dois na classificacao, cada metade com
menos partidas e nota mais encolhida.

Este script junta as contas secundarias na conta principal, para que todas
as estatisticas saiam somadas sob um unico nome.

COMO ADICIONAR UMA PESSOA NOVA
Acrescente uma linha em base/lcp_contas.csv (secundaria, principal, nome).
Os steamid aparecem na lista "Jogadores com mais de um apelido" que o
lcp_base.py imprime, e tambem na coluna steamid de base\lcp_painel.csv.

ORDEM DE EXECUCAO (o lcp_base.py refaz a base, entao rode sempre depois dele)
    py lcp_run.py
    py lcp_base.py
    py lcp_contas.py     <-- aqui
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

# A tabela de fusao fica em base/lcp_contas.csv (fora do GitHub, porque tem
# steamid). Colunas: secundaria, principal, nome
#   secundaria  conta a ser absorvida
#   principal   conta que fica
#   nome        nome que aparece na tabela para a conta principal (opcional)
ARQ_CONTAS = os.path.join(PASTA_BASE, "lcp_contas.csv")


def carregar_contas():
    contas, nomes = {}, {}
    if os.path.exists(ARQ_CONTAS):
        with open(ARQ_CONTAS, "r", encoding="utf-8-sig", newline="") as h:
            for r in csv.DictReader(h):
                sec = (r.get("secundaria") or "").strip()
                prin = (r.get("principal") or "").strip()
                if sec and prin:
                    contas[sec] = prin
                    if (r.get("nome") or "").strip():
                        nomes[prin] = r["nome"].strip()
    return contas, nomes


CONTAS, NOMES = carregar_contas()
ARQ_RP = os.path.join(PASTA_BASE, "lcp_round_player.csv")
ARQ_AP = os.path.join(PASTA_BASE, "lcp_apelidos.csv")
ARQ_JOG = os.path.join(PASTA_BASE, "lcp_jogadores.csv")

csv.field_size_limit(10 ** 7)


def ler(c):
    with open(c, "r", encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


def gravar(c, linhas, campos):
    with open(c, "w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)


def main():
    if not os.path.exists(ARQ_RP):
        print("Nao encontrei " + ARQ_RP)
        print("Rode antes:  py lcp_base.py")
        sys.exit(1)

    print("=" * 74)
    print("LCP CONTAS - fusao de contas da mesma pessoa")
    print("=" * 74)
    print()

    if not CONTAS:
        print("Nenhuma fusao configurada. Nada a fazer.")
        return

    linhas = ler(ARQ_RP)
    campos = list(linhas[0].keys()) if linhas else []
    if "steamid" not in campos:
        print("A base nao tem coluna steamid.")
        sys.exit(1)

    # o que existe hoje, antes de mexer
    antes = {}
    for r in linhas:
        s = r.get("steamid", "")
        a = antes.setdefault(s, {"rnd": 0, "part": set(), "nomes": set()})
        a["rnd"] += 1
        a["part"].add(r.get("partida"))
        if r.get("player"):
            a["nomes"].add(r["player"])

    ausentes = [s for s in CONTAS if s not in antes]
    principais_ausentes = [d for d in CONTAS.values() if d not in antes]

    for s in ausentes:
        print("AVISO: conta %s nao aparece na base. Fusao ignorada." % s)
    for d in principais_ausentes:
        print("AVISO: conta principal %s nao aparece na base." % d)
    if ausentes or principais_ausentes:
        print()

    # TRAVA: a mesma pessoa nao pode estar nas duas contas na MESMA partida.
    # Se isso acontecer, sao duas pessoas diferentes ou o steamid esta errado,
    # e fundir destruiria a base em silencio.
    bloqueadas = set()
    for sec, prin in CONTAS.items():
        if sec not in antes or prin not in antes:
            continue
        juntas = antes[sec]["part"] & antes[prin]["part"]
        if juntas:
            bloqueadas.add(sec)
            print("ERRO: as contas %s e %s aparecem juntas em %d partida(s)."
                  % (sec, prin, len(juntas)))
            print("      Nicks: %s  /  %s"
                  % (", ".join(sorted(antes[sec]["nomes"])),
                     ", ".join(sorted(antes[prin]["nomes"]))))
            print("      Uma pessoa nao joga duas vezes na mesma partida, entao")
            print("      sao jogadores diferentes ou o steamid na tabela esta errado.")
            print("      Essa fusao foi IGNORADA. Confira a tabela CONTAS.")
            print()
    if bloqueadas and len(bloqueadas) == len(CONTAS):
        print("Nenhuma fusao valida restou. Base nao foi alterada.")
        return

    # aplica a fusao
    trocadas = 0
    for r in linhas:
        s = r.get("steamid", "")
        if s in CONTAS and s in antes and s not in bloqueadas:
            r["steamid"] = CONTAS[s]
            trocadas += 1

    gravar(ARQ_RP, linhas, campos)
    print("Gravado: " + ARQ_RP)
    print("   linhas com steamid trocado: %d" % trocadas)
    print()

    # apelido preferido
    if os.path.exists(ARQ_AP):
        ap = ler(ARQ_AP)
        campos_ap = list(ap[0].keys()) if ap else []
        if "steamid" in campos_ap and "apelido" in campos_ap:
            ap = [r for r in ap
                  if r.get("steamid") not in CONTAS or r.get("steamid") in bloqueadas]
            vistos = set(r.get("steamid") for r in ap)
            for sid, nome in NOMES.items():
                achou = False
                for r in ap:
                    if r.get("steamid") == sid:
                        r["apelido"] = nome
                        achou = True
                if not achou and sid not in vistos:
                    novo = {c: "" for c in campos_ap}
                    novo["steamid"] = sid
                    novo["apelido"] = nome
                    ap.append(novo)
            gravar(ARQ_AP, ap, campos_ap)
            print("Gravado: " + ARQ_AP + "  (apelido preferido aplicado)")
            print()

    # limpa a conta absorvida de lcp_jogadores.csv
    if os.path.exists(ARQ_JOG):
        jg = ler(ARQ_JOG)
        campos_jg = list(jg[0].keys()) if jg else []
        if "steamid" in campos_jg:
            n0 = len(jg)
            jg = [r for r in jg
                  if r.get("steamid") not in CONTAS or r.get("steamid") in bloqueadas]
            gravar(ARQ_JOG, jg, campos_jg)
            print("Gravado: " + ARQ_JOG + "  (%d conta(s) absorvida(s) removida(s))" % (n0 - len(jg)))
            print()

    # relatorio
    print("=" * 74)
    print("RESULTADO DA FUSAO")
    print("=" * 74)
    for sec, prin in CONTAS.items():
        if sec not in antes or prin not in antes or sec in bloqueadas:
            continue
        a, b = antes[sec], antes[prin]
        nome = NOMES.get(prin) or (sorted(b["nomes"])[0] if b["nomes"] else prin)
        print()
        print("%s  (steamid %s)" % (nome, prin))
        print("   conta principal : %3d partidas, %4d rounds   nicks: %s"
              % (len(b["part"]), b["rnd"], ", ".join(sorted(b["nomes"]))))
        print("   conta absorvida : %3d partidas, %4d rounds   nicks: %s"
              % (len(a["part"]), a["rnd"], ", ".join(sorted(a["nomes"]))))
        print("   somado          : %3d partidas, %4d rounds"
              % (len(b["part"] | a["part"]), a["rnd"] + b["rnd"]))
    print()
    print("Agora rode:  py lcp_dano.py  ->  py lcp_rating.py  ->  py lcp_painel.py")


if __name__ == "__main__":
    main()