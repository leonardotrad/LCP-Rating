"""
round_classifier.py - classificacao de rounds ancorada em round_end.

Regra: sao oficiais os rounds que terminam depois do ultimo
round_announce_match_start. Descarta faca e aquecimento e
funciona mesmo quando round_poststart esta incompleto.

Os eventos necessarios sao lidos da demo que estiver na pasta
demos, entao os parsers nao precisam ser alterados.

Saida (mesmo contrato da versao anterior):
event_index, tick_start, tick_end, total_rounds_played,
half, is_warmup_period, round_type, kill_events

FRONTEIRA DOS ROUNDS
A kill que encerra um round acontece no mesmo tick do evento round_end.
Antes, este modulo publicava tick_start igual ao tick de round_end do round
anterior. Como os consumidores filtram as kills por tick >= tick_start, essa
kill final caia no round seguinte: 391 kills em 549 rounds, sempre a kill
decisiva. Isso nao perdia nem duplicava kill nenhuma, os totais por jogador
continuavam certos, mas embaralhava tudo que depende de round, com destaque
para o entry (a primeira kill do round passava a ser a ultima do anterior),
o multi-kill, o estado de vivos do clutch e o leverage.

Agora o round publicado vai de tick_start = fim_anterior + 1 ate
tick_end = fim_real + 1, ou seja, o intervalo meio aberto [tick_start,
tick_end) contem exatamente os ticks (fim_anterior, fim_real], que e a mesma
regra que este modulo sempre usou para contar kill_events.

O deslocamento de um tick foi conferido na base: existem 366 kills no tick
exato de fim de round e nenhuma no tick seguinte, entao nenhum consumidor
passa a contar a mesma kill duas vezes, use ele [inicio, fim) ou
[inicio, fim].

INICIO DO ROUND (corrigido em 20/10)
O round comecava logo depois do round_end anterior. Com isso:
  - o round 1 comecava no tick 0 quando o aquecimento nao tem round_end, e
    engolia o aquecimento inteiro (ate 107 kills num round 1, 986 no total);
  - a kill do pos-round (depois do round_end, antes do proximo round) caia no
    round seguinte: jogador morrendo duas vezes no mesmo round, entry falso
    (a primeira "kill" do round era a exit frag do anterior), multi-kill e
    clutch errados. 125 kills.
Agora o round comeca no round_freeze_end (o fim do freeze time, quando o
jogo libera). Kill de pos-round e de aquecimento fica fora de qualquer round.
Se faltar o freeze_end de algum round, cai na regra antiga para aquele round,
mas nunca antes do "ao vivo" (round_announce_match_start).

ROUND FANTASMA (corrigido em 21/10)
round_end sem vencedor depois do "ao vivo" e restart ou pausa do servidor:
4 rounds em 3 partidas de LAN, sem kill e com jogador morto duas vezes pelo
"world". Ficam de fora.
"""

from pathlib import Path

import pandas as pd
from demoparser2 import DemoParser

TIPOS_OFICIAIS = {"PISTOL", "NORMAL", "OVERTIME"}

ROUNDS_POR_HALF = 12
ROUNDS_REGULAMENTARES = 24
ROUNDS_POR_HALF_OT = 3

_cache = {}


def _para_tabela(dados):
    if dados is None:
        return pd.DataFrame()

    if isinstance(dados, pd.DataFrame):
        return dados

    if isinstance(dados, list):
        if not dados:
            return pd.DataFrame()
        return pd.DataFrame(dados)

    return pd.DataFrame()


def _ticks_de(eventos):
    tabela = _para_tabela(eventos)

    if tabela.empty or "tick" not in tabela.columns:
        return []

    return sorted(int(t) for t in tabela["tick"].dropna().tolist())


def _demo_da_pasta():
    demos = sorted(Path("demos").glob("*.dem"))

    if not demos:
        raise FileNotFoundError(
            "Nenhum arquivo .dem encontrado na pasta demos."
        )

    if len(demos) > 1:
        raise RuntimeError(
            "Ha mais de uma demo na pasta demos. Deixe apenas uma."
        )

    return demos[0]


def _eventos_da_demo():
    caminho = _demo_da_pasta()
    chave = str(caminho.resolve())

    if chave in _cache:
        return _cache[chave]

    parser = DemoParser(str(caminho))

    try:
        congelamento = parser.parse_event("round_freeze_end")
    except Exception:
        congelamento = None

    dados = (
        parser.parse_event("round_end"),
        parser.parse_event("round_announce_match_start"),
        congelamento,
    )

    _cache[chave] = dados

    return dados


