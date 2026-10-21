from pathlib import Path

import pandas as pd


INPUT_FILE = Path("round_player_trade_context.csv")
ENTRY_FILE = Path("trade_entry_rounds.csv")

OUTPUT_FILE = Path("round_player_impact_context.csv")


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {path}"
        )

    return pd.read_csv(path)


def prepare_context(df: pd.DataFrame) -> pd.DataFrame:
    required = {
        "round",
        "player",
        "team",
        "winner",
        "kills",
        "deaths",
        "assists",
        "headshots",
        "damage",
        "survived",
        "kast",
        "won_round",
        "trade_kills",
        "trade_deaths",
        "trade_participation",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "round_player_trade_context.csv não possui as colunas necessárias: "
            f"{sorted(missing)}"
        )

    df = df.copy()

    df["round"] = pd.to_numeric(
        df["round"],
        errors="coerce",
    ).astype("Int64")

    for column in [
        "kills",
        "deaths",
        "assists",
        "headshots",
        "damage",
        "trade_kills",
        "trade_deaths",
    ]:
        df[column] = (
            pd.to_numeric(
                df[column],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

    for column in [
        "survived",
        "kast",
        "won_round",
        "trade_participation",
    ]:
        df[column] = (
            df[column]
            .fillna(False)
            .astype(bool)
        )

    df["player"] = (
        df["player"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    df["team"] = (
        df["team"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    df["winner"] = (
        df["winner"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    return df


def prepare_entry(df: pd.DataFrame) -> pd.DataFrame:
    required = {
        "round_index",
        "entry_killer",
        "entry_victim",
        "entry_tick",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "trade_entry_rounds.csv não possui as colunas necessárias: "
            f"{sorted(missing)}"
        )

    df = df.copy()

    df["round_index"] = pd.to_numeric(
        df["round_index"],
        errors="coerce",
    )

    # entry_rounds também começa em 0.
    df["round"] = (
        df["round_index"] + 1
    ).astype("Int64")

    df["entry_killer"] = (
        df["entry_killer"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    df["entry_victim"] = (
        df["entry_victim"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    df["entry_tick"] = pd.to_numeric(
        df["entry_tick"],
        errors="coerce",
    )

    return df


def build_entry_player_table(entry: pd.DataFrame):
    # ============================================================
    # ENTRY KILL
    # ============================================================

    entry_kills = (
        entry[
            entry["entry_killer"] != ""
        ]
        [
            [
                "round",
                "entry_killer",
            ]
        ]
        .rename(
            columns={
                "entry_killer": "player",
            }
        )
    )

    entry_kills["entry_kill"] = 1

    entry_kills = (
        entry_kills[
            [
                "round",
                "player",
                "entry_kill",
            ]
        ]
    )

    # ============================================================
    # ENTRY DEATH
    # ============================================================

    entry_deaths = (
        entry[
            entry["entry_victim"] != ""
        ]
        [
            [
                "round",
                "entry_victim",
            ]
        ]
        .rename(
            columns={
                "entry_victim": "player",
            }
        )
    )

    entry_deaths["entry_death"] = 1

    entry_deaths = (
        entry_deaths[
            [
                "round",
                "player",
                "entry_death",
            ]
        ]
    )

    return entry_kills, entry_deaths


def merge_entry_context(
    context,
    entry_kills,
    entry_deaths,
):
    result = context.copy()

    result = result.merge(
        entry_kills,
        on=[
            "round",
            "player",
        ],
        how="left",
    )

    result = result.merge(
        entry_deaths,
        on=[
            "round",
            "player",
        ],
        how="left",
    )

    result["entry_kill"] = (
        result["entry_kill"]
        .fillna(0)
        .astype(int)
    )

    result["entry_death"] = (
        result["entry_death"]
        .fillna(0)
        .astype(int)
    )

    # ============================================================
    # FLAGS
    # ============================================================

    result["made_entry"] = (
        result["entry_kill"] > 0
    )

    result["suffered_entry"] = (
        result["entry_death"] > 0
    )

    # ============================================================
    # ENTRY DENTRO DO RESULTADO DO ROUND
    #
    # Aqui não colocamos peso.
    # Apenas registramos o contexto.
    # ============================================================

    result["entry_kill_in_win"] = (
        result["entry_kill"]
        .gt(0)
        & result["won_round"]
    )

    result["entry_kill_in_loss"] = (
        result["entry_kill"]
        .gt(0)
        & ~result["won_round"]
    )

    result["entry_death_in_win"] = (
        result["entry_death"]
        .gt(0)
        & result["won_round"]
    )

    result["entry_death_in_loss"] = (
        result["entry_death"]
        .gt(0)
        & ~result["won_round"]
    )

    # ============================================================
    # CONTEXTO DE CONTRIBUIÇÃO
    #
    # NOVAMENTE: são métricas factuais, NÃO são LCP Score.
    # ============================================================

    result["round_kill_assist_value"] = (
        result["kills"]
        + (
            0.5
            * result["assists"]
        )
    )

    result["round_trade_value"] = (
        result["trade_kills"]
        + result["trade_deaths"]
    )

    result["round_entry_value"] = (
        result["entry_kill"]
        - result["entry_death"]
    )

    result["round_survival_value"] = (
        result["survived"].astype(int)
    )

    return result


def validate(
    context,
    entry,
    result,
):
    print()
    print("=" * 80)
    print("VALIDAÇÃO ROUND PLAYER IMPACT CONTEXT")
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

    # ------------------------------------------------------------
    # Estrutura
    # ------------------------------------------------------------

    expected_lines = (
        result["round"].nunique()
        * result["player"].nunique()
    )

    print(
        f"Linhas esperadas: {expected_lines}"
    )

    if len(result) == expected_lines:
        print(
            "OK: estrutura round x jogador preservada."
        )
    else:
        print(
            "ATENÇÃO: estrutura round x jogador inconsistente."
        )

    print()

    # ------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------

    print(
        f"Rounds de entry na origem: {len(entry)}"
    )

    total_entry_kills = int(
        result["entry_kill"].sum()
    )

    total_entry_deaths = int(
        result["entry_death"].sum()
    )

    print(
        f"Entry kills:   {total_entry_kills}"
    )

    print(
        f"Entry deaths:  {total_entry_deaths}"
    )

    print()

    if total_entry_kills == len(entry):
        print(
            "OK: todos os entry kills foram associados."
        )
    else:
        print(
            "ATENÇÃO: quantidade de entry kills inconsistente."
        )

    if total_entry_deaths == len(entry):
        print(
            "OK: todos os entry deaths foram associados."
        )
    else:
        print(
            "ATENÇÃO: quantidade de entry deaths inconsistente."
        )

    print()

    # ------------------------------------------------------------
    # Um único entry por round
    # ------------------------------------------------------------

    entry_kill_rounds = (
        result[
            result["entry_kill"] > 0
        ]
        .groupby("round")
        .size()
    )

    entry_death_rounds = (
        result[
            result["entry_death"] > 0
        ]
        .groupby("round")
        .size()
    )

    bad_entry_kills = entry_kill_rounds[
        entry_kill_rounds != 1
    ]

    bad_entry_deaths = entry_death_rounds[
        entry_death_rounds != 1
    ]

    print(
        "Rounds com quantidade diferente de 1 entry kill:",
        len(bad_entry_kills),
    )

    print(
        "Rounds com quantidade diferente de 1 entry death:",
        len(bad_entry_deaths),
    )

    print()

    # ------------------------------------------------------------
    # Entry em rounds vencidos/perdidos
    # ------------------------------------------------------------

    print("Entry kills em rounds vencidos:")
    print(
        int(
            result["entry_kill_in_win"].sum()
        )
    )

    print(
        "Entry kills em rounds perdidos:"
    )

    print(
        int(
            result["entry_kill_in_loss"].sum()
        )
    )

    print()

    print(
        "Entry deaths em rounds vencidos:"
    )

    print(
        int(
            result["entry_death_in_win"].sum()
        )
    )

    print(
        "Entry deaths em rounds perdidos:"
    )

    print(
        int(
            result["entry_death_in_loss"].sum()
        )
    )

    print()

    # ------------------------------------------------------------
    # Relação Entry + Trade
    # ------------------------------------------------------------

    print("=" * 80)
    print("ENTRY + TRADE")
    print("=" * 80)
    print()

    entry_trade = result[
        (
            result["entry_kill"]
            > 0
        )
        | (
            result["entry_death"]
            > 0
        )
    ][
        [
            "round",
            "player",
            "team",
            "winner",
            "entry_kill",
            "entry_death",
            "trade_kills",
            "trade_deaths",
            "trade_participation",
            "won_round",
        ]
    ]

    print(
        entry_trade.to_string(
            index=False
        )
    )

    print()

    # ------------------------------------------------------------
    # Ranking puramente descritivo
    # ------------------------------------------------------------

    player_summary = (
        result
        .groupby("player")
        .agg(
            entry_kills=(
                "entry_kill",
                "sum",
            ),
            entry_deaths=(
                "entry_death",
                "sum",
            ),
            entry_rounds=(
                "made_entry",
                "sum",
            ),
            suffered_entry_rounds=(
                "suffered_entry",
                "sum",
            ),
            entry_kills_in_wins=(
                "entry_kill_in_win",
                "sum",
            ),
            entry_kills_in_losses=(
                "entry_kill_in_loss",
                "sum",
            ),
            entry_deaths_in_wins=(
                "entry_death_in_win",
                "sum",
            ),
            entry_deaths_in_losses=(
                "entry_death_in_loss",
                "sum",
            ),
        )
        .reset_index()
    )

    player_summary["entry_difference"] = (
        player_summary["entry_kills"]
        -
        player_summary["entry_deaths"]
    )

    player_summary["entry_success"] = (
        player_summary["entry_kills"]
        /
        (
            player_summary["entry_kills"]
            +
            player_summary["entry_deaths"]
        )
    )

    print("=" * 80)
    print("ENTRY POR JOGADOR")
    print("=" * 80)
    print()

    print(
        player_summary
        .sort_values(
            "entry_difference",
            ascending=False,
        )
        .to_string(
            index=False
        )
    )

    print()

    # ------------------------------------------------------------
    # Amostra
    # ------------------------------------------------------------

    print("=" * 80)
    print("EXEMPLO - PRIMEIROS 25 REGISTROS")
    print("=" * 80)
    print()

    columns = [
        "round",
        "player",
        "team",
        "winner",
        "kills",
        "deaths",
        "assists",
        "trade_kills",
        "trade_deaths",
        "entry_kill",
        "entry_death",
        "survived",
        "kast",
        "won_round",
    ]

    print(
        result[
            columns
        ]
        .head(25)
        .to_string(
            index=False
        )
    )


def main():
    print()
    print("=" * 80)
    print("LCP - ROUND PLAYER IMPACT CONTEXT")
    print("=" * 80)
    print()

    context = load_csv(
        INPUT_FILE
    )

    entry = load_csv(
        ENTRY_FILE
    )

    context = prepare_context(
        context
    )

    entry = prepare_entry(
        entry
    )

    (
        entry_kills,
        entry_deaths,
    ) = build_entry_player_table(
        entry
    )

    result = merge_entry_context(
        context,
        entry_kills,
        entry_deaths,
    )

    validate(
        context,
        entry,
        result,
    )

    result = result.sort_values(
        [
            "round",
            "team",
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
    print("ROUND PLAYER IMPACT CONTEXT CONCLUÍDO")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()