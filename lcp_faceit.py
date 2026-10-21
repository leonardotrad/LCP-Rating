"""
lcp_faceit.py - busca data e apelidos de cada partida na API da FACEIT.

Gera em base:
  faceit_cache.json     dados brutos, para nao consultar duas vezes
  lcp_apelidos.csv      steamid + apelido mais recente
  lcp_datas.csv         partida + data + competicao

Rode depois de processar partidas novas:  py lcp_faceit.py
"""

import json
import os
import sys
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# apelido com caractere especial nao pode derrubar o script no terminal do Windows
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


PASTA_BASE = Path("base")
CACHE = PASTA_BASE / "faceit_cache.json"
PASTA_SAIDA = Path("saidas")

PAUSA = 0.3


def ler_chave():
    env = Path(".env")

    if not env.exists():
        return None

    for linha in env.read_text(encoding="utf-8", errors="replace").splitlines():
        linha = linha.strip()

        if not linha or linha.startswith("#") or "=" not in linha:
            continue

        nome, valor = linha.split("=", 1)

        if "FACEIT" in nome.upper():
            return valor.strip().strip('"').strip("'")

    return None


def id_da_partida(codigo):
    achado = re.match(r"(1-[0-9a-fA-F-]{36})", codigo)
    return achado.group(1) if achado else None


def buscar(match_id, chave):
    url = "https://open.faceit.com/data/v4/matches/" + match_id
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + chave)

    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    print("=" * 68)
    print("LCP FACEIT - datas e apelidos")
    print("=" * 68)
    print()

    chave = ler_chave()

    if not chave:
        print("ERRO: chave da FACEIT nao encontrada no .env")
        return

    PASTA_BASE.mkdir(exist_ok=True)

    cache = {}

    if CACHE.exists():
        cache = json.loads(CACHE.read_text(encoding="utf-8"))

    codigos = []

    for pasta in sorted(PASTA_SAIDA.iterdir()):
        if (pasta / "resumo_partida.txt").exists():
            codigos.append(pasta.name)

    if not codigos:
        print("Nenhuma partida em saidas.")
        return

    novos = 0
    falhas = []

    for codigo in codigos:
        match_id = id_da_partida(codigo)

        if not match_id:
            falhas.append(codigo + " (id nao reconhecido)")
            continue

        if match_id in cache:
            continue

        try:
            cache[match_id] = buscar(match_id, chave)
            novos += 1
            print("  buscado: " + match_id)
            time.sleep(PAUSA)
        except Exception as e:
            falhas.append(codigo + " (" + str(e)[:40] + ")")

    CACHE.write_text(json.dumps(cache), encoding="utf-8")

    print()
    print("Partidas consultadas agora: " + str(novos))
    print("Partidas no cache: " + str(len(cache)))

    if falhas:
        print()
        print("Falhas:")
        for f in falhas:
            print("   " + f)

    linhas_data = []
    linhas_jog = []

    for codigo in codigos:
        match_id = id_da_partida(codigo)
        dados = cache.get(match_id)

        if not dados:
            continue

        inicio = dados.get("started_at") or dados.get("finished_at")
        quando = None

        if inicio:
            quando = datetime.fromtimestamp(int(inicio), tz=timezone.utc)

        linhas_data.append({
            "partida": codigo,
            "match_id": match_id,
            "data": quando.strftime("%Y-%m-%d %H:%M") if quando else None,
            "timestamp": int(inicio) if inicio else None,
            "competicao": dados.get("competition_name"),
        })

        for info in (dados.get("teams") or {}).values():
            for jogador in info.get("roster", []):
                steam = jogador.get("game_player_id")
                apelido = jogador.get("nickname")

                if not steam or not apelido:
                    continue

                linhas_jog.append({
                    "steamid": str(steam),
                    "apelido": apelido,
                    "timestamp": int(inicio) if inicio else 0,
                    "partida": codigo,
                })

    datas = pd.DataFrame(linhas_data).sort_values("timestamp")
    datas.to_csv(PASTA_BASE / "lcp_datas.csv", index=False)

    jog = pd.DataFrame(linhas_jog)

    if jog.empty:
        print("Nenhum jogador retornado pela API.")
        return

    jog = jog.sort_values("timestamp")
    recentes = jog.groupby("steamid").tail(1)[["steamid", "apelido", "partida"]]
    recentes = recentes.rename(columns={"partida": "partida_do_apelido"})
    recentes.to_csv(PASTA_BASE / "lcp_apelidos.csv", index=False)

    historico = jog.groupby("steamid")["apelido"].agg(lambda s: sorted(set(s)))
    trocaram = historico[historico.apply(len) > 1]

    print()
    print("Jogadores: " + str(len(recentes)))
    print("Trocaram de apelido: " + str(len(trocaram)))

    for steam, nomes in trocaram.items():
        atual = recentes[recentes.steamid == steam]["apelido"].iloc[0]
        anteriores = [n for n in nomes if n != atual]
        print("   " + atual + "  (antes: " + ", ".join(anteriores) + ")")

    if len(datas):
        print()
        print("Periodo das partidas: " + str(datas["data"].iloc[0]) +
              "  ate  " + str(datas["data"].iloc[-1]))
        print("Competicoes: " + ", ".join(sorted(set(
            str(c) for c in datas["competicao"].dropna()))))


if __name__ == "__main__":
    main()