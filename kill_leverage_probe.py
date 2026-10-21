from pathlib import Path

import pandas as pd


INPUT_FILE = Path(
    "round_state_probe.csv"
)

OUTPUT_FILE = Path(
    "kill_leverage_probe.csv"
)


def load_data():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {INPUT_FILE}"
        )

    return pd.read_csv(INPUT_FILE)


def prepare(df):
    df = df.copy()

    numeric_columns = [
        "round",
        "sequence",
        "tick",
        "own_alive_before",
        "enemy_alive_before",
        "difference_before",
        "own_alive_after",
        "enemy_alive_after",
        "difference_after",
    ]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

    boolean_columns = [
        "is_first_kill",
        "is_last_kill",
        "killer_team_won",
    ]

    for column in boolean_columns:
        if column in df.columns:
            df[column] = (
                df[column]
                .fillna(False)
                .astype(bool)
            )

    # Preservar nomes dos jogadores exatamente
    # como estão na origem.
    for column in [
        "attacker",
        "victim",
        "attacker_team",
        "victim_team",
        "winner",
        "transition",
    ]:
        if column in df.columns:
            df[column] = (
                df[column]
                .fillna("")
                .astype(str)
                .str.strip()
            )

    return df


COLUNAS_ESTADO = [
    "round",
    "sequence",
    "own_alive_before",
    "enemy_alive_before",
    "own_alive_after",
    "enemy_alive_after",
    "difference_before",
    "difference_after",
]


def descartar_rounds_incompletos(df):
    """Remove rounds em que a contagem de vivos nao pode ser lida.

    POR QUE ISSO EXISTE
    O prepare() converte as colunas numericas com errors="coerce", que
    transforma qualquer valor ilegivel em NaN. Logo depois, o add_exact_state()
    fazia .astype(int) direto nessas colunas, e uma unica linha com NaN
    derrubava o script inteiro com IntCastingNaNError. Era isso que fazia a
    partida perder Leverage e Clutch.

    Preencher o NaN com zero seria pior do que falhar: criaria um estado
    "0v0" inexistente e contaminaria o modelo. E descartar so a linha quebraria
    a sequencia de kills do round, que a validacao exige inteira.

    Entao o round inteiro sai, e fica registrado quantos sairam e por que.
    """
    presentes = [c for c in COLUNAS_ESTADO if c in df.columns]

    faltando = [c for c in COLUNAS_ESTADO if c not in df.columns]
    if faltando:
        raise ValueError(
            "round_state_probe.csv nao tem as colunas: " + ", ".join(faltando)
        )

    ruins = df[presentes].isna().any(axis=1)

    if not ruins.any():
        return df

    rounds_ruins = sorted(df.loc[ruins, "round"].dropna().unique().tolist())
    linhas_ruins = int(ruins.sum())

    resultado = df[~df["round"].isin(rounds_ruins)].copy()

    print()
    print("=" * 80)
    print("AVISO: ESTADO INCOMPLETO")
    print("=" * 80)
    print()
    print("O round_state_probe.csv tem %d linha(s) sem contagem de vivos." % linhas_ruins)
    print("Round(s) descartado(s) por inteiro: %s"
          % ", ".join(str(int(r)) for r in rounds_ruins))
    print("Motivo: sem o numero de jogadores vivos nao da para calcular")
    print("        o leverage da kill, e inventar o valor falsearia o modelo.")
    print("Kills antes: %d   depois: %d" % (len(df), len(resultado)))
    print()

    if resultado.empty:
        raise ValueError(
            "Nenhum round com estado completo. Verifique o round_state_probe.py."
        )

    return resultado


