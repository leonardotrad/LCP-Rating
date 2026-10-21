import os
import pandas as pd
from demoparser2 import DemoParser

from round_classifier import classify_rounds


def _find_demo():
    from pathlib import Path as _P
    demos = sorted(_P("demos").glob("*.dem"))
    if not demos:
        raise FileNotFoundError("Nenhum arquivo .dem encontrado na pasta demos.")
    if len(demos) > 1:
        raise RuntimeError(
            "Ha mais de uma demo na pasta demos. Deixe apenas uma por vez."
        )
    return str(demos[0])


DEMO_PATH = _find_demo()

TICKRATE = 64.0


def clean_name(value):
    if pd.isna(value):
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def read_event(parser, event_name, fields):
    return parser.parse_event(
        event_name=event_name,
        player=fields,
    )


def team_number_to_name(team_number):

    if pd.isna(team_number):
        return None

    try:
        team_number = int(team_number)
    except (ValueError, TypeError):
        return None

    if team_number == 2:
        return "TERRORIST"

    if team_number == 3:
        return "CT"

    return None


def build_team_lookup(parser, death_ticks):

    unique_ticks = sorted(
        set(
            int(tick)
            for tick in death_ticks
            if not pd.isna(tick)
        )
    )

    if not unique_ticks:
        return {}

    print()
    print(
        "Lendo times dos jogadores nos ticks das mortes..."
    )

    ticks_df = parser.parse_ticks(
        [
            "team_num",
            "team_name",
        ],
        ticks=unique_ticks,
    )

    ticks_df = pd.DataFrame(
        ticks_df
    )

    print(
        "Snapshots de jogadores encontrados: "
        f"{len(ticks_df)}"
    )

    if ticks_df.empty:
        raise RuntimeError(
            "Não foi possível obter os times "
            "dos jogadores."
        )

    if "name" in ticks_df.columns:
        name_column = "name"

    elif "player_name" in ticks_df.columns:
        name_column = "player_name"

    else:
        raise KeyError(
            "Coluna de nome do jogador não encontrada.\n"
            f"Colunas: {list(ticks_df.columns)}"
        )

    if "tick" not in ticks_df.columns:
        raise KeyError(
            "Coluna 'tick' não encontrada."
        )

    if "team_num" not in ticks_df.columns:
        raise KeyError(
            "Coluna 'team_num' não encontrada."
        )

    lookup = {}

    for _, row in ticks_df.iterrows():

        player_name = clean_name(
            row[name_column]
        )

        tick = row["tick"]

        team = team_number_to_name(
            row["team_num"]
        )

        if player_name is None:
            continue

        if pd.isna(tick):
            continue

        lookup[
            (
                int(tick),
                player_name,
            )
        ] = team

    return lookup


def get_player_team(
    lookup,
    tick,
    player_name,
):
    player_name = clean_name(
        player_name
    )

    if player_name is None:
        return None

    if pd.isna(tick):
        return None

    tick = int(tick)

    team = lookup.get(
        (
            tick,
            player_name,
        )
    )

    if team is not None:
        return team

    for offset in range(1, 6):

        for candidate_tick in [
            tick - offset,
            tick + offset,
        ]:

            team = lookup.get(
                (
                    candidate_tick,
                    player_name,
                )
            )

            if team is not None:
                return team

    return None


def assign_deaths_to_rounds(
    classified_rounds,
    deaths,
    team_lookup,
):

    official_types = {
        "PISTOL",
        "NORMAL",
        "OVERTIME",
    }

    official_rounds = classified_rounds[
        classified_rounds[
            "round_type"
        ].isin(official_types)
    ].copy()

    official_rounds = (
        official_rounds
        .sort_values(
            "tick_start"
        )
        .reset_index(
            drop=True
        )
    )

    official_rounds[
        "round_index"
    ] = range(
        len(official_rounds)
    )

    deaths = deaths.copy()

    deaths["tick"] = pd.to_numeric(
        deaths["tick"],
        errors="coerce",
    )

    official_rounds[
        "tick_start"
    ] = pd.to_numeric(
        official_rounds[
            "tick_start"
        ],
        errors="coerce",
    )

    official_rounds[
        "tick_end"
    ] = pd.to_numeric(
        official_rounds[
            "tick_end"
        ],
        errors="coerce",
    )

    deaths = (
        deaths
        .dropna(
            subset=["tick"]
        )
        .sort_values(
            "tick"
        )
        .reset_index(
            drop=True
        )
    )

    assigned = []

    for _, round_row in official_rounds.iterrows():

        round_index = int(
            round_row[
                "round_index"
            ]
        )

        tick_start = round_row[
            "tick_start"
        ]

        tick_end = round_row[
            "tick_end"
        ]

        if pd.isna(tick_start):
            continue

        if pd.isna(tick_end):

            round_deaths = deaths[
                deaths["tick"] >= tick_start
            ].copy()

        else:

            round_deaths = deaths[
                (
                    deaths["tick"]
                    >=
                    tick_start
                )
                &
                (
                    deaths["tick"]
                    <=
                    tick_end
                )
            ].copy()

        for _, death in round_deaths.iterrows():

            tick = death["tick"]

            attacker_name = clean_name(
                death.get(
                    "attacker_name"
                )
            )

            victim_name = clean_name(
                death.get(
                    "user_name"
                )
            )

            attacker_team = get_player_team(
                team_lookup,
                tick,
                attacker_name,
            )

            victim_team = get_player_team(
                team_lookup,
                tick,
                victim_name,
            )

            assigned.append(
                {
                    "round_index": round_index,
                    "round_number": round_index,
                    "half": round_row.get(
                        "half",
                        None,
                    ),
                    "round_type": round_row[
                        "round_type"
                    ],
                    "tick": tick,
                    "attacker_name": attacker_name,
                    "victim_name": victim_name,
                    "attacker_team": attacker_team,
                    "victim_team": victim_team,
                    "weapon": clean_name(
                        death.get(
                            "weapon"
                        )
                    ),
                }
            )

    return (
        official_rounds,
        pd.DataFrame(
            assigned
        ),
    )


