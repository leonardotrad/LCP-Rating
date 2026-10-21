# -*- coding: utf-8 -*-
r"""
lcp_dano.py - corrige a coluna de dano da base do LCP Rating.

POR QUE ISSO EXISTE
O round_player_stats.py grava em "damage" apenas o dano do golpe que matou.
Todo tiro que acertou mas nao finalizou era descartado. Isso fazia o ADR
virar um reflexo da contagem de kills em vez de medir dano, e penalizava
muito quem causa dano sem finalizar.

O QUE ELE FAZ
Le os eventos brutos de dano de cada partida em saidas\<codigo>\data_damage.csv,
reconstroi a vida da vitima round por round para contar o dano real em pontos
de vida (sem o excesso do golpe letal), descarta dano em companheiro de equipe
e grava o resultado na coluna "damage" de base\lcp_round_player.csv.

ORDEM DE EXECUCAO
    py lcp_base.py
    py lcp_dano.py      <-- aqui
    py lcp_rating.py

Valide: o ADR do topo da tabela deve ficar proximo de 100.
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
PASTA_BASE = "base"
ARQ_ROUND_PLAYER = os.path.join(PASTA_BASE, "lcp_round_player.csv")
ARQ_JOGADORES = os.path.join(PASTA_BASE, "lcp_jogadores.csv")
ARQ_AUDITORIA = os.path.join(PASTA_BASE, "lcp_dano.csv")

csv.field_size_limit(10 ** 7)


def ler_csv(caminho):
    with open(caminho, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def gravar_csv(caminho, linhas, campos):
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(linhas)


def num(v, padrao=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return padrao


def dano_da_partida(codigo):
    """Dano real causado e recebido por (event_index, jogador), so entre inimigos.
    None se a partida nao tem dado de dano."""
    arq_dano = os.path.join(PASTA_SAIDAS, codigo, "data_damage.csv")
    if not os.path.exists(arq_dano):
        return None
    eventos = ler_csv(arq_dano)
    if not eventos:
        return None

    # time de cada jogador em cada round, para descartar dano em companheiro
    times = {}
    arq_ctx = os.path.join(PASTA_SAIDAS, codigo, "round_player_context.csv")
    if os.path.exists(arq_ctx):
        for r in ler_csv(arq_ctx):
            times[(str(r.get("event_index")), r.get("player"))] = r.get("team")

    eventos.sort(key=lambda r: (int(num(r.get("round_event_index"))), int(num(r.get("tick")))))

    vida = {}
    dano = {}
    recebido = {}
    for r in eventos:
        ri = str(r.get("round_event_index"))
        atacante = r.get("attacker_name")
        vitima = r.get("victim_name")
        if not atacante or not vitima:
            continue

        chave_vida = (ri, vitima)
        antes = vida.get(chave_vida, 100.0)
        depois = num(r.get("health_after_hit"), antes)
        perda = antes - depois
        vida[chave_vida] = depois

        if perda <= 0:
            continue
        if atacante == vitima:
            continue
        ta = times.get((ri, atacante))
        tv = times.get((ri, vitima))
        if ta and tv and ta == tv:
            continue

        k = (ri, atacante)
        dano[k] = dano.get(k, 0.0) + perda
        kv = (ri, vitima)
        recebido[kv] = recebido.get(kv, 0.0) + perda

    return dano, recebido


def main():
    if not os.path.exists(ARQ_ROUND_PLAYER):
        print("Nao encontrei " + ARQ_ROUND_PLAYER)
        print("Rode primeiro:  py lcp_base.py")
        sys.exit(1)
    if not os.path.isdir(PASTA_SAIDAS):
        print("Nao encontrei a pasta " + PASTA_SAIDAS)
        sys.exit(1)

    print("=" * 78)
    print("LCP DANO - correcao da coluna de dano")
    print("=" * 78)
    print()

    linhas = ler_csv(ARQ_ROUND_PLAYER)
    campos = list(linhas[0].keys()) if linhas else []
    if "damage_received" not in campos:
        campos.append("damage_received")

    # apelido atual da FACEIT, para o relatorio sair com o nome certo
    apelidos = {}
    arq_ap = os.path.join(PASTA_BASE, "lcp_apelidos.csv")
    if os.path.exists(arq_ap):
        for r in ler_csv(arq_ap):
            if r.get("steamid"):
                apelidos[r["steamid"]] = r.get("apelido") or ""

    if "damage" not in campos:
        print("A base nao tem coluna damage. Nada a fazer.")
        sys.exit(1)

    partidas = sorted(set(r["partida"] for r in linhas))
    tabela = {}
    tabela_rec = {}
    sem_dado = []
    for cod in partidas:
        d = dano_da_partida(cod)
        if d is None:
            sem_dado.append(cod)
            continue
        d, rec = d
        for (ri, jog), v in d.items():
            tabela[(cod, ri, jog)] = v
        for (ri, jog), v in rec.items():
            tabela_rec[(cod, ri, jog)] = v

    if sem_dado:
        print("ATENCAO - partidas sem data_damage.csv, mantidas como estavam:")
        for c in sem_dado:
            print("   " + c)
        print()

    # aplica
    antes_por_jog = {}
    depois_por_jog = {}
    rounds_por_jog = {}
    nomes = {}
    alteradas = 0
    kills_sem_dano = 0

    for r in linhas:
        cod = r["partida"]
        sid = r.get("steamid", "")
        nomes.setdefault(sid, apelidos.get(sid) or r.get("player", ""))
        velho = num(r.get("damage"))

        if cod in sem_dado:
            novo = velho
        else:
            novo = tabela.get((cod, str(r.get("event_index")), r.get("player")))
            if novo is None:
                novo = 0.0
                if num(r.get("kills")) > 0:
                    kills_sem_dano += 1

        if abs(novo - velho) > 0.01:
            alteradas += 1
        r["damage"] = str(int(round(novo)))
        if cod in sem_dado:
            r["damage_received"] = ""
        else:
            rec = tabela_rec.get((cod, str(r.get("event_index")), r.get("player")), 0.0)
            r["damage_received"] = str(int(round(rec)))

        antes_por_jog[sid] = antes_por_jog.get(sid, 0.0) + velho
        depois_por_jog[sid] = depois_por_jog.get(sid, 0.0) + novo
        rounds_por_jog[sid] = rounds_por_jog.get(sid, 0) + 1

    gravar_csv(ARQ_ROUND_PLAYER, linhas, campos)
    print("Gravado: " + ARQ_ROUND_PLAYER)
    print("   linhas: %d   corrigidas: %d" % (len(linhas), alteradas))
    if kills_sem_dano:
        print("   %d linhas com kill e sem evento de dano (residuo de warmup, desprezivel)" % kills_sem_dano)
    print()

    # auditoria
    aud = []
    for (cod, ri, jog), v in sorted(tabela.items()):
        aud.append({"partida": cod, "event_index": ri, "player": jog, "dano_real": round(v, 1)})
    gravar_csv(ARQ_AUDITORIA, aud, ["partida", "event_index", "player", "dano_real"])
    print("Gravado: " + ARQ_AUDITORIA + "  (trilha de auditoria)")
    print()

    # atualiza adr em lcp_jogadores.csv, se existir
    if os.path.exists(ARQ_JOGADORES):
        jl = ler_csv(ARQ_JOGADORES)
        jc = list(jl[0].keys()) if jl else []
        if "adr" in jc:
            for r in jl:
                sid = r.get("steamid", "")
                n = rounds_por_jog.get(sid, 0)
                if n:
                    r["adr"] = str(round(depois_por_jog[sid] / n, 1))
            gravar_csv(ARQ_JOGADORES, jl, jc)
            print("Gravado: " + ARQ_JOGADORES + "  (coluna adr atualizada)")
            print()

    # relatorio
    print("=" * 78)
    print("ADR ANTES x DEPOIS  (jogadores com 50 rounds ou mais)")
    print("=" * 78)
    print("%-16s %6s %10s %10s %9s" % ("jogador", "rounds", "ADR antes", "ADR novo", "delta"))
    print("-" * 78)
    res = []
    for sid, n in rounds_por_jog.items():
        if n < 50:
            continue
        res.append((nomes.get(sid, sid), n, antes_por_jog[sid] / n, depois_por_jog[sid] / n))
    for nome, n, a, b in sorted(res, key=lambda x: -x[3]):
        print("%-16s %6d %10.1f %10.1f %+9.1f" % (nome, n, a, b, b - a))
    print()
    if res:
        print("Media do grupo: %.1f  ->  %.1f" % (
            sum(x[2] for x in res) / len(res), sum(x[3] for x in res) / len(res)))
    print()
    print("O ADR do topo deve ficar proximo de 100. Se bateu, siga:")
    print("    py lcp_rating.py")


if __name__ == "__main__":
    main()
