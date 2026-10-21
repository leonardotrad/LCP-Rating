"""
trade_events_builder.py - gera o trade_events.csv que faltava no projeto.

Reutiliza a funcao de deteccao de trades do proprio trade_parser.py,
sem reprocessar a demo. Valida contra o arquivo antigo, se existir.

Rodar depois do trade_parser.py.
"""

import sys
from pathlib import Path

import pandas as pd

from trade_parser import find_trades_for_window

ENTRADA_MORTES = Path("trade_debug_deaths.csv")
ENTRADA_ENTRY = Path("trade_entry_rounds.csv")
SAIDA = Path("trade_events.csv")
GABARITO = Path("csvs_anteriores") / "trade_events.csv"

JANELAS = [2.0, 3.0, 4.0, 5.0]
JANELA_PADRAO = 3.0


def comparar(gerado, referencia):
    if len(gerado) != len(referencia):
        return False

    colunas = list(referencia.columns)

    if set(colunas) != set(gerado.columns):
        return False

    a = gerado[colunas].astype(str).reset_index(drop=True)
    b = referencia[colunas].astype(str).reset_index(drop=True)

    return a.equals(b)


def main():
    print("=" * 70)
    print("TRADE EVENTS BUILDER")
    print("=" * 70)
    print()

    for arquivo in (ENTRADA_MORTES, ENTRADA_ENTRY):
        if not arquivo.exists():
            print("ERRO: " + str(arquivo) + " nao encontrado.")
            print("Rode o trade_parser.py antes deste script.")
            sys.exit(1)

    mortes = pd.read_csv(ENTRADA_MORTES)
    entry = pd.read_csv(ENTRADA_ENTRY)

    print("Mortes carregadas: " + str(len(mortes)))
    print("Rounds com entry: " + str(len(entry)))
    print()

    referencia = None

    if GABARITO.exists():
        referencia = pd.read_csv(GABARITO)
        print("Gabarito encontrado: " + str(len(referencia)) + " linhas")
        print()

    janela_escolhida = None
    resultados = {}

    for janela in JANELAS:
        trades = find_trades_for_window(mortes, entry, janela)
        resultados[janela] = trades

        marca = ""

        if referencia is not None and comparar(trades, referencia):
            marca = "  <-- IDENTICO AO GABARITO"
            janela_escolhida = janela

        print("Janela " + str(janela) + "s: " + str(len(trades)) + " trades" + marca)

    print()

    if janela_escolhida is None:
        janela_escolhida = JANELA_PADRAO

        if referencia is None:
            print("Sem gabarito para comparar.")
            print("Usando a janela padrao de " + str(JANELA_PADRAO) + "s.")
        else:
            print("ATENCAO: nenhuma janela reproduziu o arquivo antigo.")
            print("Usando a janela padrao de " + str(JANELA_PADRAO) + "s.")
            print("Me avise antes de processar as outras partidas.")
    else:
        print("Janela original identificada: " + str(janela_escolhida) + "s")

    final = resultados[janela_escolhida]
    final.to_csv(SAIDA, index=False)

    print()
    print("-" * 70)
    print("Arquivo gerado: " + str(SAIDA))
    print("Linhas: " + str(len(final)))
    print("Janela usada: " + str(janela_escolhida) + "s")
    print("-" * 70)


if __name__ == "__main__":
    main()