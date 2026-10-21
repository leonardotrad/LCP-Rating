from pathlib import Path

import pandas as pd
from demoparser2 import DemoParser

from round_classifier import classify_rounds


# ============================================================
# CONFIGURAÇÃO
# ============================================================

DEMO_FOLDER = Path("demos")

OFFICIAL_ROUND_TYPES = {
    "PISTOL",
    "NORMAL",
    "OVERTIME",
}


# ============================================================
# LOCALIZAR DEMO
# ============================================================

def find_demo():

    demo_files = list(
        DEMO_FOLDER.glob("*.dem")
    )

    if not demo_files:
        raise FileNotFoundError(
            "Nenhum arquivo .dem encontrado na pasta demos."
        )

    if len(demo_files) > 1:

        print("Foram encontradas várias demos:")

        for demo in demo_files:
            print(f" - {demo}")

        raise RuntimeError(
            "Deixe apenas uma demo na pasta demos "
            "enquanto estamos desenvolvendo o parser."
        )

    return demo_files[0]


# ============================================================
# PEGAR EVENTOS ENTRE TICKS
# ============================================================

def get_events_between_ticks(
    events,
    tick_start,
    tick_end=None,
):

    if events.empty:
        return events.copy()

    # Último intervalo da demo
    if tick_end is None or pd.isna(tick_end):

        return events[
            events["tick"] >= tick_start
        ].copy()

    return events[
        (events["tick"] >= tick_start)
        & (events["tick"] < tick_end)
    ].copy()


# ============================================================
# EXTRAIR KILLS OFICIAIS
# ============================================================

def extract_official_kills(
    deaths,
    round_classification,
):

    records = []

    for _, round_row in (
        round_classification.iterrows()
    ):

        round_type = (
            round_row["round_type"]
        )

        # Somente rounds oficiais
        if round_type not in OFFICIAL_ROUND_TYPES:
            continue

        tick_start = int(
            round_row["tick_start"]
        )

        tick_end = (
            round_row["tick_end"]
        )

        round_deaths = (
            get_events_between_ticks(
                deaths,
                tick_start,
                tick_end,
            )
        )

        if round_deaths.empty:
            continue

        for _, death in (
            round_deaths.iterrows()
        ):

            records.append({

                # ------------------------------------------------
                # ROUND
                # ------------------------------------------------

                "round_event_index":
                    round_row[
                        "event_index"
                    ],

                "round_number":
                    round_row[
                        "total_rounds_played"
                    ],

                "half":
                    round_row[
                        "half"
                    ],

                "round_type":
                    round_type,

                "round_tick_start":
                    round_row[
                        "tick_start"
                    ],

                "round_tick_end":
                    round_row[
                        "tick_end"
                    ],

                # ------------------------------------------------
                # EVENTO
                # ------------------------------------------------

                "tick":
                    death.get("tick"),

                # ------------------------------------------------
                # JOGADORES
                # ------------------------------------------------

                "attacker_name":
                    death.get(
                        "attacker_name"
                    ),

                "attacker_steamid":
                    death.get(
                        "attacker_steamid"
                    ),

                "victim_name":
                    death.get(
                        "user_name"
                    ),

                "victim_steamid":
                    death.get(
                        "user_steamid"
                    ),

                # time de cada um (2 = TR, 3 = CT), para separar kill em
                # companheiro e suicidio, que nao contam como kill
                "attacker_team":
                    death.get(
                        "attacker_team_num"
                    ),

                "victim_team":
                    death.get(
                        "user_team_num"
                    ),

                "assister_name":
                    death.get(
                        "assister_name"
                    ),

                "assister_steamid":
                    death.get(
                        "assister_steamid"
                    ),

                # ------------------------------------------------
                # ARMA
                # ------------------------------------------------

                "weapon":
                    death.get(
                        "weapon"
                    ),

                "headshot":
                    death.get(
                        "headshot"
                    ),

                # ------------------------------------------------
                # CONTEXTO
                # ------------------------------------------------

                "dmg_health":
                    death.get(
                        "dmg_health"
                    ),

                "dmg_armor":
                    death.get(
                        "dmg_armor"
                    ),

                "hitgroup":
                    death.get(
                        "hitgroup"
                    ),

                "distance":
                    death.get(
                        "distance"
                    ),

                "thrusmoke":
                    death.get(
                        "thrusmoke"
                    ),

                "attackerblind":
                    death.get(
                        "attackerblind"
                    ),

                "attackerinair":
                    death.get(
                        "attackerinair"
                    ),

                "noscope":
                    death.get(
                        "noscope"
                    ),

                "revenge":
                    death.get(
                        "revenge"
                    ),

                "dominated":
                    death.get(
                        "dominated"
                    ),

                "penetrated":
                    death.get(
                        "penetrated"
                    ),
            })

    if not records:
        return pd.DataFrame()

    return pd.DataFrame(
        records
    )


