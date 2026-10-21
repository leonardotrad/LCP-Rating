from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = (
    BASE_DIR / "kill_leverage_probe.csv"
)

OUTPUT_EVENTS = (
    BASE_DIR / "kill_win_probability_leverage.csv"
)

OUTPUT_PLAYERS = (
    BASE_DIR / "kill_win_probability_player_summary.csv"
)

OUTPUT_STATES = (
    BASE_DIR / "kill_state_win_probability.csv"
)


# ============================================================
# CONFIGURAÇÃO
# ============================================================

MAX_ITERATIONS = 5000

LEARNING_RATE = 0.03

REGULARIZATION = 0.001

EPSILON = 1e-9


# ============================================================
# UTILITÁRIOS
# ============================================================


def parse_state(
    state: str,
) -> tuple[int, int]:

    own, enemy = state.lower().split("v")

    return int(own), int(enemy)


def sigmoid(
    value: float,
) -> float:

    # Evita overflow numérico.
    if value >= 35:
        return 1.0

    if value <= -35:
        return 0.0

    return 1.0 / (
        1.0 + math.exp(-value)
    )


# ============================================================
# MODELO
# ============================================================
#
# P(vitória) =
#
# sigmoid(
#     intercept
#     + own_coefficient * próprios vivos
#     - enemy_coefficient * inimigos vivos
# )
#
# Os coeficientes próprios são mantidos positivos.
#
# Isso garante:
#
# mais aliados -> maior probabilidade
# mais inimigos -> menor probabilidade
#
# O modelo é suave, portanto não cria platôs artificiais.
#
# ============================================================


def fit_monotonic_logistic(
    training_df: pd.DataFrame,
) -> tuple[float, float, float]:

    data = training_df.copy()

    parsed = (
        data["exact_state_before"]
        .apply(parse_state)
    )

    data["own_alive"] = (
        parsed.apply(lambda x: x[0])
    )

    data["enemy_alive"] = (
        parsed.apply(lambda x: x[1])
    )

    # --------------------------------------------------------
    # Peso por round.
    #
    # Cada round recebe peso total 1.
    #
    # Assim rounds com muitas kills não dominam o ajuste.
    # --------------------------------------------------------

    kills_per_round = (
        data.groupby("round")["round"]
        .transform("size")
    )

    data["weight"] = (
        1.0
        / kills_per_round
    )

    x_own = (
        data["own_alive"]
        .astype(float)
        .to_numpy()
    )

    x_enemy = (
        data["enemy_alive"]
        .astype(float)
        .to_numpy()
    )

    y = (
        data["killer_team_won"]
        .astype(float)
        .to_numpy()
    )

    weights = (
        data["weight"]
        .astype(float)
        .to_numpy()
    )

    # --------------------------------------------------------
    # Inicialização.
    #
    # Intercepto próximo da taxa geral.
    # --------------------------------------------------------

    global_probability = (
        data.groupby("round")
        ["killer_team_won"]
        .first()
        .mean()
    )

    global_probability = min(
        max(
            float(global_probability),
            0.01,
        ),
        0.99,
    )

    intercept = math.log(
        global_probability
        / (
            1.0
            - global_probability
        )
    )

    own_coefficient = 0.35

    enemy_coefficient = 0.35

    # --------------------------------------------------------
    # Gradiente descendente.
    # --------------------------------------------------------

    total_weight = (
        weights.sum()
    )

    previous_loss = None

    for _ in range(
        MAX_ITERATIONS
    ):

        z = (
            intercept
            + own_coefficient * x_own
            - enemy_coefficient * x_enemy
        )

        probabilities = np.array(
            [
                sigmoid(float(value))
                for value in z
            ]
        )

        residual = (
            probabilities
            - y
        )

        weighted_residual = (
            residual
            * weights
        )

        gradient_intercept = (
            weighted_residual.sum()
            / total_weight
        )

        gradient_own = (
            (
                weighted_residual
                * x_own
            ).sum()
            / total_weight
        )

        gradient_enemy = (
            (
                weighted_residual
                * (
                    -x_enemy
                )
            ).sum()
            / total_weight
        )

        # ----------------------------------------------------
        # Regularização pequena.
        # ----------------------------------------------------

        gradient_intercept += (
            REGULARIZATION
            * intercept
        )

        gradient_own += (
            REGULARIZATION
            * own_coefficient
        )

        gradient_enemy += (
            REGULARIZATION
            * enemy_coefficient
        )

        intercept -= (
            LEARNING_RATE
            * gradient_intercept
        )

        own_coefficient -= (
            LEARNING_RATE
            * gradient_own
        )

        enemy_coefficient -= (
            LEARNING_RATE
            * gradient_enemy
        )

        # ----------------------------------------------------
        # Garante monotonicidade.
        # ----------------------------------------------------

        own_coefficient = max(
            own_coefficient,
            EPSILON,
        )

        enemy_coefficient = max(
            enemy_coefficient,
            EPSILON,
        )

        # ----------------------------------------------------
        # Log-loss para verificar convergência.
        # ----------------------------------------------------

        clipped = np.clip(
            probabilities,
            1e-7,
            1.0 - 1e-7,
        )

        loss = (
            -(
                weights
                * (
                    y * np.log(clipped)
                    + (
                        1.0 - y
                    )
                    * np.log(
                        1.0 - clipped
                    )
                )
            ).sum()
            / total_weight
        )

        loss += (
            0.5
            * REGULARIZATION
            * (
                intercept ** 2
                + own_coefficient ** 2
                + enemy_coefficient ** 2
            )
        )

        if previous_loss is not None:

            if abs(
                previous_loss - loss
            ) < 1e-10:

                break

        previous_loss = loss

    return (
        float(intercept),
        float(own_coefficient),
        float(enemy_coefficient),
    )


