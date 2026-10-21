from pathlib import Path

import pandas as pd


KILLS_FILE = Path("data_kills.csv")
ROUND_RESULTS_FILE = Path("round_results.csv")
CONTEXT_FILE = Path("round_player_impact_context.csv")

OUTPUT_FILE = Path("round_state_probe.csv")


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {path}"
        )

    return pd.read_csv(path)


def prepare_kills(df: pd.DataFrame) -> pd.DataFrame:
    required = {
        "round_number",
        "tick",
        "attacker_name",
        "victim_name",
        "round_event_index",
        "weapon",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "data_kills.csv não possui as colunas necessárias: "
            f"{sorted(missing)}"
        )

    result = df.copy()

    result["round_number"] = pd.to_numeric(
        result["round_number"],
        errors="coerce",
    )

    result["round"] = (
        result["round_number"] + 1
    ).astype("Int64")

    result["tick"] = pd.to_numeric(
        result["tick"],
        errors="coerce",
    )

    result["round_event_index"] = pd.to_numeric(
        result["round_event_index"],
        errors="coerce",
    )

    for column in [
        "attacker_name",
        "victim_name",
        "weapon",
    ]:
        result[column] = (
            result[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    # ============================================================
    # CLASSIFICAÇÃO DO EVENTO
    # ============================================================

    result["event_type"] = "PLAYER_KILL"

    world_event = (
        (result["weapon"].str.lower() == "world")
        |
        (result["attacker_name"] == "")
        |
        (result["victim_name"] == "")
        |
        (result["attacker_name"] == result["victim_name"])
    )

    result.loc[
        world_event,
        "event_type",
    ] = "WORLD_EVENT"

    return result.sort_values(
        [
            "round",
            "tick",
        ]
    ).reset_index(drop=True)


def prepare_rounds(df: pd.DataFrame) -> pd.DataFrame:
    required = {
        "round",
        "winner",
        "reason",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "round_results.csv não possui as colunas necessárias: "
            f"{sorted(missing)}"
        )

    result = df.copy()

    result["round"] = pd.to_numeric(
        result["round"],
        errors="coerce",
    ).astype("Int64")

    result["winner"] = (
        result["winner"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    result["reason"] = (
        result["reason"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    return result


def build_player_lookup(context: pd.DataFrame):
    """Monta as formas de achar o time de um jogador num round.

    CORRECAO: antes havia uma unica chave, a coluna round, e quando ela nao
    casava com a numeracao usada em data_kills o round inteiro ficava sem time.
    Sem time, as contagens de vivos saiam None, viravam NaN no CSV e derrubavam
    o kill_leverage_probe mais adiante, sem nenhum aviso.

    Agora sao tres caminhos, do mais especifico para o mais geral:
      por_round  -> time do jogador naquele round
      por_event  -> mesma coisa indexada por event_index
      por_half   -> time do jogador naquele half, para completar um round
                    que veio incompleto
    O half importa porque os times trocam de lado no intervalo.
    """
    required = {
        "round",
        "player",
        "team",
    }

    missing = required - set(context.columns)

    if missing:
        raise ValueError(
            "round_player_impact_context.csv não possui: "
            f"{sorted(missing)}"
        )

    from collections import Counter

    por_round = {}
    por_event = {}
    votos_half = {}
    half_do_round = {}

    tem_event = "event_index" in context.columns
    tem_half = "half" in context.columns

    for _, row in context.iterrows():
        player = str(row["player"]).strip()
        team = str(row["team"]).strip()

        try:
            round_number = int(row["round"])
        except (TypeError, ValueError):
            round_number = None

        try:
            event_index = int(row["event_index"]) if tem_event else None
        except (TypeError, ValueError):
            event_index = None

        try:
            half = int(row["half"]) if tem_half else None
        except (TypeError, ValueError):
            half = None

        # IMPORTANTE: o half do round e registrado ANTES de qualquer descarte.
        # Na primeira versao desta correcao eu pulava a linha logo que o time
        # vinha vazio, e com isso nunca ficava sabendo a que half pertenciam
        # justamente os rounds que precisavam ser preenchidos. O terceiro
        # caminho de recuperacao nunca chegava a ser usado.
        if round_number is not None and half is not None:
            half_do_round[round_number] = half

        if not player or not team or team.lower() in ("nan", "none"):
            continue

        if round_number is not None:
            por_round.setdefault(round_number, {})[player] = team

        if event_index is not None:
            por_event.setdefault(event_index, {})[player] = team

        if half is not None:
            votos_half.setdefault((half, player), Counter())[team] += 1

    # time do jogador no half, por maioria dos rounds em que ele aparece.
    # Serve apenas para PREENCHER o que falta, nunca para sobrescrever o que
    # o arquivo ja traz: a coluna team e coerente com o vencedor do round, e
    # trocar um valor existente quebraria o killer_team_won.
    por_half = {}
    for (half, player), contagem in votos_half.items():
        por_half.setdefault(half, {})[player] = contagem.most_common(1)[0][0]

    return por_round, por_event, por_half, half_do_round


def alive_counts(roster, dead):
    ct_alive = sum(
        1
        for player, team in roster.items()
        if team == "CT"
        and player not in dead
    )

    t_alive = sum(
        1
        for player, team in roster.items()
        if team == "T"
        and player not in dead
    )

    return ct_alive, t_alive


def state_label(
    attacker_team,
    ct_alive,
    t_alive,
):
    if attacker_team == "CT":
        own_alive = ct_alive
        enemy_alive = t_alive
    elif attacker_team == "T":
        own_alive = t_alive
        enemy_alive = ct_alive
    else:
        return "UNKNOWN"

    if own_alive == 5 and enemy_alive == 5:
        return "5v5"

    if own_alive == enemy_alive == 4:
        return "4v4"

    if own_alive == enemy_alive == 3:
        return "3v3"

    if own_alive == enemy_alive == 2:
        return "2v2"

    if own_alive == enemy_alive == 1:
        return "1v1"

    if own_alive > enemy_alive:
        return "MAN_ADVANTAGE"

    if own_alive < enemy_alive:
        return "MAN_DISADVANTAGE"

    return "UNKNOWN"


def numeric_difference(
    attacker_team,
    ct_alive,
    t_alive,
):
    if attacker_team == "CT":
        return ct_alive - t_alive

    if attacker_team == "T":
        return t_alive - ct_alive

    return None


def classify_transition(
    difference_before,
    difference_after,
    is_first_kill,
):
    if (
        difference_before is None
        or difference_after is None
    ):
        return "UNKNOWN"

    if (
        is_first_kill
        and difference_before == 0
        and difference_after > 0
    ):
        return "FIRST_KILL_ADVANTAGE"

    if (
        difference_before < 0
        and difference_after == 0
    ):
        return "EQUALIZER"

    if (
        difference_before < 0
        and difference_after > 0
    ):
        return "COMEBACK_SWING"

    if (
        difference_before == 0
        and difference_after > 0
    ):
        return "REGAIN_ADVANTAGE"

    if (
        difference_before > 0
        and difference_after > difference_before
    ):
        return "EXTEND_ADVANTAGE"

    if (
        difference_before > 0
        and difference_after > 0
    ):
        return "ADVANTAGE_PRESSURE"

    if (
        difference_before < 0
        and difference_after < 0
        and difference_after > difference_before
    ):
        return "DISADVANTAGE_PRESSURE"

    if (
        difference_before < 0
        and difference_after < 0
    ):
        return "DISADVANTAGE_KILL"

    return "OTHER"


def montar_roster(
    round_number,
    event_index,
    jogadores_do_round,
    por_round,
    por_event,
    por_half,
    half_do_round,
    relatorio,
):
    """Roster do round, completando o que faltar sem inventar nada."""

    roster = dict(por_round.get(round_number, {}))

    if event_index is not None:
        for player, team in por_event.get(event_index, {}).items():
            roster.setdefault(player, team)
            if player not in por_round.get(round_number, {}):
                relatorio["por_event"] += 1

    half = half_do_round.get(round_number)

    for player in jogadores_do_round:
        if player in roster or not player:
            continue

        team = None

        if half is not None:
            team = por_half.get(half, {}).get(player)

        if team:
            roster[player] = team
            relatorio["por_half"] += 1
        else:
            relatorio["sem_time"].add(player)

    return roster


def reconstruct_round_states(
    kills,
    player_lookup,
):
    por_round, por_event, por_half, half_do_round = player_lookup

    relatorio = {
        "por_event": 0,
        "por_half": 0,
        "sem_time": set(),
        "rounds_sem_roster": [],
        "rounds_incompletos": [],
    }

    rows = []

    # Somente eliminações reais jogador -> jogador.
    player_kills = kills[
        kills["event_type"] == "PLAYER_KILL"
    ].copy()

    for round_number, round_kills in player_kills.groupby(
        "round",
        sort=True,
    ):
        round_number = int(
            round_number
        )

        event_index = None

        if "round_event_index" in round_kills.columns:
            valores = (
                round_kills["round_event_index"]
                .dropna()
                .unique()
                .tolist()
            )

            if valores:
                try:
                    event_index = int(valores[0])
                except (TypeError, ValueError):
                    event_index = None

        jogadores_do_round = set()

        for coluna in ("attacker_name", "victim_name"):
            for nome in round_kills[coluna].dropna().unique().tolist():
                nome = str(nome).strip()
                if nome:
                    jogadores_do_round.add(nome)

        roster = montar_roster(
            round_number,
            event_index,
            jogadores_do_round,
            por_round,
            por_event,
            por_half,
            half_do_round,
            relatorio,
        )

        if not roster:
            relatorio["rounds_sem_roster"].append(round_number)
        elif len(roster) != 10:
            relatorio["rounds_incompletos"].append(
                (round_number, len(roster))
            )

        dead = set()

        round_kills = round_kills.sort_values(
            "tick"
        ).reset_index(drop=True)

        for sequence, (_, kill) in enumerate(
            round_kills.iterrows(),
            start=1,
        ):
            attacker = kill[
                "attacker_name"
            ]

            victim = kill[
                "victim_name"
            ]

            attacker_team = roster.get(
                attacker
            )

            victim_team = roster.get(
                victim
            )

            ct_before, t_before = alive_counts(
                roster,
                dead,
            )

            own_before = (
                ct_before
                if attacker_team == "CT"
                else t_before
                if attacker_team == "T"
                else None
            )

            enemy_before = (
                t_before
                if attacker_team == "CT"
                else ct_before
                if attacker_team == "T"
                else None
            )

            diff_before = numeric_difference(
                attacker_team,
                ct_before,
                t_before,
            )

            state_before = state_label(
                attacker_team,
                ct_before,
                t_before,
            )

            is_first_kill = (
                sequence == 1
            )

            dead.add(
                victim
            )

            ct_after, t_after = alive_counts(
                roster,
                dead,
            )

            own_after = (
                ct_after
                if attacker_team == "CT"
                else t_after
                if attacker_team == "T"
                else None
            )

            enemy_after = (
                t_after
                if attacker_team == "CT"
                else ct_after
                if attacker_team == "T"
                else None
            )

            diff_after = numeric_difference(
                attacker_team,
                ct_after,
                t_after,
            )

            transition = classify_transition(
                diff_before,
                diff_after,
                is_first_kill,
            )

            is_last_kill = (
                sequence == len(round_kills)
            )

            rows.append(
                {
                    "round": round_number,
                    "sequence": sequence,
                    "tick": int(kill["tick"]),
                    "attacker": attacker,
                    "victim": victim,
                    "attacker_team": attacker_team,
                    "victim_team": victim_team,
                    "own_alive_before": own_before,
                    "enemy_alive_before": enemy_before,
                    "ct_alive_before": ct_before,
                    "t_alive_before": t_before,
                    "state_before": state_before,
                    "difference_before": diff_before,
                    "own_alive_after": own_after,
                    "enemy_alive_after": enemy_after,
                    "ct_alive_after": ct_after,
                    "t_alive_after": t_after,
                    "difference_after": diff_after,
                    "transition": transition,
                    "is_first_kill": is_first_kill,
                    "is_last_kill": is_last_kill,
                }
            )

    imprimir_relatorio_roster(relatorio)

    return pd.DataFrame(rows)


def imprimir_relatorio_roster(relatorio):
    recuperados = relatorio["por_event"] + relatorio["por_half"]
    problemas = (
        relatorio["sem_time"]
        or relatorio["rounds_sem_roster"]
        or relatorio["rounds_incompletos"]
    )

    if not recuperados and not problemas:
        return

    print()
    print("=" * 80)
    print("ROSTER DOS ROUNDS")
    print("=" * 80)
    print()

    if relatorio["por_event"]:
        print(
            "Entradas recuperadas pelo event_index: %d"
            % relatorio["por_event"]
        )

    if relatorio["por_half"]:
        print(
            "Entradas recuperadas pelo half do jogador: %d"
            % relatorio["por_half"]
        )

    if relatorio["rounds_incompletos"]:
        print()
        print("Rounds com roster diferente de 10 jogadores:")
        for round_number, quantidade in relatorio["rounds_incompletos"]:
            print("   round %s: %d jogador(es)" % (round_number, quantidade))

    if relatorio["rounds_sem_roster"]:
        print()
        print(
            "ATENCAO: rounds sem nenhum jogador identificado: %s"
            % ", ".join(str(r) for r in relatorio["rounds_sem_roster"])
        )

    if relatorio["sem_time"]:
        print()
        print(
            "ATENCAO: jogadores sem time em algum round: %s"
            % ", ".join(sorted(relatorio["sem_time"]))
        )
        print(
            "         As kills desses jogadores ficam sem contagem de vivos"
        )
        print(
            "         e o round e descartado no kill_leverage_probe."
        )


def add_round_results(
    states,
    rounds,
):
    result = states.merge(
        rounds[
            [
                "round",
                "winner",
                "reason",
            ]
        ],
        on="round",
        how="left",
    )

    result["killer_team_won"] = (
        result["attacker_team"]
        == result["winner"]
    )

    return result


def add_world_events(
    result,
    kills,
):
    world_events = kills[
        kills["event_type"] == "WORLD_EVENT"
    ].copy()

    if world_events.empty:
        result["world_event_in_round"] = False

        return result

    world_rounds = set(
        world_events["round"]
        .dropna()
        .astype(int)
        .tolist()
    )

    result["world_event_in_round"] = (
        result["round"]
        .astype(int)
        .isin(world_rounds)
    )

    return result


def validate(
    result,
    kills,
):
    print()
    print("=" * 80)
    print("VALIDAÇÃO")
    print("=" * 80)
    print()

    total_events = len(kills)

    player_kills = int(
        (
            kills["event_type"]
            == "PLAYER_KILL"
        ).sum()
    )

    world_events = int(
        (
            kills["event_type"]
            == "WORLD_EVENT"
        ).sum()
    )

    print(
        "Eventos totais em data_kills:",
        total_events,
    )

    print(
        "PLAYER_KILL:",
        player_kills,
    )

    print(
        "WORLD_EVENT:",
        world_events,
    )

    print()

    print(
        "Rounds analisados:",
        result["round"].nunique(),
    )

    print(
        "Kills jogador x jogador analisadas:",
        len(result),
    )

    print()

    print(
        "Primeiras kills:",
        int(
            result["is_first_kill"].sum()
        ),
    )

    print(
        "Últimas kills:",
        int(
            result["is_last_kill"].sum()
        ),
    )

    print()

    # CORRECAO: a validacao antiga comparava com numeros fixos de uma unica
    # partida antiga (150 kills, 1 world event) e por isso acusava problema em
    # todas as outras. Agora a conferencia e interna a propria partida.

    if player_kills == len(result):
        print(
            "OK: todas as %d PLAYER_KILL foram reconstruidas." % player_kills
        )
    else:
        print(
            "ATENCAO: %d PLAYER_KILL em data_kills e %d reconstruidas."
            % (player_kills, len(result))
        )

    rounds_analisados = result["round"].nunique()

    if int(result["is_first_kill"].sum()) == rounds_analisados:
        print("OK: uma primeira kill por round.")
    else:
        print(
            "ATENCAO: %d primeiras kills para %d rounds."
            % (int(result["is_first_kill"].sum()), rounds_analisados)
        )

    if int(result["is_last_kill"].sum()) == rounds_analisados:
        print("OK: uma ultima kill por round.")
    else:
        print(
            "ATENCAO: %d ultimas kills para %d rounds."
            % (int(result["is_last_kill"].sum()), rounds_analisados)
        )

    print()

    sem_time = int(
        result["attacker_team"].isna().sum()
        + result["victim_team"].isna().sum()
    )

    if sem_time:
        print(
            "ATENCAO: %d campo(s) de time vazio(s) nas PLAYER_KILL." % sem_time
        )
        print(
            "         Esses rounds serao descartados no kill_leverage_probe."
        )
    else:
        print(
            "OK: todas as PLAYER_KILL possuem times."
        )

    sem_contagem = int(
        result["own_alive_before"].isna().sum()
    )

    if sem_contagem:
        print(
            "ATENCAO: %d linha(s) sem contagem de vivos." % sem_contagem
        )
    else:
        print(
            "OK: todas as linhas tem contagem de vivos."
        )


def print_transition_summary(df):
    print()
    print("=" * 80)
    print("TRANSIÇÕES DE ESTADO")
    print("=" * 80)
    print()

    print(
        df["transition"]
        .value_counts()
        .to_string()
    )

    print()

    print("=" * 80)
    print("ESTADOS ANTES DA KILL")
    print("=" * 80)
    print()

    print(
        df["state_before"]
        .value_counts()
        .to_string()
    )


def print_world_events(kills):
    print()
    print("=" * 80)
    print("WORLD EVENTS IGNORADOS NO ESTADO DE COMBATE")
    print("=" * 80)
    print()

    world_events = kills[
        kills["event_type"] == "WORLD_EVENT"
    ].copy()

    if world_events.empty:
        print(
            "Nenhum WORLD_EVENT."
        )

        return

    columns = [
        "round_number",
        "round_event_index",
        "tick",
        "attacker_name",
        "victim_name",
        "weapon",
    ]

    columns = [
        column
        for column in columns
        if column in world_events.columns
    ]

    print(
        world_events[
            columns
        ].to_string(
            index=False
        )
    )


def main():
    print()
    print("=" * 80)
    print("LCP - ROUND STATE PROBE")
    print("=" * 80)
    print()

    kills = load_csv(
        KILLS_FILE
    )

    rounds = load_csv(
        ROUND_RESULTS_FILE
    )

    context = load_csv(
        CONTEXT_FILE
    )

    kills = prepare_kills(
        kills
    )

    rounds = prepare_rounds(
        rounds
    )

    player_lookup = build_player_lookup(
        context
    )

    states = reconstruct_round_states(
        kills,
        player_lookup,
    )

    result = add_round_results(
        states,
        rounds,
    )

    result = add_world_events(
        result,
        kills,
    )

    validate(
        result,
        kills,
    )

    print_world_events(
        kills
    )

    print_transition_summary(
        result
    )

    result.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print()
    print("=" * 80)
    print("ARQUIVO GERADO")
    print("=" * 80)
    print()

    print(
        OUTPUT_FILE
    )

    print()
    print("=" * 80)
    print("ROUND STATE PROBE CONCLUÍDO")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()