def calculate_entry_rounds(
    round_deaths,
):

    if round_deaths.empty:

        return pd.DataFrame(
            columns=[
                "round_index",
                "entry_killer",
                "entry_victim",
                "entry_tick",
            ]
        )

    first = (
        round_deaths
        .sort_values(
            [
                "round_index",
                "tick",
            ]
        )
        .groupby(
            "round_index",
            as_index=False,
            sort=False,
        )
        .first()
    )

    first = first.rename(
        columns={
            "attacker_name": "entry_killer",
            "victim_name": "entry_victim",
            "tick": "entry_tick",
        }
    )

    return first[
        [
            "round_index",
            "entry_killer",
            "entry_victim",
            "entry_tick",
        ]
    ]


def find_trades_for_window(
    round_deaths,
    entry_rounds,
    trade_window_seconds,
):
    """
    Calcula trades.

    Regra:

    Jogador A morre para jogador B.

    Dentro da janela de trade, um companheiro de A
    precisa matar EXATAMENTE o jogador B.

    Portanto:

        morte:      B -> A
        trade kill: C -> B

    Isso é diferente de simplesmente matar qualquer
    jogador da equipe adversária.
    """

    if round_deaths.empty:
        return pd.DataFrame()

    entry_map = {}

    for _, row in entry_rounds.iterrows():

        entry_map[
            int(
                row[
                    "round_index"
                ]
            )
        ] = {
            "entry_killer": clean_name(
                row[
                    "entry_killer"
                ]
            ),
            "entry_victim": clean_name(
                row[
                    "entry_victim"
                ]
            ),
        }

    trades = []

    for round_index, deaths_round in (
        round_deaths
        .groupby(
            "round_index"
        )
    ):

        deaths_round = (
            deaths_round
            .sort_values(
                "tick"
            )
            .reset_index(
                drop=True
            )
        )

        used_trade_kills = set()

        for death_index, death in (
            deaths_round.iterrows()
        ):

            victim = clean_name(
                death[
                    "victim_name"
                ]
            )

            killer = clean_name(
                death[
                    "attacker_name"
                ]
            )

            victim_team = clean_name(
                death[
                    "victim_team"
                ]
            )

            killer_team = clean_name(
                death[
                    "attacker_team"
                ]
            )

            death_tick = death[
                "tick"
            ]

            if victim is None:
                continue

            if killer is None:
                continue

            if victim_team is None:
                continue

            if killer_team is None:
                continue

            # Não há trade se for team kill.
            if victim_team == killer_team:
                continue

            # Procurar próxima kill.
            for candidate_index in range(
                death_index + 1,
                len(deaths_round),
            ):

                candidate = (
                    deaths_round.iloc[
                        candidate_index
                    ]
                )

                candidate_killer = clean_name(
                    candidate[
                        "attacker_name"
                    ]
                )

                candidate_victim = clean_name(
                    candidate[
                        "victim_name"
                    ]
                )

                candidate_attacker_team = (
                    clean_name(
                        candidate[
                            "attacker_team"
                        ]
                    )
                )

                candidate_victim_team = (
                    clean_name(
                        candidate[
                            "victim_team"
                        ]
                    )
                )

                candidate_tick = candidate[
                    "tick"
                ]

                if candidate_killer is None:
                    continue

                if candidate_victim is None:
                    continue

                if (
                    candidate_index
                    in used_trade_kills
                ):
                    continue

                delta_ticks = (
                    candidate_tick
                    -
                    death_tick
                )

                delta_seconds = (
                    delta_ticks
                    /
                    TICKRATE
                )

                if (
                    delta_seconds
                    >
                    trade_window_seconds
                ):
                    break

                # ----------------------------------------------------
                # REGRA 1:
                # Quem faz o trade precisa ser companheiro
                # do jogador que acabou de morrer.
                # ----------------------------------------------------

                if (
                    candidate_attacker_team
                    !=
                    victim_team
                ):
                    continue

                # ----------------------------------------------------
                # REGRA 2:
                # A vítima do trade precisa pertencer
                # ao time do jogador que fez a primeira kill.
                # ----------------------------------------------------

                if (
                    candidate_victim_team
                    !=
                    killer_team
                ):
                    continue

                # ----------------------------------------------------
                # REGRA PRINCIPAL:
                # O jogador morto no trade precisa ser EXATAMENTE
                # o jogador que matou a vítima anteriormente.
                # ----------------------------------------------------

                if (
                    candidate_victim
                    !=
                    killer
                ):
                    continue

                # Não permitir o mesmo jogador.
                if candidate_killer == killer:
                    continue

                # ----------------------------------------------------
                # Trade encontrado.
                # ----------------------------------------------------

                used_trade_kills.add(
                    candidate_index
                )

                entry = entry_map.get(
                    int(
                        round_index
                    )
                )

                entry_victim = None
                entry_killer = None

                if entry is not None:

                    entry_victim = clean_name(
                        entry[
                            "entry_victim"
                        ]
                    )

                    entry_killer = clean_name(
                        entry[
                            "entry_killer"
                        ]
                    )

                # A morte original foi Entry Death?
                traded_entry_kill = (
                    victim
                    ==
                    entry_victim
                )

                # O jogador que morreu era Entry Killer?
                traded_entry_death = (
                    killer
                    ==
                    entry_killer
                )

                trades.append(
                    {
                        "round_index": int(
                            round_index
                        ),
                        "death_tick": death_tick,
                        "trade_tick": candidate_tick,
                        "trade_delay_seconds": round(
                            delta_seconds,
                            3,
                        ),
                        "player_traded": victim,
                        "enemy_killer": killer,
                        "trade_killer": candidate_killer,
                        "trade_victim": candidate_victim,
                        "traded_entry_kill": (
                            traded_entry_kill
                        ),
                        "traded_entry_death": (
                            traded_entry_death
                        ),
                    }
                )

                break

    return pd.DataFrame(
        trades
    )