# ============================================================
# PROBABILIDADE
# ============================================================


def state_probability(
    own_alive: int,
    enemy_alive: int,
    intercept: float,
    own_coefficient: float,
    enemy_coefficient: float,
) -> float:

    # Estados terminais.

    if enemy_alive <= 0 and own_alive > 0:
        return 1.0

    if own_alive <= 0 and enemy_alive > 0:
        return 0.0

    if own_alive <= 0 and enemy_alive <= 0:
        return 0.5

    linear_value = (
        intercept
        + own_coefficient
        * own_alive
        - enemy_coefficient
        * enemy_alive
    )

    return sigmoid(
        linear_value
    )


# ============================================================
# MATRIZ COMPLETA
# ============================================================


def build_state_table(
    intercept: float,
    own_coefficient: float,
    enemy_coefficient: float,
) -> pd.DataFrame:

    rows = []

    for own_alive in range(1, 6):

        for enemy_alive in range(1, 6):

            probability = (
                state_probability(
                    own_alive,
                    enemy_alive,
                    intercept,
                    own_coefficient,
                    enemy_coefficient,
                )
            )

            rows.append(
                {
                    "exact_state": (
                        f"{own_alive}v{enemy_alive}"
                    ),
                    "own_alive": (
                        own_alive
                    ),
                    "enemy_alive": (
                        enemy_alive
                    ),
                    "win_probability": (
                        probability
                    ),
                }
            )

    return pd.DataFrame(
        rows
    )


# ============================================================
# LEAVE-ONE-ROUND-OUT
# ============================================================