def add_exact_state(df):
    result = df.copy()

    # ============================================================
    # ESTADO EXATO ANTES
    # ============================================================

    result["exact_state_before"] = (
        result["own_alive_before"]
        .astype(int)
        .astype(str)
        + "v"
        + result["enemy_alive_before"]
        .astype(int)
        .astype(str)
    )

    # ============================================================
    # ESTADO EXATO DEPOIS
    # ============================================================

    result["exact_state_after"] = (
        result["own_alive_after"]
        .astype(int)
        .astype(str)
        + "v"
        + result["enemy_alive_after"]
        .astype(int)
        .astype(str)
    )

    # ============================================================
    # TOTAL DE JOGADORES VIVOS
    # ============================================================

    result["total_alive_before"] = (
        result["own_alive_before"]
        + result["enemy_alive_before"]
    )

    result["total_alive_after"] = (
        result["own_alive_after"]
        + result["enemy_alive_after"]
    )

    # ============================================================
    # VANTAGEM / DESVANTAGEM
    # ============================================================

    result["numeric_disadvantage"] = (
        result["difference_before"]
        .clip(upper=0)
        .abs()
    )

    result["numeric_advantage"] = (
        result["difference_before"]
        .clip(lower=0)
    )

    result["numeric_pressure"] = (
        result["enemy_alive_before"]
        - result["own_alive_before"]
    )

    # ============================================================
    # ESTADOS ESPECÍFICOS
    # ============================================================

    result["is_5v5"] = (
        (result["own_alive_before"] == 5)
        & (result["enemy_alive_before"] == 5)
    )

    result["is_4v4"] = (
        (result["own_alive_before"] == 4)
        & (result["enemy_alive_before"] == 4)
    )

    result["is_3v3"] = (
        (result["own_alive_before"] == 3)
        & (result["enemy_alive_before"] == 3)
    )

    result["is_2v2"] = (
        (result["own_alive_before"] == 2)
        & (result["enemy_alive_before"] == 2)
    )

    result["is_1v1"] = (
        (result["own_alive_before"] == 1)
        & (result["enemy_alive_before"] == 1)
    )

    result["is_own_last_alive"] = (
        result["own_alive_before"] == 1
    )

    result["is_enemy_last_alive"] = (
        result["enemy_alive_before"] == 1
    )

    # ============================================================
    # PRESSÃO
    # ============================================================

    result["high_pressure"] = (
        result["difference_before"] <= -2
    )

    result["close_game"] = (
        result["difference_before"].abs() <= 1
    )

    result["critical_state"] = (
        result["is_1v1"]
        | result["is_own_last_alive"]
        | result["is_enemy_last_alive"]
        | result["high_pressure"]
    )

    return result


def add_progress_and_phase(df):
    result = df.copy()

    # ============================================================
    # PROGRESSO DO ROUND
    # ============================================================

    total_kills = (
        result.groupby("round")["sequence"]
        .transform("max")
    )

    result["total_player_kills"] = total_kills

    result["kills_before"] = (
        result["sequence"] - 1
    )

    result["kills_after"] = (
        total_kills - result["sequence"]
    )

    result["progress"] = (
        result["kills_before"]
        / total_kills
    )

    result["progress_percent"] = (
        result["progress"] * 100
    )

    # ============================================================
    # FASE DO ROUND
    # ============================================================

    result["phase"] = pd.cut(
        result["progress"],
        bins=[
            -0.000001,
            0.25,
            0.50,
            0.75,
            1.000001,
        ],
        labels=[
            "EARLY",
            "EARLY_MID",
            "LATE_MID",
            "LATE",
        ],
    )

    return result


def add_transition_validation(df):
    result = df.copy()

    result["transition"] = result["transition"].fillna("").astype(str)

    return result


def aggregate_exact_state(df):
    summary = (
        df.groupby(
            [
                "exact_state_before",
                "exact_state_after",
                "transition",
            ]
        )
        .agg(
            events=(
                "round",
                "size",
            ),
            rounds=(
                "round",
                "nunique",
            ),
            wins=(
                "killer_team_won",
                "sum",
            ),
            losses=(
                "killer_team_won",
                lambda x: (~x).sum(),
            ),
            first_kills=(
                "is_first_kill",
                "sum",
            ),
            last_kills=(
                "is_last_kill",
                "sum",
            ),
            last_enemy_kills=(
                "is_enemy_last_alive",
                "sum",
            ),
            last_own_kills=(
                "is_own_last_alive",
                "sum",
            ),
        )
        .reset_index()
    )

    summary["event_win_rate"] = (
        summary["wins"]
        / summary["events"]
    )

    return summary


def aggregate_state_before(df):
    summary = (
        df.groupby(
            "exact_state_before"
        )
        .agg(
            events=(
                "round",
                "size",
            ),
            wins=(
                "killer_team_won",
                "sum",
            ),
            losses=(
                "killer_team_won",
                lambda x: (~x).sum(),
            ),
            first_kills=(
                "is_first_kill",
                "sum",
            ),
            equalizers=(
                "transition",
                lambda x: (
                    x == "EQUALIZER"
                ).sum(),
            ),
            regains=(
                "transition",
                lambda x: (
                    x == "REGAIN_ADVANTAGE"
                ).sum(),
            ),
            extensions=(
                "transition",
                lambda x: (
                    x == "EXTEND_ADVANTAGE"
                ).sum(),
            ),
            disadvantage_pressure=(
                "transition",
                lambda x: (
                    x == "DISADVANTAGE_PRESSURE"
                ).sum(),
            ),
        )
        .reset_index()
    )

    summary["event_win_rate"] = (
        summary["wins"]
        / summary["events"]
    )

    return summary


