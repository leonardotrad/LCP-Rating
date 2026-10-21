from pathlib import Path

import pandas as pd


ROUND_PLAYER_CONTEXT = Path("round_player_context.csv")
TRADE_EVENTS = Path("trade_events.csv")

OUTPUT_FILE = Path("round_player_trade_context.csv")


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
        "survived",
        "kast_without_trade",
        "won_round",
        "round_result",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "round_player_context.csv não possui as colunas necessárias: "
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
        "kast_without_trade",
        "won_round",
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

    return df


def prepare_trade_events(df: pd.DataFrame) -> pd.DataFrame:
    required = {
        "round_index",
        "death_tick",
        "trade_tick",
        "trade_delay_seconds",
        "player_traded",
        "enemy_killer",
        "trade_killer",
        "trade_victim",
        "traded_entry_kill",
        "traded_entry_death",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            "trade_events.csv não possui as colunas necessárias: "
            f"{sorted(missing)}"
        )

    df = df.copy()

    df["round_index"] = pd.to_numeric(
        df["round_index"],
        errors="coerce",
    )

    # trade_events usa round_index começando em 0.
    # Nosso contexto usa rounds de 1 a 22.
    df["round"] = (
        df["round_index"] + 1
    ).astype("Int64")

    for column in [
        "death_tick",
        "trade_tick",
        "trade_delay_seconds",
    ]:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    for column in [
        "player_traded",
        "enemy_killer",
        "trade_killer",
        "trade_victim",
    ]:
        df[column] = (
            df[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    for column in [
        "traded_entry_kill",
        "traded_entry_death",
    ]:
        df[column] = (
            df[column]
            .fillna(False)
            .astype(bool)
        )

    return df


def aggregate_trade_stats(trades: pd.DataFrame):
    # ============================================================
    # TRADE DEATHS
    #
    # player_traded = jogador que morreu e foi recuperado.
    # ============================================================

    trade_deaths = (
        trades[
            trades["player_traded"] != ""
        ]
        .groupby(
            [
                "round",
                "player_traded",
            ],
            dropna=False,
        )
        .agg(
            trade_deaths=(
                "trade_tick",
                "size",
            ),
            trade_death_entry=(
                "traded_entry_death",
                "sum",
            ),
        )
        .reset_index()
        .rename(
            columns={
                "player_traded": "player",
            }
        )
    )

    # ============================================================
    # TRADE KILLS
    #
    # trade_killer = jogador que conseguiu o trade.
    # ============================================================

    trade_kills = (
        trades[
            trades["trade_killer"] != ""
        ]
        .groupby(
            [
                "round",
                "trade_killer",
            ],
            dropna=False,
        )
        .agg(
            trade_kills=(
                "trade_victim",
                "size",
            ),
            trade_kills_on_entry=(
                "traded_entry_kill",
                "sum",
            ),
        )
        .reset_index()
        .rename(
            columns={
                "trade_killer": "player",
            }
        )
    )

    # ============================================================
    # RESUMO DE EVENTOS DE TRADE
    #
    # Mantemos também a menor demora encontrada no round,
    # apenas como informação auxiliar.
    # ============================================================

    trade_summary = (
        trades.groupby(
            [
                "round",
                "player_traded",
            ],
            dropna=False,
        )
        .agg(
            fastest_trade_delay=(
                "trade_delay_seconds",
                "min",
            ),
            average_trade_delay=(
                "trade_delay_seconds",
                "mean",
            ),
        )
        .reset_index()
        .rename(
            columns={
                "player_traded": "player",
            }
        )
    )

    return (
        trade_kills,
        trade_deaths,
        trade_summary,
    )


def merge_trade_context(
    context,
    trade_kills,
    trade_deaths,
    trade_summary,
):
    result = context.copy()

    # ============================================================
    # TRADE KILLS
    # ============================================================

    result = result.merge(
        trade_kills[
            [
                "round",
                "player",
                "trade_kills",
                "trade_kills_on_entry",
            ]
        ],
        on=[
            "round",
            "player",
        ],
        how="left",
    )

    # ============================================================
    # TRADE DEATHS
    # ============================================================

    result = result.merge(
        trade_deaths[
            [
                "round",
                "player",
                "trade_deaths",
                "trade_death_entry",
            ]
        ],
        on=[
            "round",
            "player",
        ],
        how="left",
    )

    # ============================================================
    # INFORMAÇÕES AUXILIARES
    # ============================================================

    result = result.merge(
        trade_summary[
            [
                "round",
                "player",
                "fastest_trade_delay",
                "average_trade_delay",
            ]
        ],
        on=[
            "round",
            "player",
        ],
        how="left",
    )

    for column in [
        "trade_kills",
        "trade_kills_on_entry",
        "trade_deaths",
        "trade_death_entry",
    ]:
        result[column] = (
            pd.to_numeric(
                result[column],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

    # ============================================================
    # MARCADORES
    # ============================================================

    result["was_traded"] = (
        result["trade_deaths"] > 0
    )

    result["made_trade"] = (
        result["trade_kills"] > 0
    )

    result["trade_participation"] = (
        result["was_traded"]
        | result["made_trade"]
    )

    # ============================================================
    # KAST REAL
    #
    # K = kill
    # A = assist
    # S = survive
    # T = was traded
    # ============================================================

    result["kast"] = (
        (result["kills"] > 0)
        | (result["assists"] > 0)
        | result["survived"]
        | result["was_traded"]
    )

    # ============================================================
    # KAST anterior para comparação
    # ============================================================

    result["kast_changed_by_trade"] = (
        result["kast"]
        & ~result["kast_without_trade"]
    )

    # ============================================================
    # CONTRIBUIÇÃO DE TRADE
    #
    # Não é ainda um peso do LCP.
    # É somente uma variável factual.
    # ============================================================

    result["trade_contribution"] = (
        result["trade_kills"]
        + result["trade_deaths"]
    )

    return result


def validate(
    context,
    trades,
    result,
):
    print()
    print("=" * 80)
    print("VALIDAÇÃO TRADE CONTEXT")
    print("=" * 80)
    print()

    print(
        f"Eventos de trade: {len(trades)}"
    )

    print(
        f"Linhas jogador x round: {len(result)}"
    )

    print(
        f"Rounds: {result['round'].nunique()}"
    )

    print(
        f"Jogadores: {result['player'].nunique()}"
    )

    print()

    # ------------------------------------------------------------
    # Cada evento de trade deve gerar:
    # 1 trade death
    # 1 trade kill
    # ------------------------------------------------------------

    total_trade_kills = int(
        result["trade_kills"].sum()
    )

    total_trade_deaths = int(
        result["trade_deaths"].sum()
    )

    print(
        f"Trade kills:  {total_trade_kills}"
    )

    print(
        f"Trade deaths: {total_trade_deaths}"
    )

    print()

    if total_trade_kills != len(trades):
        print(
            "ATENÇÃO: quantidade de trade kills "
            "não bate com eventos de trade."
        )
    else:
        print(
            "OK: todos os eventos possuem trade kill."
        )

    if total_trade_deaths != len(trades):
        print(
            "ATENÇÃO: quantidade de trade deaths "
            "não bate com eventos de trade."
        )
    else:
        print(
            "OK: todos os eventos possuem trade death."
        )

    print()

    # ------------------------------------------------------------
    # KAST
    # ------------------------------------------------------------

    old_kast = int(
        context["kast_without_trade"].sum()
    )

    new_kast = int(
        result["kast"].sum()
    )

    changed = int(
        result["kast_changed_by_trade"].sum()
    )

    print(
        f"KAST sem Trade: {old_kast}"
    )

    print(
        f"KAST com Trade: {new_kast}"
    )

    print(
        f"Rounds/jogador adicionados por Trade: {changed}"
    )

    print()

    # ------------------------------------------------------------
    # Trades por jogador
    # ------------------------------------------------------------

    player_trade = (
        result.groupby("player")
        .agg(
            trade_kills=(
                "trade_kills",
                "sum",
            ),
            trade_deaths=(
                "trade_deaths",
                "sum",
            ),
            trade_rounds=(
                "trade_participation",
                "sum",
            ),
            kast=(
                "kast",
                "sum",
            ),
        )
        .reset_index()
        .sort_values(
            [
                "trade_rounds",
                "trade_kills",
            ],
            ascending=False,
        )
    )

    print("=" * 80)
    print("TRADE POR JOGADOR")
    print("=" * 80)
    print()

    print(
        player_trade.to_string(
            index=False
        )
    )

    print()

    # ------------------------------------------------------------
    # Eventos de trade que também envolveram entry
    # ------------------------------------------------------------

    entry_trade_kills = int(
        trades[
            "traded_entry_kill"
        ].sum()
    )

    entry_trade_deaths = int(
        trades[
            "traded_entry_death"
        ].sum()
    )

    print(
        "Trade kills envolvendo entry:",
        entry_trade_kills,
    )

    print(
        "Trade deaths envolvendo entry:",
        entry_trade_deaths,
    )

    print()

    # ------------------------------------------------------------
    # Validação estrutural
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
    # Amostra
    # ------------------------------------------------------------

    print("=" * 80)
    print("EXEMPLO DE ROUNDS COM TRADE")
    print("=" * 80)
    print()

    sample = result[
        result["trade_participation"]
    ][
        [
            "round",
            "player",
            "team",
            "winner",
            "kills",
            "deaths",
            "assists",
            "trade_kills",
            "trade_deaths",
            "survived",
            "kast",
            "won_round",
        ]
    ].head(25)

    if sample.empty:
        print(
            "Nenhum evento encontrado."
        )
    else:
        print(
            sample.to_string(
                index=False
            )
        )


def main():
    print()
    print("=" * 80)
    print("LCP - ROUND PLAYER TRADE CONTEXT")
    print("=" * 80)
    print()

    context = load_csv(
        ROUND_PLAYER_CONTEXT
    )

    trades = load_csv(
        TRADE_EVENTS
    )

    context = prepare_context(
        context
    )

    trades = prepare_trade_events(
        trades
    )

    (
        trade_kills,
        trade_deaths,
        trade_summary,
    ) = aggregate_trade_stats(
        trades
    )

    result = merge_trade_context(
        context,
        trade_kills,
        trade_deaths,
        trade_summary,
    )

    validate(
        context,
        trades,
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
    print("ROUND PLAYER TRADE CONTEXT CONCLUÍDO")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()