def calculate_leverage(
    df: pd.DataFrame,
) -> pd.DataFrame:

    rows = []

    rounds = sorted(
        df["round"]
        .dropna()
        .unique()
    )

    for current_round in rounds:

        training_df = df[
            df["round"]
            != current_round
        ].copy()

        test_df = df[
            df["round"]
            == current_round
        ].copy()

        (
            intercept,
            own_coefficient,
            enemy_coefficient,
        ) = fit_monotonic_logistic(
            training_df
        )

        for _, row in test_df.iterrows():

            (
                own_before,
                enemy_before,
            ) = parse_state(
                row[
                    "exact_state_before"
                ]
            )

            (
                own_after,
                enemy_after,
            ) = parse_state(
                row[
                    "exact_state_after"
                ]
            )

            probability_before = (
                state_probability(
                    own_before,
                    enemy_before,
                    intercept,
                    own_coefficient,
                    enemy_coefficient,
                )
            )

            probability_after = (
                state_probability(
                    own_after,
                    enemy_after,
                    intercept,
                    own_coefficient,
                    enemy_coefficient,
                )
            )

            leverage = (
                probability_after
                - probability_before
            )

            # Pequenas diferenças negativas de
            # arredondamento não devem gerar valor negativo.

            leverage = max(
                leverage,
                0.0,
            )

            rows.append(
                {
                    "round": row[
                        "round"
                    ],
                    "sequence": row[
                        "sequence"
                    ],
                    "tick": row[
                        "tick"
                    ],
                    "attacker": row[
                        "attacker"
                    ],
                    "victim": row[
                        "victim"
                    ],
                    "attacker_team": row[
                        "attacker_team"
                    ],
                    "victim_team": row[
                        "victim_team"
                    ],
                    "exact_state_before": row[
                        "exact_state_before"
                    ],
                    "exact_state_after": row[
                        "exact_state_after"
                    ],
                    "transition": row[
                        "transition"
                    ],
                    "phase": row[
                        "phase"
                    ],
                    "killer_team_won": row[
                        "killer_team_won"
                    ],
                    "is_first_kill": row[
                        "is_first_kill"
                    ],
                    "is_last_kill": row[
                        "is_last_kill"
                    ],
                    "own_alive_before": (
                        own_before
                    ),
                    "enemy_alive_before": (
                        enemy_before
                    ),
                    "own_alive_after": (
                        own_after
                    ),
                    "enemy_alive_after": (
                        enemy_after
                    ),
                    "probability_before": (
                        probability_before
                    ),
                    "probability_after": (
                        probability_after
                    ),
                    "raw_leverage": (
                        probability_after
                        - probability_before
                    ),
                    "win_probability_leverage": (
                        leverage
                    ),
                    "intercept": (
                        intercept
                    ),
                    "own_coefficient": (
                        own_coefficient
                    ),
                    "enemy_coefficient": (
                        enemy_coefficient
                    ),
                }
            )

    return pd.DataFrame(
        rows
    )


# ============================================================
# PERCENTUAIS
# ============================================================


def add_percentages(
    df: pd.DataFrame,
) -> pd.DataFrame:

    result = df.copy()

    result[
        "probability_before_pct"
    ] = (
        result[
            "probability_before"
        ]
        * 100.0
    )

    result[
        "probability_after_pct"
    ] = (
        result[
            "probability_after"
        ]
        * 100.0
    )

    result[
        "leverage_percentage_points"
    ] = (
        result[
            "win_probability_leverage"
        ]
        * 100.0
    )

    result[
        "leverage_percentile"
    ] = (
        result[
            "leverage_percentage_points"
        ]
        .rank(
            method="average",
            pct=True,
        )
        * 100.0
    )

    return result


# ============================================================
# RESUMO POR JOGADOR
# ============================================================