# ============================================================
# EXTRAIR DAMAGE OFICIAL
# ============================================================

def extract_official_damage(
    damage_events,
    round_classification,
):

    records = []

    for _, round_row in (
        round_classification.iterrows()
    ):

        round_type = (
            round_row["round_type"]
        )

        # Somente rounds oficiais
        if round_type not in OFFICIAL_ROUND_TYPES:
            continue

        tick_start = int(
            round_row["tick_start"]
        )

        tick_end = (
            round_row["tick_end"]
        )

        round_damage = (
            get_events_between_ticks(
                damage_events,
                tick_start,
                tick_end,
            )
        )

        if round_damage.empty:
            continue

        for _, event in (
            round_damage.iterrows()
        ):

            records.append({

                # ------------------------------------------------
                # ROUND
                # ------------------------------------------------

                "round_event_index":
                    round_row[
                        "event_index"
                    ],

                "round_number":
                    round_row[
                        "total_rounds_played"
                    ],

                "half":
                    round_row[
                        "half"
                    ],

                "round_type":
                    round_type,

                "round_tick_start":
                    round_row[
                        "tick_start"
                    ],

                "round_tick_end":
                    round_row[
                        "tick_end"
                    ],

                # ------------------------------------------------
                # EVENTO
                # ------------------------------------------------

                "tick":
                    event.get(
                        "tick"
                    ),

                # ------------------------------------------------
                # ATACANTE
                # ------------------------------------------------

                "attacker_name":
                    event.get(
                        "attacker_name"
                    ),

                "attacker_steamid":
                    event.get(
                        "attacker_steamid"
                    ),

                # ------------------------------------------------
                # VÍTIMA
                # ------------------------------------------------

                "victim_name":
                    event.get(
                        "user_name"
                    ),

                "victim_steamid":
                    event.get(
                        "user_steamid"
                    ),

                # ------------------------------------------------
                # ARMA / FONTE
                # ------------------------------------------------

                "weapon":
                    event.get(
                        "weapon"
                    ),

                # ------------------------------------------------
                # DAMAGE
                # ------------------------------------------------

                "dmg_health":
                    event.get(
                        "dmg_health"
                    ),

                "dmg_armor":
                    event.get(
                        "dmg_armor"
                    ),

                "health_after_hit":
                    event.get(
                        "health"
                    ),

                # ------------------------------------------------
                # HIT
                # ------------------------------------------------

                "hitgroup":
                    event.get(
                        "hitgroup"
                    ),
            })

    if not records:
        return pd.DataFrame()

    return pd.DataFrame(
        records
    )


# ============================================================
# CRIAR RESUMO GENERAL
# ============================================================

