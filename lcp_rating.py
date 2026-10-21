# -*- coding: utf-8 -*-
r"""
lcp_rating.py - LCP Rating na escala 1.00 (padrao HLTV)

O QUE MUDOU NESTA VERSAO
1. O ADR passou a ser dano real (corrigido pelo lcp_dano.py).
2. A confiabilidade de cada metrica agora e medida por divisao em metades
   (rounds pares contra rounds impares, com correcao de Spearman-Brown),
   e nao mais por estabilidade entre partidas. Motivo: no formato MIX os
   times mudam a cada partida, entao o teste entre partidas media a troca
   de time junto com o jogador e punia metricas boas.
3. Metricas descartadas por nao terem sinal individual:
   Trade kills e Saldo de entry.
4. Metricas novas: Volume de entry, Dano de utility por round,
   Inimigos cegados por round.
5. (21/10) Clutch FORA da nota, por decisao do dono do projeto: virou a
   coluna Clutch_pct, a porcentagem de clutches convertidos. So conta quem foi
   para cima (matou, morreu ou defusou) ou venceu; quem guardou a arma (nao
   matou, nao morreu e perdeu, ou morreu sem matar longe da C4 plantada) fica
   de fora. Nenhuma versao de clutch passou no teste de confiabilidade com a
   amostra atual (~20 clutches por jogador).
6. A nota final sai na escala 1.00, onde 1.00 e a media do grupo.
7. (20/10) Leverage saiu: variava so 7% entre os jogadores. No lugar,
   Kills em desvantagem = parte das kills feitas com o time em menor numero
   (inclui a que empata). Utility bem-sucedida conta granada por granada, so
   inimigo; toda smoke conta como acerto e decoy sai. K/D caiu para 15% da
   Efficiency. Entraram: Assistencias (Teamplay), KAST e Morrer primeiro,
   que conta contra (Efficiency), Volume de entry de TR e Entry kill de TR
   (Entry). Taxa de troca foi testada e deu ruido: fica so informativa.
8. (21/10) Entry: entrou First kills por round, saiu Volume de entry geral
   (que premiava tambem morrer primeiro).
9. Os pilares usam a MESMA escala da nota, entao a nota e exatamente a media
   ponderada dos quatro pilares mostrados e da para conferir na mao.

ORDEM DE EXECUCAO
    py lcp_base.py
    py lcp_contas.py
    py lcp_dano.py
    py lcp_rating.py
    py lcp_painel.py
"""

import csv
import math
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
ARQ_OUT = os.path.join(PASTA_BASE, "lcp_rating.csv")
ARQ_PERFIL = os.path.join(PASTA_BASE, "lcp_perfil.csv")
ARQ_XLSX = os.path.join(PASTA_BASE, "LCP_Rating.xlsx")

MIN_PARTIDAS = 4
MIN_ROUNDS = 60
PRIOR_BASE = 40.0      # forca do encolhimento para metrica pouco confiavel
PRIOR_PISO = 10.0
ESPALHAMENTO = 0.11    # desvio padrao alvo da nota, igual ao HLTV

PESOS_PILARES = {
    "Impact": 0.40,
    "Teamplay": 0.22,
    "Efficiency": 0.20,
    "Entry": 0.18,
}

csv.field_size_limit(10 ** 7)


def f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def bo(v):
    return 1 if str(v).strip().lower() in ("true", "1", "1.0") else 0