def create_player_summary(
    df: pd.DataFrame,
) -> pd.DataFrame:

    summary = (
        df.groupby(
            "attacker"
        )
        .agg(
            kills=(
                "attacker",
                "size",
            ),
            average_leverage_pp=(
                "leverage_percentage_points",
                "mean",
            ),
            median_leverage_pp=(
                "leverage_percentage_points",
                "median",
            ),
            total_leverage_pp=(
                "leverage_percentage_points",
                "sum",
            ),
            average_leverage_percentile=(
                "leverage_percentile",
                "mean",
            ),
            maximum_leverage_pp=(
                "leverage_percentage_points",
                "max",
            ),
            opening_kills=(
                "is_first_kill",
                "sum",
            ),
            closing_kills=(
                "is_last_kill",
                "sum",
            ),
            disadvantage_kills=(
                "transition",
                lambda x: (
                    x
                    == "DISADVANTAGE_PRESSURE"
                ).sum(),
            ),
            equalizer_kills=(
                "transition",
                lambda x: (
                    x
                    == "EQUALIZER"
                ).sum(),
            ),
            regain_kills=(
                "transition",
                lambda x: (
                    x
                    == "REGAIN_ADVANTAGE"
                ).sum(),
            ),
            extension_kills=(
                "transition",
                lambda x: (
                    x
                    == "EXTEND_ADVANTAGE"
                ).sum(),
            ),
        )
        .reset_index()
    )

    return summary.sort_values(
        "average_leverage_pp",
        ascending=False,
    )


# ============================================================
# RESUMO POR TRANSIÇÃO
# ============================================================


def create_transition_summary(
    df: pd.DataFrame,
) -> pd.DataFrame:

    summary = (
        df.groupby(
            "transition"
        )
        .agg(
            kills=(
                "attacker",
                "size",
            ),
            average_leverage_pp=(
                "leverage_percentage_points",
                "mean",
            ),
            median_leverage_pp=(
                "leverage_percentage_points",
                "median",
            ),
            minimum_leverage_pp=(
                "leverage_percentage_points",
                "min",
            ),
            maximum_leverage_pp=(
                "leverage_percentage_points",
                "max",
            ),
            average_before=(
                "probability_before_pct",
                "mean",
            ),
            average_after=(
                "probability_after_pct",
                "mean",
            ),
        )
        .reset_index()
    )

    return summary.sort_values(
        "average_leverage_pp",
        ascending=False,
    )


# ============================================================
# VALIDAÇÃO DA MATRIZ
# ============================================================


def validate_monotonicity(
    state_table: pd.DataFrame,
) -> None:

    matrix = np.zeros(
        (6, 6),
        dtype=float,
    )

    for _, row in state_table.iterrows():

        own_alive = int(
            row[
                "own_alive"
            ]
        )

        enemy_alive = int(
            row[
                "enemy_alive"
            ]
        )

        matrix[
            own_alive,
            enemy_alive,
        ] = float(
            row[
                "win_probability"
            ]
        )

    violations = []

    # Mais aliados -> probabilidade maior
    # ou igual.

    for own_alive in range(1, 5):

        for enemy_alive in range(1, 6):

            current = matrix[
                own_alive,
                enemy_alive,
            ]

            stronger = matrix[
                own_alive + 1,
                enemy_alive,
            ]

            if stronger < (
                current
                - 1e-12
            ):

                violations.append(
                    (
                        "ALLY",
                        f"{own_alive}v{enemy_alive}",
                        current,
                        stronger,
                    )
                )

    # Mais inimigos -> probabilidade menor
    # ou igual.

    for own_alive in range(1, 6):

        for enemy_alive in range(1, 5):

            current = matrix[
                own_alive,
                enemy_alive,
            ]

            stronger_enemy = matrix[
                own_alive,
                enemy_alive + 1,
            ]

            if stronger_enemy > (
                current
                + 1e-12
            ):

                violations.append(
                    (
                        "ENEMY",
                        f"{own_alive}v{enemy_alive}",
                        current,
                        stronger_enemy,
                    )
                )

    if violations:

        print()
        print(
            "VIOLAÇÕES:"
        )

        for violation in violations:

            print(
                violation
            )

        raise ValueError(
            "A matriz não é monotônica."
        )

    print(
        "OK: modelo de estado monotônico."
    )


# ============================================================
# IMPRESSÃO DA MATRIZ
# ============================================================


