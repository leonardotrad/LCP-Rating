from pathlib import Path

import pandas as pd


DATA_KILLS = Path("data_kills.csv")
ROUND_RESULTS = Path("round_results.csv")
DATA_ROUNDS = Path("data_rounds.csv")

OUTPUT_FILE = Path("round_player_stats.csv")


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {path}"
        )

    return pd.read_csv(path)


def normalize_text(series: pd.Series) -> pd.Series:
    return (
        series
        .fillna("")
        .astype(str)
        .str.strip()
    )


def load_data():
    kills = load_csv(DATA_KILLS)
    round_results = load_csv(ROUND_RESULTS)
    rounds = load_csv(DATA_ROUNDS)

    return kills, round_results, rounds


def prepare_kills(kills: pd.DataFrame) -> pd.DataFrame:
    df = kills.copy()

    required = {
        "round_event_index",
        "round_number",
        "half",
        "round_type",
        "tick",
        "attacker_name",
        "victim_name",
        "assister_name",
        "headshot",
        "dmg_health",
        "dmg_armor",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "data_kills.csv não possui as colunas necessárias: "
            f"{sorted(missing)}"
        )

    df["round_event_index"] = pd.to_numeric(
        df["round_event_index"],
        errors="coerce",
    )

    df["round_number"] = pd.to_numeric(
        df["round_number"],
        errors="coerce",
    )

    df["tick"] = pd.to_numeric(
        df["tick"],
        errors="coerce",
    )

    df["attacker_name"] = normalize_text(
        df["attacker_name"]
    )

    df["victim_name"] = normalize_text(
        df["victim_name"]
    )

    df["assister_name"] = normalize_text(
        df["assister_name"]
    )

    df["headshot"] = (
        df["headshot"]
        .fillna(False)
        .astype(bool)
    )

    df["dmg_health"] = pd.to_numeric(
        df["dmg_health"],
        errors="coerce",
    ).fillna(0)

    df["dmg_armor"] = pd.to_numeric(
        df["dmg_armor"],
        errors="coerce",
    ).fillna(0)

    # round_number do data_kills começa em 0.
    # round_results usa 1...22.
    df["round"] = (
        df["round_number"] + 1
    ).astype("Int64")

    return df