def ler(caminho):
    with open(caminho, "r", encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


def soma(rs, col):
    return sum(f(r.get(col)) for r in rs)


# ---------------------------------------------------------------- metricas
# cada metrica: (nome, pilar, peso no pilar, funcao valor, funcao tamanho da amostra,
#                precisa de flash)
def _lado_t(fn):
    """A mesma conta, so nos rounds em que ele jogou de TR."""
    return lambda rs: fn([r for r in rs if r.get("time") == "T"])


def _contra(fn):
    """Metrica que conta contra: quanto maior o valor, pior."""
    def g(rs):
        v, n = fn(rs)
        return (-v, n) if v is not None else (None, 0)
    return g


def _por_round(col):
    return lambda rs: (soma(rs, col) / len(rs), len(rs)) if rs else (None, 0)


def _kast(rs):
    """Matou, deu assistencia, sobreviveu ou foi trocado."""
    ok = sum(1 for r in rs if f(r.get("kills")) > 0 or f(r.get("assists")) > 0
             or not bo(r.get("died")) or f(r.get("deaths_traded")) > 0)
    return (ok / len(rs), len(rs)) if rs else (None, 0)


METRICAS = [
    ("ADR", "Impact", 0.40,
     lambda rs: (soma(rs, "damage") / len(rs), len(rs)) if rs else (None, 0), False),
    ("Kills por round", "Impact", 0.25,
     lambda rs: (soma(rs, "kills") / len(rs), len(rs)) if rs else (None, 0), False),
    ("Multi-kill", "Impact", 0.20,
     lambda rs: (sum(bo(r["multi_kill"]) for r in rs) / len(rs), len(rs)) if rs else (None, 0), False),
    ("Kills em desvantagem", "Impact", 0.15,
     lambda rs: (soma(rs, "kills_desvantagem") / soma(rs, "kills_modelo"), soma(rs, "kills_modelo"))
     if soma(rs, "kills_modelo") > 0 else (None, 0), False),

    ("Contribuicao de utility", "Teamplay", 0.20,
     lambda rs: (soma(rs, "util_thrown") / len(rs), len(rs)) if rs else (None, 0), False),
    ("Inimigos cegados por round", "Teamplay", 0.15,
     lambda rs: (soma(rs, "enemies_blinded") / len(rs), len(rs)) if rs else (None, 0), True),
    ("Utility bem-sucedida", "Teamplay", 0.15,
     lambda rs: (soma(rs, "util_ok") / soma(rs, "util_thrown"), soma(rs, "util_thrown"))
     if soma(rs, "util_thrown") > 0 else (None, 0), True),
    ("Dano de utility por round", "Teamplay", 0.15,
     lambda rs: (soma(rs, "util_damage") / len(rs), len(rs)) if rs else (None, 0), False),
    ("Ser trocado ao morrer", "Teamplay", 0.15,
     lambda rs: (soma(rs, "deaths_traded") / soma(rs, "deaths"), soma(rs, "deaths"))
     if soma(rs, "deaths") > 0 else (None, 0), False),
    ("Assistencias por round", "Teamplay", 0.20, _por_round("assists"), False),

    ("K/D", "Efficiency", 0.15,
     lambda rs: (soma(rs, "kills") / soma(rs, "deaths"), soma(rs, "deaths"))
     if soma(rs, "deaths") > 0 else (None, 0), False),
    ("Headshot %", "Efficiency", 0.25,
     lambda rs: (soma(rs, "headshots") / soma(rs, "kills"), soma(rs, "kills"))
     if soma(rs, "kills") > 0 else (None, 0), False),
    ("Sobrevivencia", "Efficiency", 0.25,
     lambda rs: (1 - sum(bo(r["died"]) for r in rs) / len(rs), len(rs)) if rs else (None, 0), False),
    ("KAST", "Efficiency", 0.20, _kast, False),
    ("Morrer primeiro (contra)", "Efficiency", 0.15, _contra(_por_round("entry_deaths")), False),

    ("First kills por round", "Entry", 0.35, _por_round("entry_kills"), False),
    ("Aproveitamento de entry", "Entry", 0.30,
     lambda rs: (soma(rs, "entry_kills") / soma(rs, "entry_attempts"), soma(rs, "entry_attempts"))
     if soma(rs, "entry_attempts") > 0 else (None, 0), False),
    ("Volume de entry de TR", "Entry", 0.20, _lado_t(_por_round("entry_attempts")), False),
    ("Entry kill de TR", "Entry", 0.15, _lado_t(_por_round("entry_kills")), False),

]


# ---------------------------------------------------------------- estatistica
def spearman(xs, ys):
    n = len(xs)
    if n < 4:
        return float("nan")

    def rk(v):
        o = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[o[j + 1]] == v[o[i]]:
                j += 1
            m = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[o[k]] = m
            i = j + 1
        return r

    rx, ry = rk(xs), rk(ys)
    mx = sum(rx) / n
    my = sum(ry) / n
    nu = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return nu / (dx * dy) if dx > 0 and dy > 0 else float("nan")


def desvio(v):
    n = len(v)
    if n < 2:
        return 0.0
    m = sum(v) / n
    return math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1))


