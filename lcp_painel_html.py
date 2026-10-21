# -*- coding: utf-8 -*-
r"""
lcp_painel_html.py - gera o painel do draft (HTML, PNG e PDF), no modelo do
"LCP Rating - Guia do Draft, edicao Halloween".

Le o que a esteira ja produziu:
    base\lcp_painel.csv        nota, pilares e numeros de exibicao (lcp_painel.py)
    base\lcp_round_player.csv  total de rounds
    base\lcp_partidas.csv      total de partidas
    base\lcp_datas.csv         periodo
    base\lcp_draft.csv         lista oficial do draft: lista, base, capitao, tier
                               (fica em base\ para os apelidos nao irem ao GitHub)
    base\painel\lcp_banner.png banner da LCP, de onde sai o logo

Grava em base\painel\:
    LCP_Painel.html, LCP_Painel.png, LCP_Painel.pdf

O PNG e o PDF saem pelo Microsoft Edge em modo invisivel, que ja vem no
Windows. Nao precisa instalar nada.

Rode depois do lcp_painel.py:
    py lcp_painel_html.py
"""

import base64
import csv
import html
import os
import subprocess
import sys
from pathlib import Path

from lcp_rating import PESOS_PILARES

# pesos que o lcp_rating.py realmente usou na ultima execucao (pode ser um teste)
try:
    import json as _json
    with open(os.path.join("base", "lcp_pesos_usados.json"), encoding="utf-8") as _h:
        PESOS_PILARES = _json.load(_h)["pilares"]
except (OSError, ValueError, KeyError):
    pass

# apelido com caractere especial nao pode derrubar o script no terminal do Windows
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


PASTA_BASE = Path("base")
# --teste: grava em base/painel_teste/ e marca "PESOS DE TESTE" no cabecalho,
# para comparar uma distribuicao de pesos sem tocar no painel oficial
TESTE = "--teste" in sys.argv
PASTA_OUT = PASTA_BASE / ("painel_teste" if TESTE else "painel")
ARQ_PAINEL = PASTA_BASE / "lcp_painel.csv"
ARQ_RP = PASTA_BASE / "lcp_round_player.csv"
ARQ_DRAFT = PASTA_BASE / "lcp_draft.csv"
ARQ_PART = PASTA_BASE / "lcp_partidas.csv"
ARQ_DATAS = PASTA_BASE / "lcp_datas.csv"
ARQ_BANNER = PASTA_BASE / "painel" / "lcp_banner.png"
ARQ_CHANCE = PASTA_BASE / "lcp_clutch_chance.csv"

EDGE = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

LARGURA = 1680
ALTURA = 1700

# recorte do logo dentro do banner (pixels do banner de 1448x1086)
LOGO_X, LOGO_Y, LOGO_L = 262, 312, 910
LOGO_CAIXA = 250

SIGLA = {"Impact": "IMP", "Teamplay": "TEAM", "Efficiency": "EFI", "Entry": "ENT", "Clutch": "CLU"}

DESCRICAO = {
    "Impact": "dano, kills e kills que viram o round",
    "Teamplay": "utilitária (smoke inclusa), flash, assistências e vingar o companheiro (trade)",
    "Efficiency": "headshot, sobrevivência, KAST e K/D; morrer primeiro conta contra",
    "Entry": "first kill, aproveitamento do primeiro duelo e entrada no lado TR",
    "Clutch": "converter o clutch quando vai pra cima; vale mais contra mais inimigos",
}