def aggregate_player_state(df):
    summary = (
        df.groupby(
            [
                "attacker",
                "exact_state_before",
            ]
        )
        .agg(
            events=(
                "round",
                "size",
            ),
            wins=(
                "killer_team_won",
                "sum",
            ),
            first_kills=(
                "is_first_kill",
                "sum",
            ),
            last_kills=(
                "is_last_kill",
                "sum",
            ),
            equalizers=(
                "transition",
                lambda x: (
                    x == "EQUALIZER"
                ).sum(),
            ),
            regains=(
                "transition",
                lambda x: (
                    x == "REGAIN_ADVANTAGE"
                ).sum(),
            ),
            extensions=(
                "transition",
                lambda x: (
                    x == "EXTEND_ADVANTAGE"
                ).sum(),
            ),
            disadvantage_pressure=(
                "transition",
                lambda x: (
                    x == "DISADVANTAGE_PRESSURE"
                ).sum(),
            ),
        )
        .reset_index()
    )

    summary["event_win_rate"] = (
        summary["wins"]
        / summary["events"]
    )

    return summary


def aggregate_player(df):
    summary = (
        df.groupby(
            "attacker"
        )
        .agg(
            kills=(
                "round",
                "size",
            ),
            winning_events=(
                "killer_team_won",
                "sum",
            ),
            first_kills=(
                "is_first_kill",
                "sum",
            ),
            equalizers=(
                "transition",
                lambda x: (
                    x == "EQUALIZER"
                ).sum(),
            ),
            regains=(
                "transition",
                lambda x: (
                    x == "REGAIN_ADVANTAGE"
                ).sum(),
            ),
            extensions=(
                "transition",
                lambda x: (
                    x == "EXTEND_ADVANTAGE"
                ).sum(),
            ),
            disadvantage_pressure=(
                "transition",
                lambda x: (
                    x == "DISADVANTAGE_PRESSURE"
                ).sum(),
            ),
            last_kills=(
                "is_last_kill",
                "sum",
            ),
            enemy_last_kills=(
                "is_enemy_last_alive",
                "sum",
            ),
            own_last_kills=(
                "is_own_last_alive",
                "sum",
            ),
            high_pressure_kills=(
                "high_pressure",
                "sum",
            ),
            critical_state_kills=(
                "critical_state",
                "sum",
            ),
            average_numeric_disadvantage=(
                "numeric_disadvantage",
                "mean",
            ),
        )
        .reset_index()
    )

    summary["event_win_rate"] = (
        summary["winning_events"]
        / summary["kills"]
    )

    summary["high_pressure_rate"] = (
        summary["high_pressure_kills"]
        / summary["kills"]
    )

    summary["critical_state_rate"] = (
        summary["critical_state_kills"]
        / summary["kills"]
    )

    return summary


def print_exact_states(summary):
    print()
    print("=" * 80)
    print("ESTADOS EXATOS")
    print("=" * 80)
    print()

    print(
        summary.sort_values(
            [
                "exact_state_before",
                "events",
            ],
            ascending=[
                True,
                False,
            ],
        ).to_string(
            index=False
        )
    )


def print_state_before(summary):
    print()
    print("=" * 80)
    print("ESTADO ANTES DA KILL")
    print("=" * 80)
    print()

    print(
        summary.sort_values(
            "events",
            ascending=False,
        ).to_string(
            index=False
        )
    )


def print_player(summary):
    print()
    print("=" * 80)
    print("PERFIL POR JOGADOR")
    print("=" * 80)
    print()

    columns = [
        "attacker",
        "kills",
        "winning_events",
        "event_win_rate",
        "first_kills",
        "equalizers",
        "regains",
        "extensions",
        "disadvantage_pressure",
        "last_kills",
        "enemy_last_kills",
        "own_last_kills",
        "high_pressure_kills",
        "critical_state_kills",
        "average_numeric_disadvantage",
    ]

    print(
        summary.sort_values(
            "winning_events",
            ascending=False,
        )[
            columns
        ].to_string(
            index=False
        )
    )


def print_player_state(summary):
    print()
    print("=" * 80)
    print("JOGADOR × ESTADO")
    print("=" * 80)
    print()

    print(
        summary.sort_values(
            [
                "attacker",
                "exact_state_before",
            ]
        ).to_string(
            index=False
        )
    )


