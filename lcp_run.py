"""
lcp_run.py - processa uma fila de demos de ponta a ponta.

Como usar:
  1. Coloque as demos em uma destas pastas:
       fila\\campeonato
       fila\\calibracao
  2. Rode:  py lcp_run.py

Cada partida vai para saidas\\<codigo_da_partida>\\
Partidas ja processadas sao puladas.
Demos ilegiveis sao separadas e NAO interrompem o lote.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
from demoparser2 import DemoParser

os.environ["PYTHONIOENCODING"] = "utf-8"

CADEIA = [
    "lcp_parser.py",
    "round_results.py",
    "round_player_stats.py",
    "round_player_context.py",
    "trade_parser.py",
    "trade_events_builder.py",
    "round_player_trade_context.py",
    "round_player_impact_context.py",
    "round_state_probe.py",
    "kill_leverage_probe.py",
    "kill_leverage_model.py",
    "clutch_parser.py",
    "duels_parser.py",
    "utility_parser.py",
    "damage_parser.py",
]

PASTA_FILA = Path("fila")
PASTA_CAMPEONATO = PASTA_FILA / "campeonato"
PASTA_CALIBRACAO = PASTA_FILA / "calibracao"
PASTA_ILEGIVEIS = PASTA_FILA / "ilegiveis"
PASTA_DEMOS = Path("demos")
PASTA_SAIDA = Path("saidas")


def preparar_fila():
    PASTA_CAMPEONATO.mkdir(parents=True, exist_ok=True)
    PASTA_CALIBRACAO.mkdir(parents=True, exist_ok=True)
    PASTA_DEMOS.mkdir(exist_ok=True)

    for demo in list(PASTA_FILA.glob("*.dem")) + list(PASTA_DEMOS.glob("*.dem")):
        destino = PASTA_CALIBRACAO / demo.name

        if not destino.exists():
            shutil.move(str(demo), str(destino))

    fila = []
    vistos = set()

    for pasta, tipo in [(PASTA_CAMPEONATO, "campeonato"),
                        (PASTA_CALIBRACAO, "calibracao")]:
        for demo in sorted(pasta.glob("*.dem")):
            if demo.stem in vistos:
                continue

            vistos.add(demo.stem)
            fila.append((demo, tipo))

    return fila


def limpar_csvs():
    """Apaga CSV solto na raiz antes de cada demo, para nenhum script ler
    sobra de outra partida. Os CSVs de cada partida ja ficam em saidas/<codigo>."""
    for csv in sorted(Path(".").glob("*.csv")):
        csv.unlink()


def extrair_identidades(caminho_demo, destino):
    parser = DemoParser(str(caminho_demo))

    try:
        mapa = parser.parse_header().get("map_name", "desconhecido")
    except Exception:
        mapa = "desconhecido"

    eventos = parser.parse_event("player_death")

    if not isinstance(eventos, pd.DataFrame) or eventos.empty:
        return mapa, 0

    pares = []

    combinacoes = [
        ("attacker_name", "attacker_steamid"),
        ("user_name", "user_steamid"),
        ("assister_name", "assister_steamid"),
    ]

    for coluna_nome, coluna_id in combinacoes:
        if coluna_nome in eventos.columns and coluna_id in eventos.columns:
            parcial = eventos[[coluna_nome, coluna_id]].copy()
            parcial.columns = ["player", "steamid"]
            pares.append(parcial)

    if not pares:
        return mapa, 0

    tabela = pd.concat(pares, ignore_index=True)
    tabela = tabela.dropna()
    tabela = tabela[tabela["steamid"].astype(str) != "0"]
    tabela["steamid"] = tabela["steamid"].astype(str)
    tabela = tabela.drop_duplicates()
    tabela = tabela.sort_values(["steamid", "player"])

    tabela.to_csv(destino / "player_identity.csv", index=False)

    return mapa, len(tabela)


def processar(demo_na_fila, tipo, posicao, total):
    codigo = demo_na_fila.stem
    destino = PASTA_SAIDA / codigo
    origem = demo_na_fila.parent

    print()
    print("=" * 70)
    print("PARTIDA " + str(posicao) + " de " + str(total) + "  [" + tipo + "]")
    print(codigo)
    print("=" * 70)

    if (destino / "resumo_partida.txt").exists():
        print("Ja processada anteriormente. Pulando.")
        return "pulada", None

    limpar_csvs()

    for sobra in PASTA_DEMOS.glob("*.dem"):
        shutil.move(str(sobra), str(PASTA_CALIBRACAO / sobra.name))

    ativa = PASTA_DEMOS / demo_na_fila.name
    shutil.move(str(demo_na_fila), str(ativa))

    destino.mkdir(parents=True, exist_ok=True)

    inicio = time.time()

    try:
        mapa, qtd = extrair_identidades(ativa, destino)
    except Exception as e:
        print("DEMO ILEGIVEL: " + str(e)[:60])
        print("O arquivo nao pode ser lido pelo parser.")

        PASTA_ILEGIVEIS.mkdir(parents=True, exist_ok=True)
        shutil.move(str(ativa), str(PASTA_ILEGIVEIS / ativa.name))
        shutil.rmtree(destino, ignore_errors=True)

        print("Movida para: " + str(PASTA_ILEGIVEIS))
        return "ilegivel", None

    print("Mapa: " + str(mapa) + "  |  jogadores identificados: " + str(qtd))
    print()

    falhas = []

    for indice, script in enumerate(CADEIA, start=1):
        marcador = "[" + str(indice).rjust(2) + "/" + str(len(CADEIA)) + "]"

        if not Path(script).exists():
            print(marcador + " PULADO  " + script)
            falhas.append(script + " (nao existe)")
            continue

        print(marcador + " " + script.ljust(34), end=" ", flush=True)

        parcial = time.time()

        try:
            resultado = subprocess.run(
                [sys.executable, script],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
            codigo_saida = resultado.returncode
            saida = (resultado.stdout or "") + "\n" + (resultado.stderr or "")
        except subprocess.TimeoutExpired:
            codigo_saida = -1
            saida = "Tempo limite de 10 minutos excedido."
        except Exception as e:
            codigo_saida = -1
            saida = str(e)

        duracao = round(time.time() - parcial)

        if codigo_saida == 0:
            print("ok (" + str(duracao) + "s)")
        else:
            print("FALHOU (" + str(duracao) + "s)")
            falhas.append(script)

            log = destino / ("erro_" + script.replace(".py", "") + ".txt")
            log.write_text(saida, encoding="utf-8")

    # move (nao copia): a raiz do projeto nao fica com dados de jogador
    copiados = 0

    for csv in sorted(Path(".").glob("*.csv")):
        shutil.move(str(csv), str(destino / csv.name))
        copiados += 1

    duracao_total = round(time.time() - inicio)

    resumo = [
        "codigo=" + codigo,
        "tipo=" + tipo,
        "mapa=" + str(mapa),
        "demo=" + demo_na_fila.name,
        "jogadores=" + str(qtd),
        "csvs=" + str(copiados),
        "segundos=" + str(duracao_total),
        "falhas=" + (", ".join(falhas) if falhas else "nenhuma"),
    ]

    (destino / "resumo_partida.txt").write_text("\n".join(resumo), encoding="utf-8")

    shutil.move(str(ativa), str(origem / ativa.name))

    print()
    print("CSVs arquivados: " + str(copiados) + "  |  tempo: " + str(duracao_total) + "s")

    if falhas:
        print("Falhas: " + ", ".join(falhas))
        return "com_falha", mapa

    return "ok", mapa


def main():
    inicio = time.time()

    print("=" * 70)
    print("LCP RUN - processamento em lote")
    print("=" * 70)

    fila = preparar_fila()

    if not fila:
        print()
        print("Nenhuma demo encontrada.")
        print("Coloque os arquivos .dem em: " + str(PASTA_CALIBRACAO.resolve()))
        sys.exit(1)

    campeonato = sum(1 for _, t in fila if t == "campeonato")

    print()
    print("Campeonato: " + str(campeonato) +
          "  |  Calibracao: " + str(len(fila) - campeonato))

    resultados = []

    for posicao, (demo, tipo) in enumerate(fila, start=1):
        try:
            status, mapa = processar(demo, tipo, posicao, len(fila))
        except KeyboardInterrupt:
            print()
            print("Interrompido pelo usuario.")
            break
        except Exception as e:
            print()
            print("ERRO INESPERADO: " + str(e)[:70])
            print("Seguindo para a proxima partida.")

            for sobra in PASTA_DEMOS.glob("*.dem"):
                shutil.move(str(sobra), str(PASTA_CALIBRACAO / sobra.name))

            status, mapa = "erro", None

        resultados.append((demo.stem, tipo, status, mapa))

    print()
    print("=" * 70)
    print("RESUMO GERAL")
    print("=" * 70)

    for codigo, tipo, status, mapa in resultados:
        if status == "pulada":
            continue

        print(status.ljust(12) + tipo.ljust(12) +
              str(mapa or "").ljust(12) + codigo)

    contagem = {}

    for r in resultados:
        contagem[r[2]] = contagem.get(r[2], 0) + 1

    print()
    print("Sem falha: " + str(contagem.get("ok", 0)) +
          "  |  Com falha: " + str(contagem.get("com_falha", 0)) +
          "  |  Ilegiveis: " + str(contagem.get("ilegivel", 0)) +
          "  |  Erros: " + str(contagem.get("erro", 0)) +
          "  |  Puladas: " + str(contagem.get("pulada", 0)))
    print("Tempo total: " + str(round(time.time() - inicio)) + "s")
    print("=" * 70)


if __name__ == "__main__":
    main()