def ler(c):
    with open(c, "r", encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def faixa(v):
    if v is None:
        return "nd"
    if v >= 1.10:
        return "exc"
    if v >= 1.00:
        return "bom"
    if v >= 0.90:
        return "ate"
    return "fra"


def periodo():
    if not ARQ_DATAS.exists():
        return ""
    datas = set()
    for r in ler(ARQ_DATAS):
        for v in r.values():
            t = str(v or "")
            if len(t) >= 10 and t[:4].isdigit() and t[4] == "-" and t[7] == "-":
                datas.add(t[:10])
    if not datas:
        return ""
    a, b = min(datas), max(datas)
    return "%s/%s a %s/%s/%s" % (a[8:10], a[5:7], b[8:10], b[5:7], b[:4])


def logo_css():
    if not ARQ_BANNER.exists():
        return "", False
    dado = base64.b64encode(ARQ_BANNER.read_bytes()).decode()
    k = LOGO_CAIXA / LOGO_L
    css = (".logo{width:%dpx;height:%dpx;background:url(data:image/png;base64,%s) no-repeat;"
           "background-size:%.1fpx auto;background-position:-%.1fpx -%.1fpx;}"
           % (LOGO_CAIXA, round(300 * k), dado, 1448 * k, LOGO_X * k, LOGO_Y * k))
    return css, True


def barra(v):
    """Barrinha centrada em 1.00: para a direita acima da media, para a
    esquerda abaixo. 0.30 de distancia enche metade da barra."""
    d = max(-1.0, min(1.0, (v - 1.0) / 0.30))
    if d >= 0:
        esq, larg = 50.0, 50.0 * d
    else:
        esq, larg = 50.0 + 50.0 * d, -50.0 * d
    return ('<span class="barra"><i style="left:%.1f%%;width:%.1f%%"></i><b></b></span>'
            % (esq, max(larg, 1.5)))


def montar():
    for arq in (ARQ_PAINEL, ARQ_DRAFT):
        if not arq.exists():
            print("Nao encontrei " + str(arq))
            if arq == ARQ_PAINEL:
                print("Rode antes:  py lcp_rating.py  ->  py lcp_painel.py")
            sys.exit(1)

    painel = {r["apelido"]: r for r in ler(ARQ_PAINEL)}
    draft = ler(ARQ_DRAFT)
    pilares = list(PESOS_PILARES)

    linhas, fora = [], []
    for d in draft:
        p = painel.get(d.get("base") or "")
        (linhas if p else fora).append((d, p))
    # ordena pela posicao do lcp_rating.py, que usa a nota sem arredondar.
    # Ordenar pela nota exibida (2 casas) desempatava pela ordem da lista do draft.
    linhas.sort(key=lambda x: f(x[1]["posicao"]))

    rnd = len(set((r["partida"], r["event_index"]) for r in ler(ARQ_RP))) if ARQ_RP.exists() else 0
    npart = len(ler(ARQ_PART)) if ARQ_PART.exists() else 0

    def tier(d):
        t = (d.get("tier") or "").strip().upper()
        return '<span class="tier t%s">%s</span>' % (t or "x", html.escape(t or "–"))

    corpo = []
    for i, (d, p) in enumerate(linhas, 1):
        cap = d.get("capitao", "").strip().lower() == "sim"
        pouca = p.get("poucas_partidas") == "sim"
        pos = '<span class="medalha m%d">%d</span>' % (i, i) if i <= 3 else str(i)
        lcp = f(p["LCP"])
        cels = "".join('<td class="pil %s">%.2f%s</td>' % (faixa(f(p[k])), f(p[k]), barra(f(p[k])))
                       for k in pilares)
        corpo.append(
            '<tr class="%s"><td class="pos">%s</td>'
            '<td class="nome">%s%s%s</td><td>%s</td><td class="fun">%s</td>'
            '<td class="lcp %s">%.2f</td>%s'
            '<td class="b1">%.1f</td><td>%.2f</td><td>%.0f%%</td><td>%.0f%%</td><td>%.0f%%</td>'
            '<td class="b1 dim">%s</td><td class="dim">%s</td>'
            '<td class="b1 clu"><b>%s</b><small>%s</small></td></tr>' % (
                "cap" if cap else "", pos, html.escape(d["lista"]),
                ' <span class="c">C</span>' if cap else "",
                ' <span class="aviso">&#9650;</span>' if pouca else "",
                tier(d), html.escape(p["funcao"]), faixa(lcp), lcp, cels,
                f(p["ADR"]), f(p["KD"]), f(p["HS_pct"]), f(p["KAST_pct"]), f(p["sniper_pct"]) or 0,
                p["partidas"], p["rounds"],
                ("%.0f%%" % f(p["Clutch_pct"])) if f(p.get("Clutch_pct")) is not None else "–",
                ("%s de %s" % (p.get("Clutch_vencidos"), p.get("Clutch_total"))) if p.get("Clutch_total") not in ("", "0", None) else ""))
    for d, _ in fora:
        tracos = "".join('<td class="pil nd">–</td>' for _ in pilares)
        corpo.append(
            '<tr class="sem"><td class="pos">–</td><td class="nome">%s</td><td>%s</td>'
            '<td class="fun">–</td><td class="lcp nd">–</td>%s'
            '<td class="b1">–</td><td>–</td><td>–</td><td>–</td><td>–</td>'
            '<td class="b1 dim">0</td><td class="dim">0</td><td class="b1 clu nd">–</td></tr>'
            % (html.escape(d["lista"]), tier(d), tracos))

    cab_pil = "".join('<th class="pil">%s<small>%s %d%%</small></th>'
                      % (SIGLA[k], k.upper(), round(PESOS_PILARES[k] * 100)) for k in pilares)
    pil_txt = "".join('<p><b>%s</b> %d%% › %s</p>' % (k, round(PESOS_PILARES[k] * 100), DESCRICAO[k])
                      for k in pilares)
    chance_txt = ""
    if ARQ_CHANCE.exists():
        chance_txt = " · ".join("1v%s %.0f%%" % (r["adversarios"], 100 * f(r["chance"])) for r in ler(ARQ_CHANCE))
        chance_txt = ""  # o dono do projeto pediu para tirar esta linha do painel
    sem = [d["lista"] for d, _ in fora]
    sem_txt = (" e ".join(sem) + (" ainda não aparecem" if len(sem) > 1 else " ainda não aparece")
               + " em nenhuma demo") if sem else ""

    css_logo, tem_logo = logo_css()
    return PAGINA % {
        "w": LARGURA, "h": ALTURA, "css_logo": css_logo,
        "logo": '<div class="logo"></div>' if tem_logo else '<div class="logo-txt">LCP</div>',
        "npart": npart, "rnd": rnd, "periodo": periodo(), "npil": len(pilares),
        "marca_teste": ' <span style="font-size:20px;color:#ef5a4a;vertical-align:middle">· PESOS DE TESTE</span>' if TESTE else "",
        "cab_pil": cab_pil, "corpo": "\n".join(corpo), "pil_txt": pil_txt,
        "sem_txt": (" · " + sem_txt) if sem_txt else "",
        "chance_txt": chance_txt, "npil_txt": {4: "QUATRO", 5: "CINCO"}.get(len(pilares), str(len(pilares))),
        "npil_min": {4: "quatro", 5: "cinco"}.get(len(pilares), str(len(pilares))),
    }


TEIA = """<svg class="teia %s" viewBox="0 0 200 200" fill="none" stroke="currentColor" stroke-width="0.8">
<path d="M0 0 L200 30 M0 0 L160 110 M0 0 L110 160 M0 0 L30 200"/>
<path d="M40 6 Q36 26 32 44 Q24 40 6 40 M80 12 Q70 48 64 88 Q46 74 12 80 M120 18 Q104 70 96 130 Q66 108 18 120 M160 24 Q138 92 128 172 Q86 140 24 160"/>
</svg>"""

MORCEGO = """<svg class="morcego" style="%s" viewBox="0 0 40 16" fill="currentColor">
<path d="M20 5c1-2 2-3 2-3l1 3c3-2 8-3 13-1-3 1-5 3-5 6-2-2-5-2-7 0-1-1-3-1-4 0-1-1-3-1-4 0-2-2-5-2-7 0 0-3-2-5-5-6 5-2 10-1 13 1l1-3s1 1 2 3z"/>
</svg>"""

PAGINA = ("""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>LCP Rating - Guia do Draft</title>
<style>
@page { size: %(w)dpx %(h)dpx; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; background: #07060a; }
body { width: %(w)dpx; height: %(h)dpx; padding: 28px 30px; color: #e9e4dc;
  font: 13px/1.35 "Segoe UI", system-ui, sans-serif; overflow: hidden;
  -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.quadro { position: relative; border: 1px solid #3a2a1c; height: 100%%; overflow: hidden;
  background: radial-gradient(ellipse 60%% 40%% at 50%% 0%%, rgba(120, 60, 160, .10), transparent 70%%),
              radial-gradient(ellipse 50%% 30%% at 50%% 100%%, rgba(230, 110, 30, .10), transparent 70%%),
              linear-gradient(#121015, #0e0c11);
  box-shadow: 0 0 0 1px #000, 0 0 60px rgba(230, 120, 40, .08) inset; }
%(css_logo)s
.logo-txt { font: italic 900 78px/1 Bahnschrift, sans-serif; color: #e8b437; }
.topo { position: relative; height: 196px; border: 2px solid #c99a3b; border-bottom-color: #a6773a;
  background: radial-gradient(circle at 80%% 34%%, rgba(255, 214, 140, .22) 0, rgba(255, 170, 80, .07) 70px, transparent 160px),
              radial-gradient(ellipse at 15%% 120%%, #4a2a12 0%%, transparent 55%%),
              radial-gradient(ellipse at 60%% -30%%, #2c1f3a 0%%, transparent 60%%),
              linear-gradient(#0c0a12, #120d10);
  overflow: hidden; }
.estrelas { position: absolute; inset: 0;
  background-image: radial-gradient(1px 1px at 22%% 18%%, #fff8 50%%, transparent 51%%),
    radial-gradient(1px 1px at 34%% 62%%, #fff6 50%%, transparent 51%%), radial-gradient(1.5px 1.5px at 47%% 12%%, #fff9 50%%, transparent 51%%),
    radial-gradient(1px 1px at 58%% 40%%, #fff5 50%%, transparent 51%%), radial-gradient(1px 1px at 66%% 15%%, #fff8 50%%, transparent 51%%),
    radial-gradient(1.5px 1.5px at 73%% 70%%, #fff6 50%%, transparent 51%%), radial-gradient(1px 1px at 91%% 22%%, #fff7 50%%, transparent 51%%),
    radial-gradient(1px 1px at 12%% 75%%, #fff5 50%%, transparent 51%%), radial-gradient(1px 1px at 28%% 35%%, #fff6 50%%, transparent 51%%); }
.lua { position: absolute; right: 230px; top: 22px; width: 92px; height: 92px; border-radius: 50%%;
  background: radial-gradient(circle at 35%% 35%%, #fff6dc, #f3d69a 45%%, #d9a95a 80%%, #b98240);
  box-shadow: 0 0 40px 10px rgba(255, 200, 110, .28), 0 0 120px 30px rgba(255, 160, 60, .12); }
.lua i { position: absolute; border-radius: 50%%; background: rgba(170, 120, 60, .35); }
.nevoa { position: absolute; left: 0; right: 0; bottom: 0; height: 70px;
  background: linear-gradient(transparent, rgba(160, 120, 180, .10) 60%%, rgba(200, 160, 200, .14)); }
.galho { position: absolute; left: 300px; top: -4px; width: 260px; height: 120px; color: #050407; opacity: .85; }
.teia { position: absolute; width: 200px; height: 200px; color: rgba(225, 205, 175, .22); }
.teia.e { left: -6px; top: -6px; }
.teia.d { right: -6px; top: -6px; transform: scaleX(-1); }
.morcego { position: absolute; width: 26px; color: #060508; filter: drop-shadow(0 0 2px rgba(255, 190, 110, .25)); }
.marca { position: absolute; left: 36px; top: 34px; }
.marca p { margin: 8px 0 0; font: 600 10px Bahnschrift, sans-serif; letter-spacing: 3.5px; color: #c9b9a0; }
.centro { position: absolute; left: 0; right: 0; top: 34px; text-align: center; }
.selo { display: inline-flex; font: 700 11px Bahnschrift, sans-serif; letter-spacing: 5px; }
.selo span { padding: 3px 8px 3px 13px; }
.selo .a { background: #e46a17; color: #1a0f08; }
.selo .b { background: #f2b33a; color: #1a0f08; }
h1 { margin: 12px 0 10px; font: 700 60px/1 Bahnschrift, "Segoe UI", sans-serif; letter-spacing: 2px;
  background: linear-gradient(#fff9e8 10%%, #f6d27a 55%%, #c98a2c 95%%); -webkit-background-clip: text; background-clip: text;
  color: transparent; filter: drop-shadow(0 0 14px rgba(240, 170, 60, .35)) drop-shadow(0 2px 0 #3a2208); }
.centro p { margin: 0; font: 600 12px Bahnschrift, sans-serif; letter-spacing: 6px; color: #d9a646; }
.direita { position: absolute; right: 36px; top: 128px; text-align: right;
  font: 600 11px Bahnschrift, sans-serif; letter-spacing: 3.5px; }
.direita .ab { display: none; }
.direita .n { color: #c9b9a0; }
.direita .s { color: #e8923a; margin-top: 6px; }

table { width: 100%%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
thead th { font: 700 10.5px Bahnschrift, sans-serif; letter-spacing: 1.5px; color: #cfc6b8;
  padding: 7px 4px; text-align: center; background: #141215; }
thead th small { display: block; font: 600 7.5px "Segoe UI", sans-serif; letter-spacing: .6px; color: #7d756d; margin-top: 2px; }
thead tr.grupo th { color: #e8923a; font-size: 9.5px; letter-spacing: 3px; padding: 9px 4px 6px;
  border-bottom: 1px solid #2a2420; background: #19140f; }
thead tr.grupo th.v { background: transparent; }
th.l, td.nome { text-align: left; }
.sep { border-left: 1px solid #2a2420; }
tbody td { padding: 0 4px; height: 43px; text-align: center; border-bottom: 1px solid #1d1a1e;
  font: 600 13.5px "Segoe UI", sans-serif; color: #ece7df; }
tbody tr:nth-child(even) td { background: rgba(255, 255, 255, .012); }
tbody tr.cap td { background: linear-gradient(rgba(232, 146, 58, .10), rgba(232, 146, 58, .04)); }
tbody tr.cap td:first-child { box-shadow: inset 4px 0 0 #e46a17; }
td.pos { width: 44px; color: #8b837a; font-size: 12px; }
.medalha { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 3px;
  font: 700 11px Bahnschrift, sans-serif; color: #1b140c; }
.medalha { border-radius: 50%%; width: 24px; height: 24px; font-size: 12px; box-shadow: 0 0 10px rgba(255, 190, 90, .35), inset 0 -2px 3px rgba(0, 0, 0, .3); }
.m1 { background: radial-gradient(circle at 35%% 30%%, #fff3b8, #e5b53f 55%%, #a8761c); }
.m2 { background: radial-gradient(circle at 35%% 30%%, #ffffff, #c9c6c0 55%%, #86827c); }
.m3 { background: radial-gradient(circle at 35%% 30%%, #ffd6a8, #b9824a 55%%, #7a4a20); }
td.nome { font: 700 14.5px "Segoe UI", sans-serif; white-space: nowrap; padding-left: 10px; }
.c { display: inline-block; background: #e46a17; color: #1a0f08; font: 800 9px Bahnschrift, sans-serif;
  padding: 1px 4px; border-radius: 2px; vertical-align: 2px; margin-left: 3px; }
.aviso { color: #f2a13a; font-size: 11px; margin-left: 2px; }
.tier { display: inline-block; min-width: 21px; padding: 2px 5px; border-radius: 2px;
  font: 800 9.5px Bahnschrift, sans-serif; letter-spacing: .5px; color: #fff; }
.tCAP { background: #e46a17; color: #1a0f08; min-width: 36px; }
.tA { background: #e3b23c; color: #1a1408; } .tB { background: #5b8f3c; }
.tC { background: #3f6e9a; } .tD { background: #6d6585; } .tE { background: #57534f; }
td.fun { color: #e8a052; font-size: 11.5px; font-weight: 700; }
td.lcp { font: 700 22px Bahnschrift, sans-serif; background: rgba(120, 70, 30, .16); text-shadow: 0 0 12px currentColor; }
tbody tr.cap td.lcp { background: rgba(140, 80, 30, .24); }
td.pil { font-size: 13.5px; font-weight: 700; line-height: 1; }
.barra { position: relative; display: block; width: 58px; height: 4px; margin: 5px auto 0; border-radius: 2px;
  background: rgba(255, 255, 255, .06); }
.barra i { position: absolute; top: 0; bottom: 0; border-radius: 2px; background: currentColor; opacity: .85;
  box-shadow: 0 0 6px currentColor; }
.barra b { position: absolute; left: 50%%; top: -2px; width: 1px; height: 8px; background: rgba(255, 255, 255, .35); }
.exc { color: #52d273; } .bom { color: #f0c23a; } .ate { color: #f0913a; } .fra { color: #ef5a4a; }
.nd { color: #5f5850; }
td.dim { color: #8b837a; font-size: 12px; }
td.bait, td.clu { width: 92px; line-height: 1.1; }
td.clu b { display: block; font: 700 15px Bahnschrift, sans-serif; color: #e8c37a; }
td.clu small { display: block; font-size: 9.5px; color: #a99a7d; font-weight: 600; }
td.bait b { display: block; font: 700 15px Bahnschrift, sans-serif; color: #c9a0e8; }
td.bait small { display: block; font-size: 9.5px; color: #9d8fb0; font-weight: 600; }
.textos p.chance { color: #e8a052; margin-top: 4px; }
tr.sem td { color: #6b645d; }
tr.sem td.nome { color: #9b938a; }

.legenda { display: flex; justify-content: space-between; padding: 10px 34px; font-size: 10.5px; color: #a9a097;
  border-bottom: 1px solid #2a2420; }
.legenda b { color: #ece7df; }
.legenda .cores span { margin-left: 18px; }
.legenda .cores i { display: inline-block; width: 7px; height: 7px; border-radius: 50%%; margin-right: 5px; }
.textos { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 34px; padding: 22px 34px 16px; }
.textos h3, .abrev h3 { margin: 0 0 10px; font: 700 11.5px Bahnschrift, sans-serif; letter-spacing: 3px; color: #e8923a;
  display: flex; align-items: center; gap: 10px; }
.textos h3::before, .abrev h3::before { content: "✦"; color: #f2b33a; font-size: 12px; text-shadow: 0 0 8px #f2b33a; }
.textos h3::after, .abrev h3::after { content: ""; flex: 1; height: 1px; background: linear-gradient(90deg, #6a4a24, transparent); }
.textos p { margin: 0 0 5px; font-size: 11.5px; color: #b9b0a6; }
.textos p b { color: #ece7df; }
.abrev { margin: 0 34px; padding: 16px 0 14px; border-top: 1px solid #2a2420; }
.abrev .g { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0 30px; font-size: 10.5px; color: #a9a097; }
.abrev .g p { margin: 0 0 2px; }
.abrev b { color: #ece7df; }
.rodape { position: absolute; left: 0; right: 0; bottom: 0; padding: 11px; text-align: center;
  font-size: 11px; color: #c9ad82; background: #0a0809; }
.cemiterio { position: absolute; left: 0; right: 0; bottom: 38px; height: 74px; color: #050406; }
.cemiterio svg { width: 100%%; height: 100%%; display: block; }
.brilho { position: absolute; left: 0; right: 0; bottom: 38px; height: 90px;
  background: radial-gradient(ellipse 20%% 80%% at 12%% 100%%, rgba(255, 140, 40, .22), transparent 70%%),
              radial-gradient(ellipse 20%% 80%% at 88%% 100%%, rgba(255, 140, 40, .22), transparent 70%%),
              radial-gradient(ellipse 40%% 70%% at 50%% 100%%, rgba(150, 100, 170, .12), transparent 70%%); }
</style></head><body>
<div class="quadro">
<div class="topo">
  <div class="estrelas"></div>
  <div class="lua"><i style="left:22px;top:26px;width:16px;height:16px"></i><i style="left:52px;top:46px;width:11px;height:11px"></i>
    <i style="left:34px;top:60px;width:8px;height:8px"></i><i style="left:60px;top:20px;width:7px;height:7px"></i></div>
  <svg class="galho" viewBox="0 0 260 120" fill="currentColor"><path d="M0 0h260v4c-30 2-52 8-70 20-10 6-18 16-30 18 8-8 10-14 6-16-10 10-26 14-40 22 4-8 2-12-4-10-14 10-30 20-40 40-2-14-6-20-12-24-8 6-16 18-20 30 0-16-4-28-10-36-6 6-10 14-12 22-2-12 2-24 10-34C40 22 20 14 0 12z"/></svg>
  """ + TEIA % "e" + TEIA % "d"
    + MORCEGO % "right:262px;top:44px;width:30px" + MORCEGO % "right:206px;top:30px;width:20px"
    + MORCEGO % "right:300px;top:96px;width:18px" + MORCEGO % "right:180px;top:84px;width:24px"
    + MORCEGO % "left:600px;top:20px;width:16px" + MORCEGO % "left:640px;top:150px;width:14px"
    + MORCEGO % "right:560px;top:140px;width:16px" + """
  <div class="nevoa"></div>
  <div class="marca">%(logo)s<p>LAN CHÁCARA PAPETTI</p></div>
  <div class="centro">
    <div class="selo"><span class="a">EDIÇÃO</span><span class="b">HALLOWEEN</span></div>
    <h1>LCP RATING%(marca_teste)s</h1>
    <p>GUIA DO DRAFT · 24/10/2026</p>
  </div>
  <div class="direita"><div class="ab"></div>
    <div class="n">%(npart)s PARTIDAS · %(rnd)s ROUNDS</div>
    <div class="s">ESTATÍSTICAS QUE REVELAM VALOR</div></div>
</div>
<table>
<thead>
<tr class="grupo"><th class="v" colspan="4"></th><th class="sep">NOTA</th><th class="sep" colspan="%(npil)s">PILARES</th>
<th class="sep" colspan="5">NÚMEROS BRUTOS</th><th class="sep" colspan="2">AMOSTRA</th>
<th class="sep" style="letter-spacing:1px;white-space:nowrap">FORA DO LCP</th></tr>
<tr><th>#</th><th class="l" style="padding-left:10px">JOGADOR</th><th>TIER<small>ORGANIZAÇÃO</small></th>
<th>FUNÇÃO<small>MEDIDA</small></th><th class="sep">LCP</th>%(cab_pil)s
<th class="sep">ADR</th><th>K/D</th><th>HS%%</th><th>KAST</th><th>AWP%%</th>
<th class="sep">PART</th><th>RDS</th><th class="sep">CLUTCH<small>%% CONVERTIDO</small></th></tr>
</thead>
<tbody>
%(corpo)s
</tbody></table>
<div class="legenda">
  <div><b style="color:#e8923a">C</b> capitão · <span class="aviso">&#9650;</span> menos de 6 partidas, nota menos firme ·
  LCP e pilares na mesma escala, <b>1.00 = média do grupo</b> · a nota é a média ponderada dos %(npil_min)s pilares</div>
  <div class="cores"><span class="exc"><i style="background:#52d273"></i>≥ 1.10 Excelente</span>
  <span class="bom"><i style="background:#f0c23a"></i>1.00 – 1.09 Bom</span>
  <span class="ate"><i style="background:#f0913a"></i>0.90 – 0.99 Atenção</span>
  <span class="fra"><i style="background:#ef5a4a"></i>&lt; 0.90 Fraco</span></div>
</div>
<div class="textos">
  <div><h3>COMO USAR NO DRAFT</h3>
    <p>O LCP não aponta o "melhor jogador" absoluto. Ele mede o que cada um <b>produz dentro do round</b>,
    com o peso de cada estatística definido pela confiabilidade dela.</p>
    <p style="margin-top:10px">Funciona como o rating da HLTV: <b>1.00 é a média do grupo</b>. Use os pilares para
    montar time equilibrado, não para somar as maiores notas.</p></div>
  <div><h3>OS %(npil_txt)s PILARES</h3>%(pil_txt)s
    <p style="margin-top:10px"><b>Clutch fica fora da nota</b>: a coluna mostra a %% de clutches convertidos em
    round. Só conta quem foi pra cima ou venceu; guardar a arma não conta. Com a amostra atual ainda não separa
    jogador de sorte.</p>%(chance_txt)s</div>
  <div><h3>FUNÇÃO NO TIME</h3>
    <p><b>AWPer</b> › 20%% ou mais das kills de sniper</p>
    <p><b>Lurker</b> › joga longe do time no TR e entra pouco</p>
    <p><b>Entry</b> › destaque em Entry, abre os rounds</p>
    <p><b>Support</b> › destaque em Teamplay: utilitária, flash, assistência</p>
    <p><b>Rifler</b> › destaque em Impact ou Efficiency, ou sem destaque</p>
    <p style="margin-top:10px">Entry, Support e Rifler comparam o jogador <b>com o próprio perfil</b>,
    não com o grupo. IGL fica de fora: liderança não aparece na demo.</p></div>
</div>
<div class="abrev"><h3>LEGENDA DAS ABREVIAÇÕES</h3>
  <div class="g">
    <div><p><b>#</b> posição pelo LCP</p><p><b>C</b> capitão</p><p><b>Tier</b> grupo definido pela organização</p>
      <p><b>KAST</b> %% de rounds com kill, assistência, sobrevivência ou morte trocada</p></div>
    <div><p><b>LCP</b> nota final do LCP Rating</p><p><b>IMP</b> Impact · <b>TEAM</b> Teamplay</p>
      <p><b>EFI</b> Efficiency · <b>ENT</b> Entry</p>
      <p><b>PART</b> partidas na base · <b>RDS</b> rounds na base</p></div>
    <div><p><b>ADR</b> dano médio por round</p><p><b>Entry</b> primeiro duelo do round · <b>First kill</b> primeira kill do round</p>
      <p><b>Utilitária</b> granada, flash, molotov e smoke</p>
      <p><b>Kill em desvantagem</b> feita com o time em menor número</p></div>
    <div><p><b>K/D</b> kills divididas por mortes</p><p><b>HS%%</b> kills na cabeça</p>
      <p><b>AWP%%</b> kills feitas de sniper</p>
      <p><b>Clutch</b> %% convertido, sozinho contra um ou mais; guardar não conta</p></div>
  </div>
</div>
<div class="brilho"></div>
<div class="cemiterio"><svg viewBox="0 0 1600 74" preserveAspectRatio="none" fill="currentColor">
<path d="M0 74V58c40-6 80-4 120 0 60 6 120 2 180-4 80-8 160-6 240 2 90 8 180 6 270-2 100-9 200-6 300 2 90 7 180 6 270-2 80-6 150-4 220 2V74z"/>
<path d="M70 62V38a14 14 0 0 1 28 0v24zM150 62V30h4v-8h6v8h4v32zM260 62V42a10 10 0 0 1 20 0v20zM420 62V34a16 16 0 0 1 32 0v28z
M560 62V44h3v-6h4v6h3v18zM760 62V36a12 12 0 0 1 24 0v26zM940 62V40a15 15 0 0 1 30 0v22zM1100 62V32h4v-9h6v9h4v30z
M1240 62V42a11 11 0 0 1 22 0v20zM1380 62V36a14 14 0 0 1 28 0v26zM1500 62V44h3v-6h4v6h3v18z"/>
<path d="M330 62c-2-18 2-34 12-48-4 14-4 30 0 48zM342 30c8-6 16-6 24-2-8 0-16 2-24 6zM1180 62c2-20-2-36-14-50 6 16 6 32 4 50zM1168 28c-8-4-16-4-24 0 8 0 16 2 24 4z"/>
</svg></div>
<div style="position:absolute;left:150px;bottom:44px;font-size:30px;filter:drop-shadow(0 0 10px rgba(255,140,40,.8))">&#127875;</div>
<div style="position:absolute;right:150px;bottom:44px;font-size:30px;filter:drop-shadow(0 0 10px rgba(255,140,40,.8))">&#127875;</div>
<div class="rodape">Base: %(npart)s partidas, %(rnd)s rounds, %(periodo)s%(sem_txt)s ·
O LCP mede performance estatística. Liderança, call e leitura de jogo não são medidos.</div>
</div>
</body></html>
""")


def edge():
    for e in EDGE:
        if os.path.exists(e):
            return e
    return None


def main():
    PASTA_OUT.mkdir(parents=True, exist_ok=True)
    arq_html = (PASTA_OUT / "LCP_Painel.html").resolve()
    arq_html.write_text(montar(), encoding="utf-8")
    print("Gravado: " + str(arq_html))

    e = edge()
    if not e:
        print("Edge nao encontrado: abra o HTML no navegador e salve como PDF.")
        return

    url = arq_html.as_uri()
    comum = [e, "--headless", "--disable-gpu", "--hide-scrollbars", "--no-first-run"]
    png = (PASTA_OUT / "LCP_Painel.png").resolve()
    pdf = (PASTA_OUT / "LCP_Painel.pdf").resolve()
    subprocess.run(comum + ["--window-size=%d,%d" % (LARGURA, ALTURA), "--force-device-scale-factor=1.5",
                            "--screenshot=" + str(png), url], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    subprocess.run(comum + ["--no-pdf-header-footer", "--print-to-pdf=" + str(pdf), url],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    for a in (png, pdf):
        print(("Gravado: " if a.exists() else "FALHOU: ") + str(a))


if __name__ == "__main__":
    main()
