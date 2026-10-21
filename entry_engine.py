import pandas as pd


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


def read_event(parser, event_name, fields):
    return parser.parse_event(
        event_name=event_name,
        player=fields,
    )


def prepare_official_rounds(classified_rounds):
    official_types = {
        "PISTOL",
        "NORMAL",
        "OVERTIME",
    }

    official = classified_rounds[
        classified_rounds["round_type"].isin(
            official_types
        )
    ].copy()

    official = (
        official
        .sort_values("tick_start")
        .reset_index(drop=True)
    )

    official["round_index"] = range(
        len(official)
    )

    return official


def get_entry_events(
    parser,
    official_rounds,
):
    """
    Fonte única da verdade para Entry.

    Para cada round oficial:
    - pega todas as mortes do round;
    - ordena por tick;
    - a primeira morte é a First Kill;
    - o atacante recebe Entry Kill;
    - a vítima recebe Entry Death.

    Retorna:
        first_kills
    contendo uma linha por round oficial.
    """

    if official_rounds.empty:
        return pd.DataFrame()

    deaths = pd.DataFrame(
        read_event(
            parser,
            "player_death",
            [
                "tick",
                "attacker_name",
                "user_name",
                "assister_name",
                "weapon",
                "headshot",
                "team_num",
            ],
        )
    )

    if deaths.empty:
        return pd.DataFrame()

    deaths["tick"] = pd.to_numeric(
        deaths["tick"],
        errors="coerce",
    )

    deaths = (
        deaths
        .dropna(subset=["tick"])
        .sort_values("tick")
        .reset_index(drop=True)
    )

    # Entry e a primeira kill entre inimigos. Morte por queda/bomba (sem
    # atacante), suicidio e kill em companheiro nao abrem o round. Antes a
    # primeira morte de qualquer tipo valia: no suicidio o jogador ganhava
    # entry kill e entry death ao mesmo tempo.
    atacante = deaths["attacker_name"].astype(str).str.strip()
    vitima = deaths["user_name"].astype(str).str.strip()
    valida = deaths["attacker_name"].notna() & (atacante != "") & (atacante != vitima)
    if "attacker_team_num" in deaths.columns and "user_team_num" in deaths.columns:
        valida = valida & (deaths["attacker_team_num"] != deaths["user_team_num"])
    deaths = deaths[valida].reset_index(drop=True)

    assigned_deaths = []

    for _, round_row in official_rounds.iterrows():

        round_index = int(
            round_row["round_index"]
        )

        tick_start = round_row["tick_start"]
        tick_end = round_row["tick_end"]

        if pd.isna(tick_start):
            continue

        if pd.isna(tick_end):

            round_deaths = deaths[
                deaths["tick"] >= tick_start
            ].copy()

        else:

            round_deaths = deaths[
                (
                    deaths["tick"] >= tick_start
                )
                &
                (
                    deaths["tick"] < tick_end
                )
            ].copy()

        if round_deaths.empty:
            continue

        half = (
            round_row["half"]
            if "half" in round_row.index
            else None
        )

        round_type = round_row[
            "round_type"
        ]

        for _, death in round_deaths.iterrows():

            attacker = clean_name(
                death.get(
                    "attacker_name"
                )
            )

            victim = clean_name(
                death.get(
                    "user_name"
                )
            )

            weapon = clean_name(
                death.get(
                    "weapon"
                )
            )

            assigned_deaths.append(
                {
                    "round_index": round_index,
                    "round_number": round_index,
                    "half": half,
                    "round_type": round_type,
                    "tick_start": tick_start,
                    "tick_end": tick_end,
                    "tick": int(
                        death["tick"]
                    ),
                    "attacker_name": attacker,
                    "victim_name": victim,
                    "weapon": weapon,
                    "headshot": death.get(
                        "headshot"
                    ),
                }
            )

    assigned_deaths = pd.DataFrame(
        assigned_deaths
    )

    if assigned_deaths.empty:
        return pd.DataFrame()

    first_kills = (
        assigned_deaths
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

    first_kills = first_kills[
        [
            "round_index",
            "round_number",
            "half",
            "round_type",
            "tick_start",
            "tick_end",
            "tick",
            "attacker_name",
            "victim_name",
            "weapon",
        ]
    ].copy()

    return first_kills


def build_entry_player_table(
    first_kills,
    official_rounds,
):
    """
    Constrói a tabela individual usada pelo Entry Parser.
    """

    if first_kills.empty:

        return pd.DataFrame(
            columns=[
                "player",
                "entry_attempts",
                "entry_kills",
                "entry_deaths",
                "entry_difference",
                "entry_attempts_pct",
                "entry_success_pct",
            ]
        )

    entry_kills = (
        first_kills[
            first_kills[
                "attacker_name"
            ].notna()
        ]["attacker_name"]
        .rename("player")
        .value_counts()
        .rename_axis("player")
        .reset_index(
            name="entry_kills"
        )
    )

    entry_deaths = (
        first_kills[
            first_kills[
                "victim_name"
            ].notna()
        ]["victim_name"]
        .rename("player")
        .value_counts()
        .rename_axis("player")
        .reset_index(
            name="entry_deaths"
        )
    )

    all_players = sorted(
        set(
            entry_kills["player"].tolist()
        )
        |
        set(
            entry_deaths["player"].tolist()
        )
    )

    result = pd.DataFrame(
        {
            "player": all_players
        }
    )

    result = result.merge(
        entry_kills,
        on="player",
        how="left",
    )

    result = result.merge(
        entry_deaths,
        on="player",
        how="left",
    )

    result["entry_kills"] = (
        result["entry_kills"]
        .fillna(0)
        .astype(int)
    )

    result["entry_deaths"] = (
        result["entry_deaths"]
        .fillna(0)
        .astype(int)
    )

    total_rounds = len(
        official_rounds
    )

    result["entry_attempts"] = (
        result["entry_kills"]
        +
        result["entry_deaths"]
    )

    result["entry_difference"] = (
        result["entry_kills"]
        -
        result["entry_deaths"]
    )

    if total_rounds > 0:

        result["entry_attempts_pct"] = (
            result["entry_attempts"]
            /
            total_rounds
            *
            100
        ).round(0).astype(int)

    else:

        result["entry_attempts_pct"] = 0

    attempts = (
        result["entry_attempts"]
        .replace(0, pd.NA)
    )

    result["entry_success_pct"] = (
        (
            result["entry_kills"]
            /
            attempts
        )
        *
        100
    ).fillna(0).round(0).astype(int)

    result = (
        result
        .sort_values(
            [
                "entry_difference",
                "entry_success_pct",
                "entry_kills",
                "player",
            ],
            ascending=[
                False,
                False,
                False,
                True,
            ],
        )
        .reset_index(drop=True)
    )

    return result