def classify_rounds(
    round_events,
    deaths,
    half_events=None,
    round_end_events=None,
    match_start_events=None,
):
    """
    round_events e half_events sao mantidos por compatibilidade
    com os parsers existentes e nao sao mais usados na regra.
    """

    lidos_fim, lidos_inicio, lidos_congelamento = _eventos_da_demo()
    if round_end_events is None or match_start_events is None:

        if round_end_events is None:
            round_end_events = lidos_fim

        if match_start_events is None:
            match_start_events = lidos_inicio

    fins = _para_tabela(round_end_events)

    if fins.empty:
        raise RuntimeError(
            "round_end nao disponivel. Nao e possivel classificar rounds."
        )

    if "round" not in fins.columns or "tick" not in fins.columns:
        raise RuntimeError(
            "round_end sem as colunas round e tick."
        )

    fins = fins.copy()
    fins["round"] = pd.to_numeric(fins["round"], errors="coerce")
    fins["tick"] = pd.to_numeric(fins["tick"], errors="coerce")
    fins = fins.dropna(subset=["round", "tick"])
    fins = fins[fins["tick"] > 0]
    fins = fins.sort_values("tick").reset_index(drop=True)

    ticks_inicio = _ticks_de(match_start_events)
    tick_ao_vivo = ticks_inicio[-1] if ticks_inicio else 0
    ticks_congelamento = _ticks_de(lidos_congelamento)

    mortes = _para_tabela(deaths)

    if not mortes.empty and "tick" in mortes.columns:
        ticks_mortes = pd.to_numeric(mortes["tick"], errors="coerce").dropna()
    else:
        ticks_mortes = pd.Series(dtype=float)

    linhas = []
    numero_oficial = 0
    tick_anterior = 0

    for posicao, linha in fins.iterrows():
        # tick do evento round_end: o ultimo tick que ainda pertence a este round
        tick_fim_real = int(linha["tick"])

        # round_end sem vencedor depois do "ao vivo" e round fantasma (restart
        # ou pausa tecnica do servidor de LAN): sem kill entre inimigos, so
        # mortes por "world". Nao conta como round jogado.
        if (tick_fim_real > tick_ao_vivo and "winner" in fins.columns
                and pd.isna(linha["winner"])):
            tick_anterior = tick_fim_real
            continue

        # primeiro tick que pertence a este round: o fim do freeze time dele
        tick_inicio = tick_anterior + 1
        liberado = [t for t in ticks_congelamento if tick_anterior < t <= tick_fim_real]
        if liberado:
            tick_inicio = liberado[-1]
        if tick_fim_real > tick_ao_vivo:
            tick_inicio = max(tick_inicio, tick_ao_vivo)

        # borda superior exclusiva, para quem filtra com [tick_start, tick_end)
        tick_fim = tick_fim_real + 1

        tick_anterior = tick_fim_real

        if not ticks_mortes.empty:
            mortes_no_round = int(
                (
                    (ticks_mortes >= tick_inicio)
                    & (ticks_mortes <= tick_fim_real)
                ).sum()
            )
        else:
            mortes_no_round = 0

        if tick_fim_real <= tick_ao_vivo:
            if mortes_no_round >= 8:
                tipo = "KNIFE"
            else:
                tipo = "WARMUP"

            linhas.append({
                "event_index": posicao,
                "tick_start": tick_inicio,
                "tick_end": tick_fim,
                "total_rounds_played": None,
                "half": None,
                "is_warmup_period": True,
                "round_type": tipo,
                "kill_events": mortes_no_round,
            })

            continue

        numero_oficial += 1

        if numero_oficial <= ROUNDS_REGULAMENTARES:
            if numero_oficial <= ROUNDS_POR_HALF:
                half = 1
            else:
                half = 2

            if numero_oficial in (1, ROUNDS_POR_HALF + 1):
                tipo = "PISTOL"
            else:
                tipo = "NORMAL"
        else:
            tipo = "OVERTIME"

            posicao_ot = numero_oficial - ROUNDS_REGULAMENTARES - 1
            bloco = posicao_ot // ROUNDS_POR_HALF_OT
            half = 3 + bloco

        linhas.append({
            "event_index": posicao,
            "tick_start": tick_inicio,
            "tick_end": tick_fim,
            "total_rounds_played": numero_oficial - 1,
            "half": half,
            "is_warmup_period": False,
            "round_type": tipo,
            "kill_events": mortes_no_round,
        })

    resultado = pd.DataFrame(linhas)

    if resultado.empty:
        raise RuntimeError(
            "Nenhum round encontrado apos a classificacao."
        )

    oficiais = resultado[resultado["round_type"].isin(TIPOS_OFICIAIS)]

    if oficiais.empty:
        raise RuntimeError(
            "Nenhum round oficial encontrado. "
            "Ticks de match_start: " + str(ticks_inicio)
        )

    return resultado


def main():
    print("round_classifier.py e um modulo de apoio.")
    print("Ele e chamado pelos parsers, nao roda sozinho.")


if __name__ == "__main__":
    main()