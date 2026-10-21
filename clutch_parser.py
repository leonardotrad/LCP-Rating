import os

import pandas as pd
from demoparser2 import DemoParser

from round_classifier import classify_rounds


COLUNAS_STATS = [
    "player",
    "clutch_wins",
    "clutch_rounds_last",
    "clutch_rounds_total",
    "clutch_success_pct",
    "1v5_wins",
    "1v4_wins",
    "1v3_wins",
    "1v2_wins",
    "1v1_wins",
]

TIPOS_OFICIAIS = ["PISTOL", "NORMAL", "OVERTIME"]


def _find_demo():
    from pathlib import Path as _P
    demos = sorted(_P("demos").glob("*.dem"))
    if not demos:
        raise FileNotFoundError("Nenhum arquivo .dem encontrado na pasta demos.")
    if len(demos) > 1:
        raise RuntimeError("Ha mais de uma demo na pasta demos. Deixe apenas uma por vez.")
    return str(demos[0])


DEMO_PATH = _find_demo()


def read_event(parser, event_name, fields):
    return parser.parse_event(event_name=event_name, player=fields)


def clean_name(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    value = str(value).strip()
    if not value:
        return None
    return value


def normalize_winner(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    value = str(value).strip().upper()
    if value in ["T", "TERRORIST", "TERRORISTS"]:
        return "TERRORIST"
    if value in ["CT", "COUNTER-TERRORIST", "COUNTERTERRORIST", "COUNTERTERRORISTS"]:
        return "CT"
    return value


def prepare_official_rounds(classified_rounds):
    official = classified_rounds[
        classified_rounds["round_type"].isin(TIPOS_OFICIAIS)
    ].copy()
    official = official.sort_values("tick_start").reset_index(drop=True)
    official["round_index"] = range(len(official))
    return official


def get_round_results(parser):
    round_end = pd.DataFrame(
        read_event(parser, "round_end", ["tick", "round", "winner", "reason"])
    )
    if round_end.empty:
        return round_end
    round_end["tick"] = pd.to_numeric(round_end["tick"], errors="coerce")
    round_end = round_end.dropna(subset=["tick"]).sort_values("tick").reset_index(drop=True)
    return round_end


def associate_round_results(official_rounds, round_end):
    rows = []
    if round_end.empty:
        return pd.DataFrame(columns=["round_index", "round_end_tick", "winner", "reason"])

    for _, round_row in official_rounds.iterrows():
        round_index = int(round_row["round_index"])
        start_tick = int(round_row["tick_start"])
        end_value = round_row["tick_end"]

        if pd.isna(end_value):
            candidates = round_end[round_end["tick"] >= start_tick].copy()
            if not candidates.empty:
                candidates = candidates.head(1)
        else:
            end_tick = int(end_value)
            candidates = round_end[
                (round_end["tick"] >= start_tick) & (round_end["tick"] <= end_tick)
            ].copy()
            if not candidates.empty:
                candidates = candidates.tail(1)

        if candidates.empty:
            continue

        end_row = candidates.iloc[0]
        rows.append({
            "round_index": round_index,
            "round_end_tick": int(end_row["tick"]),
            "winner": normalize_winner(end_row["winner"]),
            "reason": clean_name(end_row["reason"]),
        })

    return pd.DataFrame(rows)


def get_roster_for_round(parser, round_start_tick):
    """Quem estava em cada time no inicio do round.

    CORRECAO: 'name' agora e pedido explicitamente ao parser. Antes o codigo
    dependia de o parser devolver essa coluna sozinho, e quando ela nao vinha
    a funcao devolvia dois conjuntos vazios em silencio.
    """
    try:
        snapshots = pd.DataFrame(
            parser.parse_ticks(
                ["name", "team_num", "team_name", "health", "is_alive", "steamid"],
                ticks=[int(round_start_tick)],
            )
        )
    except Exception:
        return set(), set()

    if snapshots.empty or "name" not in snapshots.columns:
        return set(), set()

    snapshots["team_num"] = pd.to_numeric(snapshots["team_num"], errors="coerce")

    terrorists = set()
    counter_terrorists = set()

    for _, row in snapshots.iterrows():
        player = clean_name(row["name"])
        if player is None:
            continue
        team_num = row["team_num"]
        if pd.isna(team_num):
            continue
        team_num = int(team_num)
        if team_num == 2:
            terrorists.add(player)
        elif team_num == 3:
            counter_terrorists.add(player)

    return terrorists, counter_terrorists


def collect_all_players(parser, official, deaths, max_rounds=10):
    """Lista de jogadores da partida, de forma resistente a falha.

    CORRECAO: antes isso vinha do roster de UM unico round, o primeiro. Se o
    parser nao devolvesse nada naquele tick exato, a lista ficava vazia, a
    tabela de estatisticas saia sem nenhuma coluna e o script quebrava mais
    adiante com KeyError: 'player'. Agora tenta varios rounds e, em ultimo
    caso, usa os nomes que aparecem nos eventos de morte.
    """
    jogadores = set()

    if not official.empty:
        for _, round_row in official.head(max_rounds).iterrows():
            try:
                tick = int(round_row["tick_start"])
            except (TypeError, ValueError):
                continue
            t, ct = get_roster_for_round(parser, tick)
            jogadores |= t | ct
            if len(jogadores) >= 10:
                break

    if jogadores:
        return jogadores

    print("AVISO: nao foi possivel ler o roster pelos ticks de inicio de round.")
    print("       Usando os nomes que aparecem nos eventos de morte.")

    for coluna in ["attacker_name", "user_name"]:
        if coluna in deaths.columns:
            for valor in deaths[coluna].dropna().unique().tolist():
                nome = clean_name(valor)
                if nome:
                    jogadores.add(nome)

    return jogadores


def get_round_deaths(deaths, round_row, result_row):
    start_tick = int(round_row["tick_start"])
    result_end = result_row.get("round_end_tick", None)

    if result_end is not None and not pd.isna(result_end):
        end_tick = int(result_end)
        round_deaths = deaths[
            (deaths["tick"] >= start_tick) & (deaths["tick"] <= end_tick)
        ].copy()
    else:
        end_value = round_row["tick_end"]
        if pd.isna(end_value):
            round_deaths = deaths[deaths["tick"] >= start_tick].copy()
        else:
            end_tick = int(end_value)
            round_deaths = deaths[
                (deaths["tick"] >= start_tick) & (deaths["tick"] <= end_tick)
            ].copy()

    return round_deaths.sort_values("tick").reset_index(drop=True)


def calculate_new_clutch_after_death(
    alive_t_before, alive_ct_before, alive_t_after, alive_ct_after, victim
):
    """O clutch nasce quando uma morte deixa o time da vitima com exatamente
    um jogador vivo, havendo ainda pelo menos um adversario vivo."""

    if victim in alive_t_before:
        if len(alive_t_before) >= 2 and len(alive_t_after) == 1 and len(alive_ct_after) >= 1:
            player = next(iter(alive_t_after))
            return player, "TERRORIST", "1v%d" % len(alive_ct_after)

    if victim in alive_ct_before:
        if len(alive_ct_before) >= 2 and len(alive_ct_after) == 1 and len(alive_t_after) >= 1:
            player = next(iter(alive_ct_after))
            return player, "CT", "1v%d" % len(alive_t_after)

    return None, None, None


def reconstruct_clutch_round(parser, round_row, result_row, deaths):
    round_index = int(round_row["round_index"])
    start_tick = int(round_row["tick_start"])

    terrorists, counter_terrorists = get_roster_for_round(parser, start_tick)

    if not terrorists or not counter_terrorists:
        return None

    round_deaths = get_round_deaths(deaths, round_row, result_row)
    if round_deaths.empty:
        return None

    alive_t = set(terrorists)
    alive_ct = set(counter_terrorists)

    clutch_situations = []
    state_rows = []
    clutch_sequence = 0

    state_rows.append({
        "round_index": round_index,
        "tick": start_tick,
        "event": "ROUND_START",
        "killer": None,
        "victim": None,
        "t_alive": len(alive_t),
        "ct_alive": len(alive_ct),
        "clutch_player": None,
        "clutch_team": None,
        "clutch_type": None,
        "clutch_sequence": None,
    })

    for _, death in round_deaths.iterrows():
        tick = int(death["tick"])
        attacker = clean_name(death["attacker_name"])
        victim = clean_name(death["user_name"])

        if victim is None:
            continue

        alive_t_before = set(alive_t)
        alive_ct_before = set(alive_ct)

        if victim in alive_t:
            alive_t.remove(victim)
        elif victim in alive_ct:
            alive_ct.remove(victim)

        current_player, current_team, current_type = calculate_new_clutch_after_death(
            alive_t_before, alive_ct_before, alive_t, alive_ct, victim
        )

        if current_player is not None:
            clutch_sequence += 1
            clutch_situations.append({
                "round_index": round_index,
                "half": round_row.get("half", None),
                "round_type": round_row["round_type"],
                "clutch_tick": tick,
                "clutch_player": current_player,
                "clutch_team": current_team,
                "clutch_type": current_type,
                "opponent_count": int(current_type.split("v")[1]),
                "clutch_sequence": clutch_sequence,
            })

        state_rows.append({
            "round_index": round_index,
            "tick": tick,
            "event": "DEATH",
            "killer": attacker,
            "victim": victim,
            "t_alive": len(alive_t),
            "ct_alive": len(alive_ct),
            "clutch_player": current_player,
            "clutch_team": current_team,
            "clutch_type": current_type,
            "clutch_sequence": clutch_sequence if current_player is not None else None,
        })

    winner = normalize_winner(result_row["winner"])
    reason = clean_name(result_row["reason"])

    for situation in clutch_situations:
        situation["winner"] = winner
        situation["reason"] = reason
        if winner == situation["clutch_team"]:
            situation["result"] = "WIN"
        elif winner is not None:
            situation["result"] = "LOSS"
        else:
            situation["result"] = None

    return {"situations": clutch_situations, "state_rows": state_rows}


def calculate_clutch_stats(clutch_df, all_players=None):
    """CORRECAO: devolve SEMPRE um DataFrame com as colunas certas, mesmo
    quando nao ha nenhum jogador ou nenhum clutch. Antes, com a lista vazia,
    saia um DataFrame sem colunas e o script quebrava adiante."""

    tem_clutch = (
        isinstance(clutch_df, pd.DataFrame)
        and not clutch_df.empty
        and "clutch_player" in clutch_df.columns
    )

    if all_players:
        players = sorted(set(all_players))
    elif tem_clutch:
        players = sorted(clutch_df["clutch_player"].dropna().unique().tolist())
    else:
        players = []

    rows = []

    for player in players:
        if tem_clutch:
            group = clutch_df[clutch_df["clutch_player"] == player].copy()
        else:
            group = pd.DataFrame()

        if group.empty:
            wins = 0
            losses = 0
        else:
            wins = int((group["result"] == "WIN").sum())
            losses = int((group["result"] == "LOSS").sum())

        total = wins + losses
        success = round(wins / total * 100) if total > 0 else 0

        type_counts = {}
        for clutch_type in ["1v1", "1v2", "1v3", "1v4", "1v5"]:
            if group.empty:
                wins_type = 0
            else:
                mask = (group["clutch_type"] == clutch_type) & (group["result"] == "WIN")
                wins_type = int(mask.sum())
            type_counts[clutch_type] = wins_type

        rows.append({
            "player": player,
            "clutch_wins": wins,
            "clutch_rounds_last": losses,
            "clutch_rounds_total": total,
            "clutch_success_pct": success,
            "1v5_wins": type_counts["1v5"],
            "1v4_wins": type_counts["1v4"],
            "1v3_wins": type_counts["1v3"],
            "1v2_wins": type_counts["1v2"],
            "1v1_wins": type_counts["1v1"],
        })

    return pd.DataFrame(rows, columns=COLUNAS_STATS)


def exportar(clutch, states, stats):
    """CORRECAO IMPORTANTE: a gravacao agora acontece ANTES de qualquer
    impressao opcional. Antes era o contrario, e um erro numa funcao que so
    imprime jogava fora todo o trabalho ja calculado."""

    if not isinstance(clutch, pd.DataFrame):
        clutch = pd.DataFrame()
    if not isinstance(states, pd.DataFrame):
        states = pd.DataFrame()

    clutch.to_csv("clutch_debug.csv", index=False)
    states.to_csv("clutch_state_reconstruction.csv", index=False)
    stats.to_csv("data_clutch.csv", index=False)

    print()
    print("=" * 100)
    print("ARQUIVOS GERADOS")
    print("=" * 100)
    print("clutch_debug.csv")
    print("clutch_state_reconstruction.csv")
    print("data_clutch.csv")


def imprimir_situacoes(clutch):
    print()
    print("=" * 100)
    print("SITUACOES DE CLUTCH")
    print("=" * 100)

    if clutch.empty:
        print("Nenhum clutch detectado.")
        return

    columns = [
        "round_index", "half", "round_type", "clutch_player", "clutch_type",
        "opponent_count", "winner", "result", "reason", "clutch_tick", "clutch_sequence",
    ]
    print(
        clutch[columns]
        .sort_values(["round_index", "clutch_tick"])
        .to_string(index=False)
    )


def imprimir_resumo(clutch):
    print()
    print("=" * 100)
    print("RESUMO DOS CLUTCHES")
    print("=" * 100)

    if clutch.empty:
        print("Nenhum clutch detectado.")
        return

    wins_total = int((clutch["result"] == "WIN").sum())
    losses_total = int((clutch["result"] == "LOSS").sum())

    print("Situacoes: %d" % len(clutch))
    print("Wins: %d" % wins_total)
    print("Losses: %d" % losses_total)
    print()
    print("Por tipo:")
    print(clutch["clutch_type"].value_counts().sort_index().to_string())


def imprimir_por_jogador(stats):
    print()
    print("=" * 100)
    print("CLUTCH POR JOGADOR")
    print("=" * 100)

    if stats.empty:
        print("Nenhuma estatistica disponivel.")
        return

    print(
        stats.sort_values(
            ["clutch_rounds_total", "clutch_wins"], ascending=False
        ).to_string(index=False)
    )


def imprimir_conferencia(clutch, stats):
    """CORRECAO: a funcao antiga comparava o resultado com uma tabela de
    numeros fixos de uma unica partida antiga, entao acusava erro em todas as
    outras e quebrava quando stats vinha vazio. Agora a conferencia e interna:
    a soma por jogador tem que bater com o total de situacoes da partida."""

    print()
    print("=" * 100)
    print("CONFERENCIA")
    print("=" * 100)

    situacoes = 0 if clutch.empty else len(clutch)
    wins = 0 if clutch.empty else int((clutch["result"] == "WIN").sum())
    losses = 0 if clutch.empty else int((clutch["result"] == "LOSS").sum())

    soma_wins = int(stats["clutch_wins"].sum()) if not stats.empty else 0
    soma_losses = int(stats["clutch_rounds_last"].sum()) if not stats.empty else 0

    linhas = [
        {
            "item": "clutches vencidos",
            "na partida": wins,
            "somado por jogador": soma_wins,
            "status": "OK" if wins == soma_wins else "DIVERGENTE",
        },
        {
            "item": "clutches perdidos",
            "na partida": losses,
            "somado por jogador": soma_losses,
            "status": "OK" if losses == soma_losses else "DIVERGENTE",
        },
        {
            "item": "situacoes com resultado",
            "na partida": wins + losses,
            "somado por jogador": soma_wins + soma_losses,
            "status": "OK" if (wins + losses) == (soma_wins + soma_losses) else "DIVERGENTE",
        },
    ]

    print(pd.DataFrame(linhas).to_string(index=False))

    sem_resultado = situacoes - (wins + losses)
    if sem_resultado > 0:
        print()
        print("AVISO: %d situacao(oes) sem vencedor definido no round." % sem_resultado)

    if stats.empty:
        print()
        print("AVISO: nenhum jogador foi identificado nesta partida.")


def main():
    print("=" * 100)
    print("LCP RATING - CLUTCH PARSER")
    print("=" * 100)

    if not os.path.exists(DEMO_PATH):
        raise FileNotFoundError("Demo nao encontrada: %s" % DEMO_PATH)

    parser = DemoParser(DEMO_PATH)

    print()
    print("Lendo rounds...")
    rounds = pd.DataFrame(
        read_event(parser, "round_poststart", ["tick", "total_rounds_played", "is_warmup_period"])
    )
    print("Eventos de round: %d" % len(rounds))

    print()
    print("Lendo player_death...")
    deaths = pd.DataFrame(
        read_event(parser, "player_death", ["tick", "attacker_name", "user_name", "weapon"])
    )

    if deaths.empty:
        raise RuntimeError("Nenhum evento player_death foi encontrado.")

    deaths["tick"] = pd.to_numeric(deaths["tick"], errors="coerce")
    deaths = deaths.dropna(subset=["tick"]).sort_values("tick").reset_index(drop=True)
    print("Eventos de morte: %d" % len(deaths))

    print()
    print("Lendo troca de half...")
    half_events = pd.DataFrame(
        read_event(parser, "round_announce_last_round_half", ["tick"])
    )

    print()
    print("Classificando rounds...")
    classified = pd.DataFrame(classify_rounds(rounds, deaths, half_events))
    official = prepare_official_rounds(classified)
    print("Rounds oficiais: %d" % len(official))

    print()
    print("Lendo resultados dos rounds...")
    round_end = get_round_results(parser)
    results = associate_round_results(official, round_end)
    print("Resultados encontrados: %d" % len(results))

    print()
    print("Reconstruindo estado vivo dos rounds...")

    clutch_rows = []
    state_rows = []
    rounds_sem_roster = 0

    for _, round_row in official.iterrows():
        round_index = int(round_row["round_index"])
        matching_result = results[results["round_index"] == round_index]

        if matching_result.empty:
            continue

        result_row = matching_result.iloc[0]
        result = reconstruct_clutch_round(parser, round_row, result_row, deaths)

        if result is None:
            rounds_sem_roster += 1
            continue

        clutch_rows.extend(result["situations"])
        state_rows.extend(result["state_rows"])

    clutch = pd.DataFrame(clutch_rows)
    states = pd.DataFrame(state_rows)

    if rounds_sem_roster:
        print("Rounds sem estado reconstruido: %d" % rounds_sem_roster)

    all_players = collect_all_players(parser, official, deaths)
    print("Jogadores identificados: %d" % len(all_players))

    stats = calculate_clutch_stats(clutch, all_players=all_players)

    # Grava primeiro. Qualquer problema de impressao depois disso nao
    # destroi mais o resultado da partida.
    exportar(clutch, states, stats)

    try:
        imprimir_situacoes(clutch)
        imprimir_resumo(clutch)
        imprimir_por_jogador(stats)
        imprimir_conferencia(clutch, stats)
    except Exception as e:
        print()
        print("AVISO: falha ao imprimir o relatorio (%s: %s)." % (type(e).__name__, e))
        print("Os arquivos ja foram gravados e estao corretos.")

    print()
    print("Clutch parser executado com sucesso.")


if __name__ == "__main__":
    main()