def create_general_summary(
    official_kills,
    official_damage,
    total_official_rounds,
):

    # --------------------------------------------------------
    # JOGADORES
    # --------------------------------------------------------

    players = set()

    for dataframe, columns in [
        (
            official_kills,
            [
                "attacker_name",
                "victim_name",
                "assister_name",
            ],
        ),
        (
            official_damage,
            [
                "attacker_name",
                "victim_name",
            ],
        ),
    ]:

        if dataframe.empty:
            continue

        for column in columns:

            if column not in dataframe.columns:
                continue

            values = (
                dataframe[column]
                .dropna()
                .astype(str)
            )

            players.update(
                value
                for value in values
                if value not in {
                    "",
                    "nan",
                    "NaN",
                }
            )


    if not players:
        return pd.DataFrame()


    # --------------------------------------------------------
    # CALCULAR POR JOGADOR
    # --------------------------------------------------------

    result = []

    for player in sorted(players):

        # ----------------------------------------------------
        # KILLS
        # ----------------------------------------------------

        if official_kills.empty:

            kills = 0

        else:

            kills = (
                official_kills[
                    "attacker_name"
                ]
                .eq(player)
                .sum()
            )


        # ----------------------------------------------------
        # DEATHS
        # ----------------------------------------------------

        if official_kills.empty:

            deaths = 0

        else:

            deaths = (
                official_kills[
                    "victim_name"
                ]
                .eq(player)
                .sum()
            )


        # ----------------------------------------------------
        # ASSISTS
        # ----------------------------------------------------

        if official_kills.empty:

            assists = 0

        else:

            assists = (
                official_kills[
                    "assister_name"
                ]
                .eq(player)
                .sum()
            )


        # ----------------------------------------------------
        # HEADSHOTS
        # ----------------------------------------------------

        if official_kills.empty:

            headshots = 0

        else:

            headshots = (
                (
                    official_kills[
                        "attacker_name"
                    ].eq(player)
                    &
                    official_kills[
                        "headshot"
                    ].eq(True)
                )
                .sum()
            )


        # ----------------------------------------------------
        # DAMAGE
        # ----------------------------------------------------

        if official_damage.empty:

            damage = 0
            armor_damage = 0
            hit_events = 0

        else:

            player_damage = (
                official_damage[
                    official_damage[
                        "attacker_name"
                    ].eq(player)
                ]
                .copy()
            )

            damage = (
                pd.to_numeric(
                    player_damage[
                        "dmg_health"
                    ],
                    errors="coerce",
                )
                .fillna(0)
                .sum()
            )

            armor_damage = (
                pd.to_numeric(
                    player_damage[
                        "dmg_armor"
                    ],
                    errors="coerce",
                )
                .fillna(0)
                .sum()
            )

            hit_events = len(
                player_damage
            )


        # ----------------------------------------------------
        # HS%
        # ----------------------------------------------------

        if kills > 0:

            hs_percentage = (
                headshots / kills
            ) * 100

        else:

            hs_percentage = 0


        # ----------------------------------------------------
        # K/D
        # ----------------------------------------------------

        if deaths > 0:

            kd = (
                kills / deaths
            )

        else:

            kd = 0


        # ----------------------------------------------------
        # K/R
        # ----------------------------------------------------

        if total_official_rounds > 0:

            kr = (
                kills
                /
                total_official_rounds
            )

        else:

            kr = 0


        # ----------------------------------------------------
        # ADR
        # ----------------------------------------------------

        if total_official_rounds > 0:

            adr = (
                damage
                /
                total_official_rounds
            )

        else:

            adr = 0


        result.append({

            "player":
                player,

            "kills":
                int(kills),

            "deaths":
                int(deaths),

            "assists":
                int(assists),

            "headshots":
                int(headshots),

            "hs_percentage":
                round(
                    hs_percentage,
                    1,
                ),

            "kd":
                round(
                    kd,
                    2,
                ),

            "kr":
                round(
                    kr,
                    2,
                ),

            "damage":
                round(
                    float(damage),
                    1,
                ),

            "armor_damage":
                round(
                    float(armor_damage),
                    1,
                ),

            "adr_reconstructed":
                round(
                    float(adr),
                    1,
                ),

            "damage_hit_events":
                int(hit_events),
        })


    # --------------------------------------------------------
    # ORDENAR
    # --------------------------------------------------------

    return (
        pd.DataFrame(result)
        .sort_values(
            by=[
                "kills",
                "adr_reconstructed",
            ],
            ascending=[
                False,
                False,
            ],
        )
        .reset_index(drop=True)
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 90)
    print("LCP RATING - PARSER CENTRAL")
    print("=" * 90)


    # ========================================================
    # DEMO
    # ========================================================

    demo_path = find_demo()

    print("\nDemo:")
    print(demo_path)


    # ========================================================
    # ABRIR DEMO
    # ========================================================

    print("\nAbrindo demo...")

    parser = DemoParser(
        str(demo_path)
    )


    # ========================================================
    # ROUNDS
    # ========================================================

    print("\nLendo rounds...")

    round_events = parser.parse_event(
        "round_poststart",
        other=[
            "is_warmup_period",
            "total_rounds_played",
        ],
    )

    if not isinstance(round_events, pd.DataFrame) or len(round_events) == 0:
        round_events = pd.DataFrame(
            columns=["tick", "is_warmup_period", "total_rounds_played"]
        )
    else:
        round_events = (
            round_events
            .sort_values("tick")
            .reset_index(drop=True)
        )

    print(
        "Eventos de round:",
        len(round_events),
    )


    # ========================================================
    # KILLS
    # ========================================================

    print("\nLendo player_death...")

    deaths = parser.parse_event(
        "player_death",
        player=["team_num"],
        other=[
            "is_warmup_period",
            "total_rounds_played",
        ],
    )

    deaths = (
        deaths
        .sort_values("tick")
        .reset_index(drop=True)
    )

    print(
        "Eventos de morte:",
        len(deaths),
    )


    # ========================================================
    # HALF
    # ========================================================

    print(
        "\nLendo round_announce_last_round_half..."
    )

    half_events = parser.parse_event(
        "round_announce_last_round_half",
        other=[
            "is_warmup_period",
            "total_rounds_played",
        ],
    )

    half_events = (
        half_events
        .sort_values("tick")
        .reset_index(drop=True)
    )

    print(
        "Eventos de troca de half:",
        len(half_events),
    )


    # ========================================================
    # CLASSIFICAR ROUNDS
    # ========================================================

    print(
        "\nClassificando rounds..."
    )

    round_classification = classify_rounds(
        round_events,
        deaths,
        half_events,
    )


    # ========================================================
    # RESUMO DOS ROUNDS
    # ========================================================

    print("\n")
    print("=" * 90)
    print("RESUMO DOS ROUNDS")
    print("=" * 90)

    print(
        round_classification[
            "round_type"
        ]
        .value_counts()
        .to_string()
    )


    # ========================================================
    # ROUNDS OFICIAIS
    # ========================================================

    official_rounds_df = (
        round_classification[
            round_classification[
                "round_type"
            ].isin(
                OFFICIAL_ROUND_TYPES
            )
        ]
        .copy()
    )

    total_official_rounds = len(
        official_rounds_df
    )

    print(
        "\nRounds oficiais:",
        total_official_rounds,
    )


    # ========================================================
    # KILLS OFICIAIS
    # ========================================================

    print(
        "\nExtraindo kills oficiais..."
    )

    official_kills = (
        extract_official_kills(
            deaths,
            round_classification,
        )
    )

    print(
        "Kills oficiais:",
        len(official_kills),
    )


    # ========================================================
    # DAMAGE
    # ========================================================

    print(
        "\nLendo player_hurt..."
    )

    hurt = parser.parse_event(
        "player_hurt",
        other=[
            "is_warmup_period",
            "total_rounds_played",
        ],
    )

    hurt = (
        hurt
        .sort_values("tick")
        .reset_index(drop=True)
    )

    print(
        "Eventos player_hurt:",
        len(hurt),
    )


    # ========================================================
    # DAMAGE OFICIAL
    # ========================================================

    print(
        "\nExtraindo damage oficial..."
    )

    official_damage = (
        extract_official_damage(
            hurt,
            round_classification,
        )
    )

    print(
        "Eventos de dano oficiais:",
        len(official_damage),
    )


    # ========================================================
    # GENERAL
    # ========================================================

    general = create_general_summary(
        official_kills,
        official_damage,
        total_official_rounds,
    )


    print("\n")
    print("=" * 90)
    print("GENERAL + DAMAGE + ADR")
    print("=" * 90)

    if general.empty:

        print(
            "Nenhum jogador encontrado."
        )

    else:

        print(
            general.to_string(
                index=False
            )
        )


    # ========================================================
    # DAMAGE POR ROUND
    # ========================================================

    if not official_damage.empty:

        damage_copy = (
            official_damage.copy()
        )

        damage_copy[
            "dmg_health"
        ] = pd.to_numeric(
            damage_copy[
                "dmg_health"
            ],
            errors="coerce",
        ).fillna(0)


        damage_per_round = (
            damage_copy
            .groupby(
                [
                    "half",
                    "round_number",
                    "round_type",
                ],
                dropna=False,
            )
            [
                "dmg_health"
            ]
            .sum()
            .reset_index(
                name="damage"
            )
        )

        print("\n")
        print("=" * 90)
        print("DAMAGE POR ROUND")
        print("=" * 90)

        print(
            damage_per_round
            .to_string(index=False)
        )


    # ========================================================
    # DAMAGE POR ARMA
    # ========================================================

    if not official_damage.empty:

        weapon_damage = (
            official_damage.copy()
        )

        weapon_damage[
            "dmg_health"
        ] = pd.to_numeric(
            weapon_damage[
                "dmg_health"
            ],
            errors="coerce",
        ).fillna(0)

        weapon_summary = (
            weapon_damage
            .groupby(
                [
                    "attacker_name",
                    "weapon",
                ],
                dropna=False,
            )
            [
                "dmg_health"
            ]
            .sum()
            .reset_index(
                name="damage"
            )
            .sort_values(
                "damage",
                ascending=False,
            )
        )

        print("\n")
        print("=" * 90)
        print("DAMAGE POR JOGADOR E ARMA")
        print("=" * 90)

        print(
            weapon_summary
            .to_string(index=False)
        )

        weapon_summary.to_csv(
            "data_damage_by_weapon.csv",
            index=False,
            encoding="utf-8-sig",
        )


    # ========================================================
    # SALVAR ROUNDS
    # ========================================================

    rounds_output = Path(
        "data_rounds.csv"
    )

    round_classification.to_csv(
        rounds_output,
        index=False,
        encoding="utf-8-sig",
    )


    # ========================================================
    # SALVAR KILLS
    # ========================================================

    kills_output = Path(
        "data_kills.csv"
    )

    official_kills.to_csv(
        kills_output,
        index=False,
        encoding="utf-8-sig",
    )


    # ========================================================
    # SALVAR DAMAGE
    # ========================================================

    damage_output = Path(
        "data_damage.csv"
    )

    official_damage.to_csv(
        damage_output,
        index=False,
        encoding="utf-8-sig",
    )


    # ========================================================
    # SALVAR GENERAL
    # ========================================================

    general_output = Path(
        "data_general.csv"
    )

    general.to_csv(
        general_output,
        index=False,
        encoding="utf-8-sig",
    )


    # ========================================================
    # FINAL
    # ========================================================

    print("\n")
    print("=" * 90)
    print("ARQUIVOS GERADOS")
    print("=" * 90)

    print(
        rounds_output
    )

    print(
        kills_output
    )

    print(
        damage_output
    )

    print(
        general_output
    )

    if not official_damage.empty:
        print(
            "data_damage_by_weapon.csv"
        )

    print(
        "\nParser central executado com sucesso."
    )


# ============================================================
# EXECUTAR
# ============================================================

if __name__ == "__main__":
    main()