def print_critical_events(df):
    print()
    print("=" * 80)
    print("KILLS EM ESTADOS CRÍTICOS")
    print("=" * 80)
    print()

    critical = df[
        df["critical_state"]
    ].copy()

    print(
        f"Quantidade: {len(critical)}"
    )

    if critical.empty:
        print(
            "Nenhuma kill em estado crítico."
        )
        return

    columns = [
        "round",
        "sequence",
        "attacker",
        "victim",
        "attacker_team",
        "exact_state_before",
        "exact_state_after",
        "transition",
        "phase",
        "killer_team_won",
        "is_first_kill",
        "is_last_kill",
    ]

    columns = [
        column
        for column in columns
        if column in critical.columns
    ]

    print(
        critical[
            columns
        ].to_string(
            index=False
        )
    )


def validate(df):
    print()
    print("=" * 80)
    print("VALIDAÇÃO")
    print("=" * 80)
    print()

    print(
        "Kills:",
        len(df),
    )

    print(
        "Rounds:",
        df["round"].nunique(),
    )

    print(
        "Jogadores:",
        df["attacker"].nunique(),
    )

    print()

    print(
        "Kills individuais: " + str(len(df))
    )

    print(
        "Estados exatos encontrados:",
        df["exact_state_before"].nunique(),
    )

    print(
        "Transições encontradas:",
        df["transition"].nunique(),
    )

    print(
        "Fases encontradas:",
        df["phase"].nunique(),
    )


def validate_individual_events(df):
    required_columns = [
        "round",
        "sequence",
        "attacker",
        "victim",
        "attacker_team",
        "exact_state_before",
        "exact_state_after",
        "transition",
        "phase",
        "killer_team_won",
        "is_first_kill",
        "is_last_kill",
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            "Colunas obrigatórias não encontradas no DataFrame: "
            + ", ".join(missing)
        )

    if len(df) == 0:
        raise ValueError(
            "Nenhuma kill individual encontrada."
        )

    if df["attacker"].isna().any():
        raise ValueError(
            "Existem attackers vazios ou nulos."
        )

    if df["victim"].isna().any():
        raise ValueError(
            "Existem victims vazios ou nulos."
        )

    if df["exact_state_before"].isna().any():
        raise ValueError(
            "Existem estados exatos antes da kill ausentes."
        )

    if df["exact_state_after"].isna().any():
        raise ValueError(
            "Existem estados exatos depois da kill ausentes."
        )

    # Cada round deve começar na sequência 1.
    first_sequences = (
        df.groupby("round")["sequence"]
        .min()
    )

    invalid_first_sequences = (
        first_sequences[
            first_sequences != 1
        ]
    )

    if not invalid_first_sequences.empty:
        raise ValueError(
            "Existem rounds cuja primeira kill não começa na sequência 1: "
            + str(
                invalid_first_sequences.to_dict()
            )
        )

    # Cada round deve terminar exatamente em uma last_kill.
    last_kill_counts = (
        df.groupby("round")["is_last_kill"]
        .sum()
    )

    invalid_last_counts = (
        last_kill_counts[
            last_kill_counts != 1
        ]
    )

    if not invalid_last_counts.empty:
        raise ValueError(
            "Existem rounds sem exatamente uma last_kill: "
            + str(
                invalid_last_counts.to_dict()
            )
        )


def main():
    print()
    print("=" * 80)
    print("LCP - KILL LEVERAGE PROBE")
    print("=" * 80)
    print()

    df = load_data()

    df = prepare(
        df
    )

    df = descartar_rounds_incompletos(
        df
    )

    df = add_exact_state(
        df
    )

    df = add_progress_and_phase(
        df
    )

    df = add_transition_validation(
        df
    )

    validate_individual_events(
        df
    )

    validate(
        df
    )

    # ============================================================
    # RESUMOS
    # ============================================================

    exact_state_summary = (
        aggregate_exact_state(
            df
        )
    )

    state_before_summary = (
        aggregate_state_before(
            df
        )
    )

    player_state_summary = (
        aggregate_player_state(
            df
        )
    )

    player_summary = (
        aggregate_player(
            df
        )
    )

    # ============================================================
    # IMPRESSÃO DOS RESUMOS
    # ============================================================

    print_exact_states(
        exact_state_summary
    )

    print_state_before(
        state_before_summary
    )

    print_player(
        player_summary
    )

    print_player_state(
        player_state_summary
    )

    print_critical_events(
        df
    )

    # ============================================================
    # SALVA A TABELA PRINCIPAL COM AS KILLS INDIVIDUAIS
    # ============================================================

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
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
    print(
        "Linhas gravadas:",
        len(df),
    )

    print(
        "Colunas gravadas:",
        len(df.columns),
    )

    print()
    print("=" * 80)
    print("KILL LEVERAGE PROBE CONCLUÍDO")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()