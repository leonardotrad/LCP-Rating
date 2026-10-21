from pathlib import Path

import pandas as pd
from demoparser2 import DemoParser


DEMO_FOLDER = Path("demos")

ROUND_RESULTS_FILE = Path("round_results.csv")
ROUND_PLAYER_STATS_FILE = Path("round_player_stats.csv")

OUTPUT_FILE = Path("round_player_context.csv")


# ================================================================
# UTILITÁRIOS
# ================================================================

def clean_name(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    value = str(value).strip()

    return value if value else None


def team_from_number(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None

    if value == 2:
        return "T"

    if value == 3:
        return "CT"

    return None


def find_demo():
    demos = list(DEMO_FOLDER.glob("*.dem"))

    if not demos:
        raise FileNotFoundError(
            "Nenhuma demo encontrada na pasta demos."
        )

    if len(demos) > 1:
        print("Foram encontradas várias demos:")
        for demo in demos:
            print(f" - {demo}")

        raise RuntimeError(
            "Deixe apenas uma demo na pasta demos."
        )

    return demos[0]


def load_csv(path):
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {path}"
        )

    return pd.read_csv(path)


# ================================================================
# ROUND RESULTS
# ================================================================

def prepare_round_results(df):
    required = {
        "round",
        "event_index",
        "tick_start",
        "winner",
        "reason",
        "half",
        "round_type",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "round_results.csv não possui as colunas necessárias: "
            f"{sorted(missing)}"
        )

    df = df.copy()

    df["round"] = pd.to_numeric(
        df["round"],
        errors="coerce",
    ).astype("Int64")

    df["event_index"] = pd.to_numeric(
        df["event_index"],
        errors="coerce",
    ).astype("Int64")

    df["tick_start"] = pd.to_numeric(
        df["tick_start"],
        errors="coerce",
    )

    df["winner"] = (
        df["winner"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    return df


# ================================================================
# PLAYER STATS
# ================================================================

def prepare_player_stats(df):
    required = {
        "round",
        "event_index",
        "half",
        "round_type",
        "winner",
        "reason",
        "player",
        "kills",
        "deaths",
        "assists",
        "headshots",
        "damage",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "round_player_stats.csv não possui as colunas necessárias: "
            f"{sorted(missing)}"
        )

    df = df.copy()

    df["round"] = pd.to_numeric(
        df["round"],
        errors="coerce",
    ).astype("Int64")

    df["event_index"] = pd.to_numeric(
        df["event_index"],
        errors="coerce",
    ).astype("Int64")

    numeric_columns = [
        "kills",
        "deaths",
        "assists",
        "headshots",
        "damage",
    ]

    for column in numeric_columns:
        df[column] = (
            pd.to_numeric(
                df[column],
                errors="coerce",
            )
            .fillna(0)
        )

    df["player"] = (
        df["player"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    return df


# ================================================================
# ROUND ROSTER
# ================================================================

def get_round_roster(parser, tick):
    snapshots = pd.DataFrame(
        parser.parse_ticks(
            [
                "team_num",
                "team_name",
                "health",
                "is_alive",
                "steamid",
            ],
            ticks=[int(tick)],
        )
    )

    if snapshots.empty:
        return {}

    if "name" not in snapshots.columns:
        return {}

    snapshots["team_num"] = pd.to_numeric(
        snapshots["team_num"],
        errors="coerce",
    )

    roster = {}

    for _, row in snapshots.iterrows():
        player = clean_name(
            row["name"]
        )

        if player is None:
            continue

        team = team_from_number(
            row["team_num"]
        )

        if team is None:
            continue

        roster[player] = team

    return roster


def build_rosters(parser, round_results):
    rosters = {}

    for _, row in round_results.iterrows():
        round_number = int(
            row["round"]
        )

        tick_start = int(
            row["tick_start"]
        )

        roster = get_round_roster(
            parser,
            tick_start,
        )

        rosters[round_number] = roster

        print(
            f"Round {round_number:02d}: "
            f"{len(roster)} jogadores no roster"
        )

    return rosters


# ================================================================
# CONTEXTO DO ROUND
# ================================================================

def add_round_context(
    stats,
    round_results,
    rosters,
):
    result = stats.copy()

    result["team"] = result.apply(
        lambda row: rosters
        .get(int(row["round"]), {})
        .get(row["player"]),
        axis=1,
    )

    # ------------------------------------------------------------
    # Validações
    # ------------------------------------------------------------

    missing_team = result["team"].isna()

    if missing_team.any():
        print()
        print(
            "ATENÇÃO: jogadores sem equipe identificada:"
        )

        print(
            result.loc[
                missing_team,
                [
                    "round",
                    "player",
                ],
            ]
            .drop_duplicates()
            .to_string(index=False)
        )

        print()

    # ------------------------------------------------------------
    # Resultado do round para cada jogador
    # ------------------------------------------------------------

    result["won_round"] = (
        result["team"]
        == result["winner"]
    )

    result["lost_round"] = (
        result["team"].notna()
        & result["winner"].notna()
        & (
            result["team"]
            != result["winner"]
        )
    )

    # ------------------------------------------------------------
    # Sobrevivência
    #
    # Se o jogador não morreu naquele round,
    # consideramos que sobreviveu.
    #
    # Isso será refinado depois, caso encontremos eventos
    # especiais de round que exijam tratamento adicional.
    # ------------------------------------------------------------

    result["survived"] = (
        result["deaths"] == 0
    )

    # ------------------------------------------------------------
    # KAST básico
    #
    # Neste estágio:
    # K = kill
    # A = assist
    # S = survived
    #
    # T (trade) será adicionado posteriormente usando
    # os dados do trade_parser.
    # ------------------------------------------------------------

    result["kast_without_trade"] = (
        (result["kills"] > 0)
        | (result["assists"] > 0)
        | result["survived"]
    )

    # ------------------------------------------------------------
    # Multi-kill
    # ------------------------------------------------------------

    result["multi_kill"] = (
        result["kills"] >= 2
    )

    result["double_kill"] = (
        result["kills"] == 2
    )

    result["triple_kill"] = (
        result["kills"] == 3
    )

    result["quad_kill"] = (
        result["kills"] == 4
    )

    result["ace"] = (
        result["kills"] >= 5
    )

    # ------------------------------------------------------------
    # Participação ofensiva
    # ------------------------------------------------------------

    result["has_kill"] = (
        result["kills"] > 0
    )

    result["has_assist"] = (
        result["assists"] > 0
    )

    result["has_damage"] = (
        result["damage"] > 0
    )

    # ------------------------------------------------------------
    # Resultado categórico
    # ------------------------------------------------------------

    def classify_result(row):
        if row["won_round"]:
            return "WIN"

        if row["lost_round"]:
            return "LOSS"

        return "UNKNOWN"

    result["round_result"] = result.apply(
        classify_result,
        axis=1,
    )

    return result


# ================================================================
# VALIDAÇÃO
# ================================================================

def validate(result, round_results, rosters):
    print()
    print("=" * 80)
    print("VALIDAÇÃO ROUND PLAYER CONTEXT")
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

    expected_lines = (
        len(round_results)
        * result["player"].nunique()
    )

    print(
        f"Linhas esperadas: {expected_lines}"
    )

    print()

    print("Rosters por round:")

    roster_sizes = {
        round_number: len(roster)
        for round_number, roster
        in rosters.items()
    }

    print(roster_sizes)

    print()

    print("Distribuição das equipes:")

    print(
        result["team"]
        .fillna("UNKNOWN")
        .value_counts()
        .to_string()
    )

    print()

    print("Distribuição de resultados:")

    print(
        result["round_result"]
        .value_counts()
        .to_string()
    )

    print()

    print("Sobrevivência:")

    print(
        result["survived"]
        .value_counts()
        .to_string()
    )

    print()

    print("KAST sem Trade:")

    print(
        result["kast_without_trade"]
        .value_counts()
        .to_string()
    )

    print()

    # ------------------------------------------------------------
    # Valida que cada jogador pertence a exatamente um time
    # em cada round.
    # ------------------------------------------------------------

    team_counts = (
        result
        .groupby(
            [
                "round",
                "player",
            ]
        )["team"]
        .nunique(
            dropna=True
        )
    )

    inconsistent = team_counts[
        team_counts > 1
    ]

    print(
        "Jogadores com mais de uma equipe no mesmo round:",
        len(inconsistent),
    )

    print()

    # ------------------------------------------------------------
    # Valida roster 5v5
    # ------------------------------------------------------------

    invalid_rosters = []

    for round_number, roster in rosters.items():
        counts = pd.Series(
            list(roster.values())
        ).value_counts()

        ct_count = int(
            counts.get("CT", 0)
        )

        t_count = int(
            counts.get("T", 0)
        )

        if ct_count != 5 or t_count != 5:
            invalid_rosters.append(
                (
                    round_number,
                    ct_count,
                    t_count,
                )
            )

    print(
        "Rounds fora de 5v5:",
        len(invalid_rosters),
    )

    if invalid_rosters:
        print(
            pd.DataFrame(
                invalid_rosters,
                columns=[
                    "round",
                    "CT",
                    "T",
                ],
            ).to_string(index=False)
        )

    print()

    print("=" * 80)
    print("EXEMPLO - PRIMEIROS 20 REGISTROS")
    print("=" * 80)
    print()

    display_columns = [
        "round",
        "half",
        "round_type",
        "winner",
        "player",
        "team",
        "kills",
        "deaths",
        "assists",
        "headshots",
        "damage",
        "survived",
        "kast_without_trade",
        "multi_kill",
        "won_round",
        "round_result",
    ]

    display_columns = [
        column
        for column in display_columns
        if column in result.columns
    ]

    print(
        result[
            display_columns
        ]
        .head(20)
        .to_string(index=False)
    )


# ================================================================
# MAIN
# ================================================================

def main():
    print()
    print("=" * 80)
    print("LCP - ROUND PLAYER CONTEXT")
    print("=" * 80)
    print()

    demo_path = find_demo()

    print("Demo:")
    print(demo_path)
    print()

    round_results = load_csv(
        ROUND_RESULTS_FILE
    )

    player_stats = load_csv(
        ROUND_PLAYER_STATS_FILE
    )

    round_results = prepare_round_results(
        round_results
    )

    player_stats = prepare_player_stats(
        player_stats
    )

    parser = DemoParser(
        str(demo_path)
    )

    print(
        "Construindo roster de cada round..."
    )
    print()

    rosters = build_rosters(
        parser,
        round_results,
    )

    print()

    result = add_round_context(
        player_stats,
        round_results,
        rosters,
    )

    validate(
        result,
        round_results,
        rosters,
    )

    # ------------------------------------------------------------
    # Ordenação final
    # ------------------------------------------------------------

    result = result.sort_values(
        [
            "round",
            "team",
            "player",
        ]
    ).reset_index(
        drop=True
    )

    # ------------------------------------------------------------
    # Salvar
    # ------------------------------------------------------------

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
    print("ROUND PLAYER CONTEXT CONCLUÍDO")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()