def print_window_analysis(
    round_deaths,
    entry_rounds,
):

    windows = [
        0.5,
        1.0,
        1.5,
        2.0,
        2.5,
        3.0,
        3.5,
        4.0,
        4.5,
        5.0,
    ]

    print()
    print("=" * 90)
    print(
        "ANÁLISE DA JANELA DE TRADE"
    )
    print("=" * 90)

    print()

    print(
        f"{'JANELA':<12}"
        f"{'TRADES':<12}"
        f"{'ENTRY KILLS':<15}"
        f"{'ENTRY DEATHS':<15}"
    )

    print(
        "-" * 54
    )

    analysis_results = []

    for window in windows:

        trades = find_trades_for_window(
            round_deaths,
            entry_rounds,
            window,
        )

        if trades.empty:

            trade_count = 0
            entry_kills = 0
            entry_deaths = 0

        else:

            trade_count = len(
                trades
            )

            entry_kills = int(
                trades[
                    "traded_entry_kill"
                ].sum()
            )

            entry_deaths = int(
                trades[
                    "traded_entry_death"
                ].sum()
            )

        analysis_results.append(
            {
                "window": window,
                "trades": trade_count,
                "entry_kills": entry_kills,
                "entry_deaths": entry_deaths,
            }
        )

        print(
            f"{window:<12.1f}"
            f"{trade_count:<12}"
            f"{entry_kills:<15}"
            f"{entry_deaths:<15}"
        )

    print()
    print(
        "REFERÊNCIA DO SCOREBOARD:"
    )

    print(
        "24 Trade Kills / "
        "24 Deaths Traded / "
        "2 Traded Entry Kills / "
        "2 Traded Entry Deaths"
    )

    exact_matches = [
        row
        for row in analysis_results
        if (
            row["trades"] == 24
            and row["entry_kills"] == 2
            and row["entry_deaths"] == 2
        )
    ]

    print()

    if exact_matches:

        print(
            "CORRESPONDÊNCIA EXATA ENCONTRADA:"
        )

        for row in exact_matches:

            print(
                f"Janela: "
                f"{row['window']:.1f}s"
            )

    else:

        trade_only_matches = [
            row
            for row in analysis_results
            if row["trades"] == 24
        ]

        if trade_only_matches:

            print(
                "Uma ou mais janelas produziram "
                "24 trades:"
            )

            for row in trade_only_matches:

                print(
                    f"{row['window']:.1f}s "
                    f"-> "
                    f"{row['trades']} trades / "
                    f"{row['entry_kills']} entry kills / "
                    f"{row['entry_deaths']} entry deaths"
                )

        else:

            print(
                "Nenhuma janela testada "
                "produziu exatamente 24 trades."
            )

    return analysis_results