def print_state_matrix(
    state_table: pd.DataFrame,
) -> None:

    print()
    print("=" * 80)
    print(
        "MATRIZ DE PROBABILIDADE DOS ESTADOS"
    )
    print("=" * 80)
    print()

    matrix = (
        state_table
        .pivot(
            index="own_alive",
            columns="enemy_alive",
            values="win_probability",
        )
        .sort_index(
            ascending=False
        )
    )

    matrix = (
        matrix * 100.0
    )

    print(
        matrix.round(
            2
        ).to_string()
    )


# ============================================================
# TOP KILLS
# ============================================================


def print_top_kills(
    df: pd.DataFrame,
) -> None:

    print()
    print("=" * 80)
    print(
        "TOP KILLS POR WIN PROBABILITY LEVERAGE"
    )
    print("=" * 80)
    print()

    top = (
        df.sort_values(
            "leverage_percentage_points",
            ascending=False,
        )
    )

    columns = [
        "round",
        "sequence",
        "attacker",
        "victim",
        "exact_state_before",
        "exact_state_after",
        "transition",
        "phase",
        "probability_before_pct",
        "probability_after_pct",
        "leverage_percentage_points",
        "killer_team_won",
    ]

    print(
        top[
            columns
        ]
        .head(30)
        .to_string(
            index=False
        )
    )


# ============================================================
# RESUMO JOGADORES
# ============================================================


def print_player_summary(
    summary: pd.DataFrame,
) -> None:

    print()
    print("=" * 80)
    print(
        "RESUMO POR JOGADOR"
    )
    print("=" * 80)
    print()

    columns = [
        "attacker",
        "kills",
        "average_leverage_pp",
        "median_leverage_pp",
        "total_leverage_pp",
        "average_leverage_percentile",
        "maximum_leverage_pp",
        "opening_kills",
        "closing_kills",
        "disadvantage_kills",
        "equalizer_kills",
        "regain_kills",
        "extension_kills",
    ]

    print(
        summary[
            columns
        ].to_string(
            index=False
        )
    )


# ============================================================
# RESUMO TRANSIÇÕES
# ============================================================


def print_transition_summary(
    summary: pd.DataFrame,
) -> None:

    print()
    print("=" * 80)
    print(
        "RESUMO POR TRANSIÇÃO"
    )
    print("=" * 80)
    print()

    print(
        summary.to_string(
            index=False
        )
    )


# ============================================================
# VALIDAÇÃO FINAL
# ============================================================


def validate_result(
    source_df: pd.DataFrame,
    result_df: pd.DataFrame,
) -> None:

    print()
    print("=" * 80)
    print(
        "VALIDAÇÃO"
    )
    print("=" * 80)
    print()

    print(
        "Kills origem:",
        len(source_df),
    )

    print(
        "Kills modelo:",
        len(result_df),
    )

    print(
        "Rounds:",
        result_df[
            "round"
        ].nunique(),
    )

    print(
        "Jogadores:",
        result_df[
            "attacker"
        ].nunique(),
    )

    print()

    if len(source_df) == 0:

        raise ValueError(
            "A origem nao possui kills."
        )

    if len(result_df) != len(source_df):

        raise ValueError(
            "O modelo tem numero de kills diferente da origem."
        )

    if result_df[
        "probability_before"
    ].isna().any():

        raise ValueError(
            "Probabilidades antes ausentes."
        )

    if result_df[
        "probability_after"
    ].isna().any():

        raise ValueError(
            "Probabilidades depois ausentes."
        )

    if result_df[
        "leverage_percentage_points"
    ].isna().any():

        raise ValueError(
            "Leverages ausentes."
        )

    if (
        result_df[
            "probability_before"
        ]
        .lt(0)
        .any()
    ):

        raise ValueError(
            "Probabilidade antes inválida."
        )

    if (
        result_df[
            "probability_before"
        ]
        .gt(100)
        .any()
    ):

        raise ValueError(
            "Probabilidade antes inválida."
        )

    if (
        result_df[
            "probability_after"
        ]
        .lt(0)
        .any()
    ):

        raise ValueError(
            "Probabilidade depois inválida."
        )

    if (
        result_df[
            "probability_after"
        ]
        .gt(100)
        .any()
    ):

        raise ValueError(
            "Probabilidade depois inválida."
        )

    if (
        result_df[
            "leverage_percentage_points"
        ]
        .lt(0)
        .any()
    ):

        raise ValueError(
            "Existe leverage negativo."
        )

    print(
        "OK: 150 kills processadas."
    )

    print(
        "OK: probabilidades válidas."
    )

    print(
        "OK: leverage não negativo."
    )


