# -*- coding: utf-8 -*-
r"""
lcp_releverage.py - refaz so a cadeia de leverage, sem reler as demos.

POR QUE ISSO EXISTE
Quando a correcao mexe apenas no round_state_probe.py, no
kill_leverage_probe.py ou no kill_leverage_model.py, nao e preciso apagar a
pasta saidas e reprocessar as demos. Esses tres scripts nao leem demo: eles
leem CSVs que ja estao guardados em saidas\<codigo>\.

Este script, para cada partida:
  1. limpa os CSVs soltos na pasta
  2. copia os CSVs guardados daquela partida de volta para a pasta
  3. roda os tres scripts
  4. devolve os CSVs gerados para saidas\<codigo>\

Se algum script falhar na primeira partida, ele para e mostra o erro inteiro,
em vez de repetir a falha 39 vezes.

Depois de rodar, siga normalmente:
    py lcp_base.py
    py lcp_contas.py
    py lcp_dano.py
    py lcp_rating.py
    py lcp_painel.py
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# apelido com caractere especial nao pode derrubar o script no terminal do Windows
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


CADEIA = [
    "round_state_probe.py",
    "kill_leverage_probe.py",
    "kill_leverage_model.py",
]

PASTA_SAIDAS = Path("saidas")
PASTA_GUARDADOS = Path("csvs_anteriores")

os.environ["PYTHONIOENCODING"] = "utf-8"


def limpar_csvs():
    soltos = sorted(Path(".").glob("*.csv"))
    if not soltos:
        return
    PASTA_GUARDADOS.mkdir(exist_ok=True)
    for arq in soltos:
        destino = PASTA_GUARDADOS / arq.name
        if destino.exists():
            destino.unlink()
        shutil.move(str(arq), str(destino))


def processar(pasta, posicao, total):
    codigo = pasta.name
    print()
    print("=" * 70)
    print("PARTIDA " + str(posicao) + " de " + str(total))
    print(codigo)
    print("=" * 70)

    guardados = sorted(pasta.glob("*.csv"))
    if not guardados:
        print("Sem CSVs guardados. Pulando.")
        return "sem_csv", []

    limpar_csvs()

    for arq in guardados:
        shutil.copy2(arq, Path(".") / arq.name)

    avisos = []
    inicio = time.time()

    for indice, script in enumerate(CADEIA, start=1):
        marcador = "[" + str(indice) + "/" + str(len(CADEIA)) + "]"

        if not Path(script).exists():
            print(marcador + " " + script.ljust(28) + " NAO EXISTE")
            return "falhou", avisos

        print(marcador + " " + script.ljust(28), end=" ", flush=True)

        try:
            r = subprocess.run(
                [sys.executable, script],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            print("TEMPO EXCEDIDO")
            return "falhou", avisos

        saida = (r.stdout or "") + "\n" + (r.stderr or "")

        if r.returncode != 0:
            print("FALHOU")
            print()
            print("-" * 70)
            print("ERRO EM " + script)
            print("-" * 70)
            print(saida[-4000:])
            return "falhou", avisos

        print("ok")

        for linha in saida.splitlines():
            t = linha.strip()
            if t.startswith("ATENCAO") or t.startswith("ATENÇÃO"):
                avisos.append(codigo + " | " + script + " | " + t)
            if "recuperadas pelo" in t or "sem contagem de vivos" in t:
                avisos.append(codigo + " | " + t)

    copiados = 0
    for arq in sorted(Path(".").glob("*.csv")):
        shutil.copy2(arq, pasta / arq.name)
        copiados += 1

    print("CSVs devolvidos: %d  |  tempo: %ds" % (copiados, round(time.time() - inicio)))
    return "ok", avisos


def main():
    if not PASTA_SAIDAS.is_dir():
        print("Nao encontrei a pasta saidas.")
        sys.exit(1)

    pastas = sorted(p for p in PASTA_SAIDAS.iterdir() if p.is_dir())
    if not pastas:
        print("Nenhuma partida em saidas.")
        sys.exit(1)

    print("=" * 70)
    print("LCP RELEVERAGE - refaz a cadeia de leverage sem reler as demos")
    print("=" * 70)
    print()
    print("Partidas: %d" % len(pastas))

    inicio = time.time()
    contagem = {}
    todos_avisos = []

    for posicao, pasta in enumerate(pastas, start=1):
        status, avisos = processar(pasta, posicao, len(pastas))
        contagem[status] = contagem.get(status, 0) + 1
        todos_avisos.extend(avisos)

        if status == "falhou":
            print()
            print("Parando aqui para voce ver o erro.")
            print("Nada foi perdido: os CSVs antigos continuam em saidas.")
            sys.exit(1)

    print()
    print("=" * 70)
    print("RESUMO")
    print("=" * 70)
    print("Refeitas: %d  |  Sem CSV: %d" % (contagem.get("ok", 0), contagem.get("sem_csv", 0)))
    print("Tempo total: %ds" % round(time.time() - inicio))

    if todos_avisos:
        print()
        print("=" * 70)
        print("AVISOS (%d)" % len(todos_avisos))
        print("=" * 70)
        for a in todos_avisos[:60]:
            print("   " + a)
        if len(todos_avisos) > 60:
            print("   ... e mais %d" % (len(todos_avisos) - 60))

    print()
    print("Agora rode:")
    print("    py lcp_base.py")
    print("    py lcp_contas.py")
    print("    py lcp_dano.py")
    print("    py lcp_rating.py")
    print("    py lcp_painel.py")


if __name__ == "__main__":
    main()