def main():

    print("=" * 90)
    print("LCP RATING - TRADE ANALYSIS")
    print("=" * 90)

    print()
    print("Demo:")
    print(DEMO_PATH)

    if not os.path.exists(
        DEMO_PATH
    ):
        raise FileNotFoundError(
            f"Demo não encontrada: "
            f"{DEMO_PATH}"
        )

    print()
    print("Abrindo demo...")

    parser = DemoParser(
        DEMO_PATH
    )

    # ================================================================
    # ROUNDS
    # ================================================================

    print()
    print(
        "Lendo rounds..."
    )

    rounds = pd.DataFrame(
        read_event(
            parser,
            "round_poststart",
            [
                "tick",
                "total_rounds_played",
                "is_warmup_period",
            ],
        )
    )

    print(
        f"Eventos de round: "
        f"{len(rounds)}"
    )

    # ================================================================
    # DEATHS
    # ================================================================

    print()
    print(
        "Lendo player_death..."
    )

    deaths = pd.DataFrame(
        read_event(
            parser,
            "player_death",
            [
                "tick",
                "attacker_name",
                "user_name",
                "weapon",
            ],
        )
    )

    print(
        f"Eventos de morte: "
        f"{len(deaths)}"
    )

    # ================================================================
    # HALF
    # ================================================================

    print()
    print(
        "Lendo round_announce_last_round_half..."
    )

    half_events = pd.DataFrame(
        read_event(
            parser,
            "round_announce_last_round_half",
            [
                "tick",
            ],
        )
    )

    print(
        f"Eventos de troca de half: "
        f"{len(half_events)}"
    )

    # ================================================================
    # CLASSIFICAÇÃO
    # ================================================================

    print()
    print(
        "Classificando rounds..."
    )

    classified_rounds = pd.DataFrame(
        classify_rounds(
            rounds,
            deaths,
            half_events,
        )
    )

    # ================================================================
    # TIMES
    # ================================================================

    team_lookup = build_team_lookup(
        parser,
        deaths[
            "tick"
        ].tolist(),
    )

    print(
        f"Associações tick/jogador/time: "
        f"{len(team_lookup)}"
    )

    # ================================================================
    # ASSOCIAR MORTES AOS ROUNDS
    # ================================================================

    print()
    print(
        "Associando mortes aos rounds oficiais..."
    )

    official_rounds, round_deaths = (
        assign_deaths_to_rounds(
            classified_rounds,
            deaths,
            team_lookup,
        )
    )

    print(
        f"Rounds oficiais: "
        f"{len(official_rounds)}"
    )

    print(
        f"Mortes associadas: "
        f"{len(round_deaths)}"
    )

    # ================================================================
    # VALIDAR TIMES
    # ================================================================

    known_attacker_teams = int(
        round_deaths[
            "attacker_team"
        ]
        .notna()
        .sum()
    )

    known_victim_teams = int(
        round_deaths[
            "victim_team"
        ]
        .notna()
        .sum()
    )

    print()
    print(
        "Times identificados:"
    )

    print(
        f"Atacantes com time: "
        f"{known_attacker_teams}"
    )

    print(
        f"Vítimas com time: "
        f"{known_victim_teams}"
    )

    # ================================================================
    # ENTRY
    # ================================================================

    print()
    print(
        "Calculando Entry por round..."
    )

    entry_rounds = calculate_entry_rounds(
        round_deaths
    )

    print(
        f"Rounds com Entry: "
        f"{len(entry_rounds)}"
    )

    # ================================================================
    # ANÁLISE DE JANELAS
    # ================================================================

    print_window_analysis(
        round_deaths,
        entry_rounds,
    )

    # ================================================================
    # DEBUG
    # ================================================================

    round_deaths.to_csv(
        "trade_debug_deaths.csv",
        index=False,
    )

    entry_rounds.to_csv(
        "trade_entry_rounds.csv",
        index=False,
    )

    print()
    print("=" * 90)
    print("ARQUIVOS GERADOS")
    print("=" * 90)

    print(
        "trade_debug_deaths.csv"
    )

    print(
        "trade_entry_rounds.csv"
    )

    print()
    print(
        "Análise de Trade concluída."
    )


if __name__ == "__main__":
    main()