# ============================================================
# MAIN
# ============================================================


def main() -> None:

    print()
    print("=" * 80)
    print(
        "LCP - WIN PROBABILITY KILL LEVERAGE V4"
    )
    print("=" * 80)
    print()

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"Arquivo não encontrado: "
            f"{INPUT_FILE}"
        )

    df = pd.read_csv(
        INPUT_FILE
    )

    required_columns = [
        "round",
        "sequence",
        "tick",
        "attacker",
        "victim",
        "attacker_team",
        "victim_team",
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
            "Colunas ausentes: "
            + ", ".join(missing)
        )

    print(
        "Kills carregadas:",
        len(df),
    )

    print(
        "Rounds:",
        df[
            "round"
        ].nunique(),
    )

    print(
        "Jogadores:",
        df[
            "attacker"
        ].nunique(),
    )

    # --------------------------------------------------------
    # Calcula leverage leave-one-round-out.
    # --------------------------------------------------------

    result = (
        calculate_leverage(
            df
        )
    )

    result = (
        add_percentages(
            result
        )
    )

    # --------------------------------------------------------
    # Modelo completo apenas para inspeção da matriz.
    # --------------------------------------------------------

    (
        intercept,
        own_coefficient,
        enemy_coefficient,
    ) = fit_monotonic_logistic(
        df
    )

    print()
    print("=" * 80)
    print(
        "PARÂMETROS DO MODELO"
    )
    print("=" * 80)
    print()

    print(
        f"Intercepto: "
        f"{intercept:.6f}"
    )

    print(
        f"Coeficiente aliados: "
        f"{own_coefficient:.6f}"
    )

    print(
        f"Coeficiente inimigos: "
        f"{enemy_coefficient:.6f}"
    )

    state_table = (
        build_state_table(
            intercept,
            own_coefficient,
            enemy_coefficient,
        )
    )

    validate_monotonicity(
        state_table
    )

    validate_result(
        source_df=df,
        result_df=result,
    )

    player_summary = (
        create_player_summary(
            result
        )
    )

    transition_summary = (
        create_transition_summary(
            result
        )
    )

    print_state_matrix(
        state_table
    )

    print_top_kills(
        result
    )

    print_player_summary(
        player_summary
    )

    print_transition_summary(
        transition_summary
    )

    # ========================================================
    # EXPORTAÇÕES
    # ========================================================

    result.to_csv(
        OUTPUT_EVENTS,
        index=False,
        encoding="utf-8-sig",
    )

    player_summary.to_csv(
        OUTPUT_PLAYERS,
        index=False,
        encoding="utf-8-sig",
    )

    state_table.to_csv(
        OUTPUT_STATES,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print("=" * 80)
    print(
        "ARQUIVOS GERADOS"
    )
    print("=" * 80)
    print()

    print(
        OUTPUT_EVENTS.name
    )

    print(
        OUTPUT_PLAYERS.name
    )

    print(
        OUTPUT_STATES.name
    )

    print()
    print("=" * 80)
    print(
        "WIN PROBABILITY LEVERAGE V4 CONCLUÍDO"
    )
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()