def consistencia(rs_por_partida):
    """Nota de regularidade: menos variacao do ADR entre partidas e melhor."""
    adrs = [soma(rs, "damage") / len(rs) for rs in rs_por_partida if len(rs) >= 10]
    if len(adrs) < 3:
        return None, 0
    m = sum(adrs) / len(adrs)
    if m <= 0:
        return None, 0
    return -desvio(adrs) / m, len(adrs)


def main():
    if not os.path.exists(ARQ_RP):
        print("Nao encontrei " + ARQ_RP + ". Rode antes:  py lcp_base.py")
        sys.exit(1)

    linhas = ler(ARQ_RP)
    apelidos = {}
    if os.path.exists(ARQ_AP):
        for r in ler(ARQ_AP):
            if r.get("steamid"):
                apelidos[r["steamid"]] = r.get("apelido") or ""

    # agrupa
    por_jog = {}
    por_jog_part = {}
    nome_demo = {}
    for r in linhas:
        s = r.get("steamid", "")
        por_jog.setdefault(s, []).append(r)
        por_jog_part.setdefault(s, {}).setdefault(r["partida"], []).append(r)
        nome_demo.setdefault(s, r.get("player", ""))

    def rs_de(s, exige_flash):
        rs = por_jog[s]
        return [r for r in rs if bo(r.get("tem_flash"))] if exige_flash else rs

    elegiveis = [s for s in por_jog
                 if len(por_jog[s]) >= MIN_ROUNDS and len(por_jog_part[s]) >= MIN_PARTIDAS]

    print("=" * 96)
    print("LCP RATING   -   escala 1.00, onde 1.00 e a media do grupo")
    print("=" * 96)
    print()
    print("Criterio: %d partidas e %d rounds no minimo" % (MIN_PARTIDAS, MIN_ROUNDS))
    print("Classificados: %d de %d jogadores" % (len(elegiveis), len(por_jog)))
    print()

    # ---------- confiabilidade por divisao em metades ----------
    conf = {}
    for nome, pilar, peso, fn, flash in METRICAS:
        A, B = [], []
        for s in por_jog:
            rr = rs_de(s, flash)
            if len(rr) < MIN_ROUNDS:
                continue
            rr = sorted(rr, key=lambda r: (r["partida"], int(f(r.get("event_index")))))
            a, _ = fn(rr[0::2])
            b, _ = fn(rr[1::2])
            if a is None or b is None:
                continue
            A.append(a)
            B.append(b)
        r = spearman(A, B)
        sb = (2 * r / (1 + r)) if (r == r and r > -0.99) else 0.0
        conf[nome] = max(min(sb, 0.95), 0.05)

    print("CONFIABILIDADE DAS METRICAS (divisao em metades, corrigida)")
    print("-" * 96)
    print("%-30s %-13s %8s %8s   %s" % ("METRICA", "PILAR", "PESO", "CONFIAN", "SITUACAO"))
    for nome, pilar, peso, fn, flash in METRICAS:
        c = conf[nome]
        sit = "forte" if c >= 0.70 else "boa" if c >= 0.50 else "fraca" if c >= 0.30 else "ruim"
        print("%-30s %-13s %7.0f%% %8.3f   %s%s" % (
            nome, pilar, peso * 100, c, sit, "   (precisa de flash)" if flash else ""))
    print()
    print("Regularidade entre partidas ficou FORA da nota: nao da para medir variacao")
    print("  de um jogador com 4 a 19 partidas. Aparece como coluna informativa.")
    print()

    # ---------- valores por jogador, com encolhimento ----------
    cru = {}
    for nome, pilar, peso, fn, flash in METRICAS:
        vals, tams = {}, {}
        for s in elegiveis:
            v, n = fn(rs_de(s, flash))
            if v is not None and n > 0:
                vals[s] = v
                tams[s] = n
        if not vals:
            cru[nome] = {}
            continue
        tot_n = sum(tams.values())
        pop = sum(vals[s] * tams[s] for s in vals) / tot_n
        n0 = PRIOR_PISO + PRIOR_BASE * (1 - conf[nome])
        cru[nome] = {s: (tams[s] * vals[s] + n0 * pop) / (tams[s] + n0) for s in vals}

    cons = {}
    for s in elegiveis:
        v, _ = consistencia(list(por_jog_part[s].values()))
        if v is not None:
            cons[s] = v

    # ---------- z por metrica ----------
    def zs(d):
        if len(d) < 2:
            return {s: 0.0 for s in d}
        m = sum(d.values()) / len(d)
        sd = desvio(list(d.values()))
        return {s: ((v - m) / sd if sd > 0 else 0.0) for s, v in d.items()}

    zmet = {nome: zs(cru[nome]) for nome, _, _, _, _ in METRICAS}
    zcons = zs(cons)

    # ---------- pilares ----------
    pilares = {}
    for s in elegiveis:
        p = {}
        for nome_p in PESOS_PILARES:
            num = den = 0.0
            for nome, pilar, peso, fn, flash in METRICAS:
                if pilar != nome_p or s not in zmet[nome]:
                    continue
                w = peso * conf[nome]
                num += w * zmet[nome][s]
                den += w
            p[nome_p] = num / den if den > 0 else 0.0
        pilares[s] = p

    # ---------- nota final ----------
    # CORRECAO: a nota e os pilares usam o MESMO fator de escala.
    # Antes o pilar saia em 1.00 + z/10 e a nota em 1.00 + 0.11*z/desvio, que
    # e um fator maior. O efeito era a nota final aparecer acima de todos os
    # pilares do jogador, e a tabela nao fechar quando alguem tentava conferir
    # a conta na mao. Agora a nota e exatamente a media ponderada dos pilares
    # mostrados.
    centro = {k: (sum(pilares[s][k] for s in elegiveis) / len(elegiveis))
              for k in PESOS_PILARES}

    bruto = {s: sum(PESOS_PILARES[k] * (pilares[s][k] - centro[k]) for k in PESOS_PILARES)
             for s in elegiveis}
    sd = desvio(list(bruto.values())) or 1.0
    fator = ESPALHAMENTO / sd

    lcp = {s: 1.0 + fator * bruto[s] for s in elegiveis}
    pilar_nota = {s: {k: 1.0 + fator * (pilares[s][k] - centro[k]) for k in PESOS_PILARES}
                  for s in elegiveis}

    # ---------- funcao ----------
    # ---------- funcao (nomes do CS) ----------
    # AWPer   20% ou mais das kills de sniper
    # Lurker  joga longe do time no TR (1 desvio acima da media na distancia ate
    #         o companheiro que morre) e entra pouco no TR. Sem a segunda regra o
    #         entry, que vai na frente, apareceria como lurker.
    # Entry   pilar Entry e o destaque do proprio perfil
    # Support pilar Teamplay e o destaque do proprio perfil
    # Rifler  o resto: destaque em Impact ou Efficiency, ou sem destaque
    # IGL fica de fora: lideranca nao aparece na demo.
    LIMIAR_AWP = 0.20
    LIMIAR_LURK = 1.0

    def media_t(s, num, den):
        t = [r for r in por_jog[s] if r.get("time") == "T"]
        d = soma(t, den)
        return soma(t, num) / d if d > 0 else None

    awp = {s: (soma(por_jog[s], "sniper_kills") / soma(por_jog[s], "kills")
               if soma(por_jog[s], "kills") > 0 else 0.0) for s in elegiveis}
    longe = {s: media_t(s, "lurk_soma", "lurk_n") for s in elegiveis}
    longe = {s: v for s, v in longe.items() if v is not None}
    z_longe = zs(longe)
    vol_t = {}
    for s in elegiveis:
        t = [r for r in por_jog[s] if r.get("time") == "T"]
        vol_t[s] = soma(t, "entry_attempts") / len(t) if t else 0.0
    mediana_vol_t = sorted(vol_t.values())[len(vol_t) // 2]

    def funcao(s):
        if awp.get(s, 0) >= LIMIAR_AWP:
            return "AWPer"
        if z_longe.get(s, 0) >= LIMIAR_LURK and vol_t.get(s, 0) < mediana_vol_t:
            return "Lurker"
        p = {k: v for k, v in pilares[s].items() if k in ("Impact", "Teamplay", "Efficiency", "Entry")}
        m = sum(p.values()) / len(p)
        rel = {k: p[k] - m for k in p}
        top = max(rel, key=lambda k: rel[k])
        if rel[top] >= 0.22 and top == "Entry":
            return "Entry"
        if rel[top] >= 0.22 and top == "Teamplay":
            return "Support"
        return "Rifler"

    def pnota(s, k):
        return pilar_nota[s][k]

    # ---------- baiter (diversao, NAO entra no LCP) ----------
    # Tres indicadores que passaram no teste de confiabilidade (21/10):
    #   Nunca abre    no TR, quase nunca e o primeiro a morrer       0,787
    #   Sempre sobra  no TR, e o ultimo vivo do time                 0,644
    #   Nao vingou    companheiro morreu perto e ele nao trocou      0,516
    # Mesmo encolhimento das metricas da nota; a media dos tres vira posicao
    # de 0 a 100 (100 = o mais baiter do grupo).
    def _t(rs):
        return [r for r in rs if r.get("time") == "T"]

    BAITER = [
        ("Nunca abre", 0.787, lambda rs: (1 - soma(_t(rs), "entry_deaths") / len(_t(rs)), len(_t(rs)))
         if _t(rs) else (None, 0)),
        ("Sempre sobra", 0.644, lambda rs: (sum(1 for r in _t(rs) if f(r.get("clutch_situacao")) > 0)
                                            / len(_t(rs)), len(_t(rs))) if _t(rs) else (None, 0)),
        ("Nao vingou", 0.516, lambda rs: ((soma(rs, "trade_oport") - soma(rs, "trade_feitas"))
                                          / soma(rs, "trade_oport"), soma(rs, "trade_oport"))
         if soma(rs, "trade_oport") > 0 else (None, 0)),
    ]
    z_bait = []
    for nome_b, conf_b, fn_b in BAITER:
        vals, tams = {}, {}
        for s in elegiveis:
            v, n = fn_b(por_jog[s])
            if v is not None and n > 0:
                vals[s], tams[s] = v, n
        pop = sum(vals[s] * tams[s] for s in vals) / sum(tams.values())
        n0 = PRIOR_PISO + PRIOR_BASE * (1 - conf_b)
        z_bait.append(zs({s: (tams[s] * vals[s] + n0 * pop) / (tams[s] + n0) for s in vals}))
    bruto_bait = {s: sum(z.get(s, 0.0) for z in z_bait) / len(z_bait) for s in elegiveis}
    ordem_bait = sorted(elegiveis, key=lambda s: bruto_bait[s])
    baiter = {s: round(100 * i / (len(ordem_bait) - 1)) for i, s in enumerate(ordem_bait)}

    def rotulo_baiter(v):
        if v >= 80:
            return "Baiter raiz"
        if v >= 60:
            return "Suspeito"
        if v >= 40:
            return "Normal"
        if v >= 20:
            return "Inocente"
        return "Kamikaze"

    # ---------- saida ----------
    ordem = sorted(elegiveis, key=lambda s: -lcp[s])
    print("=" * 96)
    print("CLASSIFICACAO")
    print("=" * 96)
    print("%3s %-14s %6s %-12s %7s %9s %11s %6s %8s %6s %6s %5s %4s %5s" % (
        "#", "apelido", "LCP", "funcao", "Impact", "Teamplay", "Efficiency",
        "Entry", "clutch", "ADR", "K/D", "rnd", "pt", "pouc"))
    print("-" * 96)
    saida = []
    for i, s in enumerate(ordem, 1):
        rs = por_jog[s]
        adr = soma(rs, "damage") / len(rs)
        kpr = soma(rs, "kills") / len(rs)
        kd = soma(rs, "kills") / soma(rs, "deaths") if soma(rs, "deaths") > 0 else 0.0
        npart = len(por_jog_part[s])
        poucas = "sim" if npart < 6 else ""
        nome = apelidos.get(s) or nome_demo.get(s, s)
        p = pilares[s]
        # clutch: informativo, fora da nota
        cl_n = int(soma(rs, "clutch_conta"))
        cl_v = int(soma(rs, "clutch_venceu"))
        cl_pct = round(100 * cl_v / cl_n, 1) if cl_n else ""
        print("%3d %-14s %6.2f %-12s %7.2f %9.2f %11.2f %6.2f %8s %6.1f %6.2f %5d %4d %5s" % (
            i, nome[:14], lcp[s], funcao(s), pnota(s, "Impact"), pnota(s, "Teamplay"),
            pnota(s, "Efficiency"), pnota(s, "Entry"),
            ("%d/%d" % (cl_v, cl_n)) if cl_n else "-", adr, kd, len(rs), npart, poucas))
        saida.append({
            "posicao": i, "apelido": nome, "steamid": s, "LCP": round(lcp[s], 2),
            "funcao": funcao(s),
            "Impact": round(pnota(s, "Impact"), 2),
            "Teamplay": round(pnota(s, "Teamplay"), 2),
            "Efficiency": round(pnota(s, "Efficiency"), 2),
            "Entry": round(pnota(s, "Entry"), 2),
            "Clutch_pct": cl_pct, "Clutch_vencidos": cl_v, "Clutch_total": cl_n,
            "Regularidade": (round(1.0 + fator * zcons[s], 2) if s in zcons else ""),
            "Baiter": baiter[s], "Baiter_rotulo": rotulo_baiter(baiter[s]),
            "ADR": round(adr, 1), "KPR": round(kpr, 2), "KD": round(kd, 2),
            "rounds": len(rs), "partidas": npart, "poucas_partidas": poucas,
        })

    campos = ["posicao", "apelido", "steamid", "LCP", "funcao"] + list(PESOS_PILARES.keys()) + \
             ["Clutch_pct", "Clutch_vencidos", "Clutch_total", "Regularidade", "Baiter", "Baiter_rotulo", "ADR", "KPR", "KD", "rounds", "partidas",
              "poucas_partidas"]
    with open(ARQ_OUT, "w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=campos)
        w.writeheader()
        w.writerows(saida)
    print()
    print("Gravado: " + ARQ_OUT)

    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "LCP Rating"
        ws.append(campos)
        for r in saida:
            ws.append([r[c] for c in campos])
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = max(
                10, min(22, max(len(str(c.value or "")) for c in col) + 2))
        wb.save(ARQ_XLSX)
        print("Gravado: " + ARQ_XLSX)
    except ImportError:
        print("Excel nao gerado (falta openpyxl). Se quiser:  py -m pip install openpyxl")

    print()
    print("COMO LER")
    print("  LCP 1.00 e a media do grupo. 1.15 e muito acima, 0.85 e muito abaixo.")
    print("  Os pilares usam a MESMA escala da nota: 1.00 e a media do grupo.")
    print("  A nota e a media ponderada dos quatro pilares (" + ", ".join(
        "%s %.0f%%" % (k, v * 100) for k, v in PESOS_PILARES.items()) + "),")
    print("  entao da para conferir a conta na mao.")
    print("  Clutch (vencidos/total), Regularidade e Baiter sao informativos, fora da nota.")
    print("  Coluna pouc = jogador com menos de 6 partidas, nota menos firme.")


if __name__ == "__main__":
    main()