def prepare_round_results(round_results: pd.DataFrame):
    df = round_results.copy()

    required = {
        "round",
        "event_index",
        "half",
        "round_type",
        "winner",
        "reason",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "round_results.csv não possui as colunas necessárias: "
            f"{sorted(missing)}"
        )

    df["round"] = pd.to_numeric(
        df["round"],
        errors="coerce",
    ).astype("Int64")

    df["event_index"] = pd.to_numeric(
        df["event_index"],
        errors="coerce",
    ).astype("Int64")

    df["winner"] = (
        df["winner"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["reason"] = (
        df["reason"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    return df


def prepare_rounds(rounds: pd.DataFrame):
    df = rounds.copy()

    official_types = {
        "PISTOL",
        "NORMAL",
        "OVERTIME",
    }

    df = df[
        df["round_type"].isin(official_types)
    ].copy()

    df["round"] = (
        pd.to_numeric(
            df["total_rounds_played"],
            errors="coerce",
        ) + 1
    ).astype("Int64")

    return df


def build_round_events(kills: pd.DataFrame):
    """
    Produz estatísticas agregadas por jogador e round
    a partir dos eventos de kill.
    """

    players = set()

    for value in kills["attacker_name"]:
        if value:
            players.add(value)

    for value in kills["victim_name"]:
        if value:
            players.add(value)

    for value in kills["assister_name"]:
        if value:
            players.add(value)

    return players


def aggregate_kill_stats(kills: pd.DataFrame):
    """
    Cria três tabelas auxiliares:

    1. kills do atacante
    2. deaths da vítima
    3. assists do assistente
    """

    # -------------------------
    # KILLS
    # -------------------------

    # Suicidio e kill em companheiro nao contam como kill (no placar valem -1).
    # A morte continua contando para a vitima.
    valida = (kills["attacker_name"] != "") & (kills["attacker_name"] != kills["victim_name"])
    if "attacker_team" in kills.columns and "victim_team" in kills.columns:
        mesmo_time = (kills["attacker_team"].notna()
                      & (kills["attacker_team"] == kills["victim_team"]))
        valida = valida & ~mesmo_time

    attacker = (
        kills[
            valida
        ]
        .groupby(
            [
                "round",
                "attacker_name",
            ],
            dropna=False,
        )
        .agg(
            kills=(
                "victim_name",
                "size",
            ),
            headshots=(
                "headshot",
                "sum",
            ),
            damage=(
                "dmg_health",
                "sum",
            ),
        )
        .reset_index()
        .rename(
            columns={
                "attacker_name": "player",
            }
        )
    )

    # -------------------------
    # DEATHS
    # -------------------------

    victim = (
        kills[
            kills["victim_name"] != ""
        ]
        .groupby(
            [
                "round",
                "victim_name",
            ],
            dropna=False,
        )
        .size()
        .reset_index(
            name="deaths"
        )
        .rename(
            columns={
                "victim_name": "player",
            }
        )
    )

    # -------------------------
    # ASSISTS
    # -------------------------

    assists = (
        kills[
            kills["assister_name"] != ""
        ]
        .groupby(
            [
                "round",
                "assister_name",
            ],
            dropna=False,
        )
        .size()
        .reset_index(
            name="assists"
        )
        .rename(
            columns={
                "assister_name": "player",
            }
        )
    )

    return attacker, victim, assists


def build_player_round_table(
    kills,
    round_results,
):
    attacker, victim, assists = aggregate_kill_stats(
        kills
    )

    # Todos os rounds oficiais.
    rounds = round_results[
        [
            "round",
            "event_index",
            "half",
            "round_type",
            "winner",
            "reason",
        ]
    ].copy()

    # --------------------------------------------------
    # Jogadores que aparecem na demo.
    #
    # Neste estágio usamos todos os jogadores encontrados
    # nos eventos de kill.
    # --------------------------------------------------

    player_names = sorted(
        build_round_events(kills)
    )

    base = []

    for _, row in rounds.iterrows():
        for player in player_names:
            base.append(
                {
                    "round": int(row["round"]),
                    "event_index": int(row["event_index"]),
                    "half": row["half"],
                    "round_type": row["round_type"],
                    "winner": row["winner"],
                    "reason": row["reason"],
                    "player": player,
                }
            )

    result = pd.DataFrame(base)

    # --------------------------------------------------
    # KILLS
    # --------------------------------------------------

    result = result.merge(
        attacker[
            [
                "round",
                "player",
                "kills",
                "headshots",
                "damage",
            ]
        ],
        on=[
            "round",
            "player",
        ],
        how="left",
    )

    # --------------------------------------------------
    # DEATHS
    # --------------------------------------------------

    result = result.merge(
        victim[
            [
                "round",
                "player",
                "deaths",
            ]
        ],
        on=[
            "round",
            "player",
        ],
        how="left",
    )

    # --------------------------------------------------
    # ASSISTS
    # --------------------------------------------------

    result = result.merge(
        assists[
            [
                "round",
                "player",
                "assists",
            ]
        ],
        on=[
            "round",
            "player",
        ],
        how="left",
    )

    # --------------------------------------------------
    # Valores ausentes = zero
    # --------------------------------------------------

    numeric_columns = [
        "kills",
        "deaths",
        "assists",
        "headshots",
        "damage",
    ]

    for column in numeric_columns:
        result[column] = (
            pd.to_numeric(
                result[column],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

    # --------------------------------------------------
    # Participação básica
    # --------------------------------------------------

    result["contribution"] = (
        (
            result["kills"] > 0
        )
        | (
            result["assists"] > 0
        )
    )

    result["kast"] = (
        result["kills"]
        + result["assists"]
        + result["deaths"]
    )

    result["kast"] = (
        result["kast"] > 0
    )

    # --------------------------------------------------
    # Round vencedor do jogador.
    #
    # Neste momento ainda NÃO atribuímos o time real.
    # Essa coluna só será preenchida depois que o roster
    # por round for incorporado.
    # --------------------------------------------------

    result["is_round_winner"] = False

    # --------------------------------------------------
    # Multi-kill
    # --------------------------------------------------

    result["multi_kill"] = (
        result["kills"] >= 2
    )

    # --------------------------------------------------
    # Marcadores úteis
    # --------------------------------------------------

    result["got_kill"] = (
        result["kills"] > 0
    )

    result["died"] = (
        result["deaths"] > 0
    )

    result["got_assist"] = (
        result["assists"] > 0
    )

    result["impact_points_raw"] = (
        result["kills"] * 1.0
        + result["assists"] * 0.5
    )

    return result


def validate(result):
    print()
    print("=" * 80)
    print("VALIDAÇÃO ROUND PLAYER STATS")
    print("=" * 80)
    print()

    print(
        f"Rounds: {result['round'].nunique()}"
    )

    print(
        f"Jogadores: {result['player'].nunique()}"
    )

    print(
        f"Linhas: {len(result)}"
    )

    print()

    print(
        "Kills totais:",
        int(result["kills"].sum())
    )

    print(
        "Deaths totais:",
        int(result["deaths"].sum())
    )

    print(
        "Assists totais:",
        int(result["assists"].sum())
    )

    print()

    expected_kills = 151

    actual_kills = int(
        result["kills"].sum()
    )

    print(
        f"Kills esperados: {expected_kills}"
    )

    print(
        f"Kills reconstruídos: {actual_kills}"
    )

    if actual_kills != expected_kills:
        print(
            "ATENÇÃO: quantidade de kills reconstruída "
            "não bate com data_kills.csv."
        )
    else:
        print(
            "OK: todos os kills foram contabilizados."
        )

    print()

    rounds_per_player = (
        result
        .groupby("player")["round"]
        .nunique()
        .sort_values()
    )

    print(
        "Rounds por jogador:"
    )

    print(
        rounds_per_player.to_string()
    )

    print()

    print(
        "Exemplo dos primeiros registros:"
    )

    print(
        result.head(25).to_string(
            index=False
        )
    )


def main():
    print()
    print("=" * 80)
    print("LCP - ROUND PLAYER STATS")
    print("=" * 80)
    print()

    kills, round_results, rounds = load_data()

    print(
        f"data_kills.csv: {len(kills)} eventos"
    )

    print(
        f"round_results.csv: {len(round_results)} rounds"
    )

    print(
        f"data_rounds.csv: {len(rounds)} registros"
    )

    print()

    kills = prepare_kills(kills)

    round_results = prepare_round_results(
        round_results
    )

    rounds = prepare_rounds(
        rounds
    )

    result = build_player_round_table(
        kills,
        round_results,
    )

    validate(result)

    # Ordenação.
    result = result.sort_values(
        [
            "round",
            "player",
        ]
    ).reset_index(
        drop=True
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
    print("ROUND PLAYER STATS CONCLUÍDO")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()