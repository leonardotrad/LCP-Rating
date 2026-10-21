import os
from collections import defaultdict

import numpy as np
import pandas as pd
from demoparser2 import DemoParser

from round_classifier import classify_rounds


# ======================================================================
# CONFIGURAÇÃO
# ======================================================================

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

OUTPUT_EVENTS = "utility_events.csv"
OUTPUT_THROWS = "utility_throws.csv"
OUTPUT_PURCHASES = "utility_purchases.csv"
OUTPUT_DAMAGE = "utility_damage.csv"
OUTPUT_SUPPORT = "utility_support.csv"
OUTPUT_DATA = "data_utility.csv"


# ======================================================================
# UTILITÁRIOS
# ======================================================================


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


def normalize_weapon(value):
    value = clean_name(value)

    if value is None:
        return None

    value = value.lower().strip()

    for prefix in (
        "weapon_",
        "item_",
    ):
        if value.startswith(prefix):
            value = value[len(prefix):]

    return value


def number(value, default=0.0):
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_event(
    parser,
    event_name,
    fields,
):
    try:
        return parser.parse_event(
            event_name=event_name,
            player=fields,
        )
    except Exception as exc:
        print(
            f"AVISO - evento '{event_name}' "
            f"não pôde ser lido: {exc}"
        )
        return []


# ======================================================================
# TIMES
# ======================================================================


def normalize_team(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None

    if value == 2:
        return "TERRORIST"

    if value == 3:
        return "CT"

    return None


# ======================================================================
# ROUNDS
# ======================================================================


def prepare_official_rounds(
    classified_rounds,
):
    official = classified_rounds[
        classified_rounds[
            "round_type"
        ].isin(
            [
                "PISTOL",
                "NORMAL",
                "OVERTIME",
            ]
        )
    ].copy()

    official = (
        official
        .sort_values(
            "tick_start"
        )
        .reset_index(
            drop=True
        )
    )

    official[
        "round_index"
    ] = np.arange(
        len(official),
        dtype=int,
    )

    official[
        "tick_start"
    ] = pd.to_numeric(
        official[
            "tick_start"
        ],
        errors="coerce",
    )

    official[
        "tick_end"
    ] = pd.to_numeric(
        official[
            "tick_end"
        ],
        errors="coerce",
    )

    official = official.dropna(
        subset=[
            "tick_start"
        ]
    ).copy()

    official[
        "tick_start"
    ] = official[
        "tick_start"
    ].astype(np.int64)

    return official


def assign_round_fast(
    events,
    official_rounds,
):
    """
    Associa cada evento ao round correspondente.

    Não usa loops evento x round.
    """

    if events.empty:
        return events.copy()

    result = events.copy()

    if "tick" not in result.columns:
        result[
            "round_index"
        ] = pd.Series(
            dtype="Int64"
        )

        return result

    result[
        "tick"
    ] = pd.to_numeric(
        result[
            "tick"
        ],
        errors="coerce",
    )

    result = result.dropna(
        subset=[
            "tick"
        ]
    ).copy()

    if result.empty:
        result[
            "round_index"
        ] = pd.Series(
            dtype="Int64"
        )

        return result

    result[
        "tick"
    ] = result[
        "tick"
    ].astype(np.int64)

    if official_rounds.empty:
        result[
            "round_index"
        ] = pd.Series(
            dtype="Int64",
            index=result.index,
        )

        return result

    starts = (
        official_rounds[
            "tick_start"
        ]
        .astype(np.int64)
        .to_numpy()
    )

    ends = (
        official_rounds[
            "tick_end"
        ]
        .fillna(
            np.iinfo(
                np.int64
            ).max
        )
        .astype(np.int64)
        .to_numpy()
    )

    round_indexes = (
        official_rounds[
            "round_index"
        ]
        .astype(int)
        .to_numpy()
    )

    ticks = (
        result[
            "tick"
        ].to_numpy(
            dtype=np.int64
        )
    )

    positions = (
        np.searchsorted(
            starts,
            ticks,
            side="right",
        )
        - 1
    )

    valid_position = (
        positions >= 0
    )

    assigned = np.full(
        len(result),
        -1,
        dtype=int,
    )

    if valid_position.any():

        event_positions = np.flatnonzero(
            valid_position
        )

        round_positions = positions[
            valid_position
        ]

        event_ticks = ticks[
            valid_position
        ]

        inside = (
            event_ticks
            <=
            ends[
                round_positions
            ]
        )

        event_positions = (
            event_positions[
                inside
            ]
        )

        round_positions = (
            round_positions[
                inside
            ]
        )

        assigned[
            event_positions
        ] = round_indexes[
            round_positions
        ]

    result[
        "round_index"
    ] = assigned

    result = result[
        result[
            "round_index"
        ] >= 0
    ].copy()

    result[
        "round_index"
    ] = result[
        "round_index"
    ].astype(int)

    return result


# ======================================================================
# ROSTER
# ======================================================================


def get_round_roster(
    parser,
    tick,
):
    try:
        snapshots = pd.DataFrame(
            parser.parse_ticks(
                [
                    "team_num",
                    "team_name",
                    "health",
                    "is_alive",
                    "steamid",
                ],
                ticks=[
                    int(tick)
                ],
            )
        )
    except Exception as exc:
        print(
            f"AVISO - erro ao ler roster "
            f"no tick {tick}: {exc}"
        )

        return {}

    if snapshots.empty:
        return {}

    if "name" not in snapshots.columns:
        return {}

    roster = {}

    for _, row in snapshots.iterrows():

        player = clean_name(
            row.get(
                "name"
            )
        )

        team = normalize_team(
            row.get(
                "team_num"
            )
        )

        if player is None:
            continue

        if team is None:
            continue

        roster[
            player
        ] = team

    return roster


def build_rosters(
    parser,
    official_rounds,
):
    rosters = {}

    for _, row in official_rounds.iterrows():

        round_index = int(
            row[
                "round_index"
            ]
        )

        tick = int(
            row[
                "tick_start"
            ]
        )

        rosters[
            round_index
        ] = get_round_roster(
            parser,
            tick,
        )

    return rosters


def get_all_players(
    rosters,
):
    players = set()

    for roster in rosters.values():
        players.update(
            roster.keys()
        )

    return sorted(
        players
    )


def get_player_team(
    rosters,
    round_index,
    player,
):
    if player is None:
        return None

    return rosters.get(
        int(round_index),
        {}
    ).get(
        player
    )


# ======================================================================
# TIPOS DE UTILITY
# ======================================================================


UTILITY_TYPES = {
    "hegrenade": "HE",

    "molotov": "BURNER",
    "incgrenade": "BURNER",

    "inferno": "BURNER",

    "flashbang": "FLASH",
    "smokegrenade": "SMOKE",
    "decoy": "DECOY",
}


def utility_type(
    weapon,
):
    weapon = normalize_weapon(
        weapon
    )

    if weapon is None:
        return None

    return UTILITY_TYPES.get(
        weapon
    )


# ======================================================================
# EVENTOS
# ======================================================================


def load_utility_events(
    parser,
):
    frames = []

    # ------------------------------------------------------------------
    # WEAPON FIRE
    # ------------------------------------------------------------------

    print()
    print(
        "Lendo weapon_fire..."
    )

    weapon_fire = pd.DataFrame(
        read_event(
            parser,
            "weapon_fire",
            [
                "tick",
                "weapon",
                "user_name",
            ],
        )
    )

    if not weapon_fire.empty:

        weapon_fire[
            "utility_type"
        ] = weapon_fire[
            "weapon"
        ].map(
            utility_type
        )

        weapon_fire = weapon_fire[
            weapon_fire[
                "utility_type"
            ].notna()
        ].copy()

        weapon_fire[
            "event_name"
        ] = "weapon_fire"

        frames.append(
            weapon_fire
        )

    print(
        f"Throws via weapon_fire: "
        f"{len(weapon_fire)}"
    )

    if not weapon_fire.empty:
        print(
            "Throws por tipo:"
        )
        print(
            weapon_fire[
                "utility_type"
            ]
            .value_counts()
            .sort_index()
            .to_string()
        )

    # ------------------------------------------------------------------
    # ITEM PURCHASE
    # ------------------------------------------------------------------

    print()
    print(
        "Lendo item_purchase..."
    )

    purchase = pd.DataFrame(
        read_event(
            parser,
            "item_purchase",
            [
                "tick",
                "user_name",
                "weapon",
                "item",
            ],
        )
    )

    if not purchase.empty:

        purchase[
            "utility_source"
        ] = None

        if "weapon" in purchase.columns:

            purchase[
                "utility_source"
            ] = purchase[
                "weapon"
            ]

        if "item" in purchase.columns:

            purchase[
                "utility_source"
            ] = (
                purchase[
                    "utility_source"
                ].fillna(
                    purchase[
                        "item"
                    ]
                )
            )

        purchase[
            "utility_type"
        ] = purchase[
            "utility_source"
        ].map(
            utility_type
        )

        purchase = purchase[
            purchase[
                "utility_type"
            ].notna()
        ].copy()

        purchase[
            "event_name"
        ] = "item_purchase"

        frames.append(
            purchase
        )

    print(
        f"Compras Utility: "
        f"{len(purchase)}"
    )

    # ------------------------------------------------------------------
    # HE
    # ------------------------------------------------------------------

    print()
    print(
        "Lendo hegrenade_detonate..."
    )

    he = pd.DataFrame(
        read_event(
            parser,
            "hegrenade_detonate",
            [
                "tick",
                "user_name",
                "x",
                "y",
                "z",
                "entityid",
                "grenadeid",
            ],
        )
    )

    if not he.empty:

        he[
            "utility_type"
        ] = "HE"

        he[
            "event_name"
        ] = (
            "hegrenade_detonate"
        )

        frames.append(
            he
        )

    print(
        f"HE detonações: "
        f"{len(he)}"
    )

    # ------------------------------------------------------------------
    # MOLOTOV
    # ------------------------------------------------------------------

    print()
    print(
        "Lendo molotov_detonate..."
    )

    molotov = pd.DataFrame(
        read_event(
            parser,
            "molotov_detonate",
            [
                "tick",
                "user_name",
                "x",
                "y",
                "z",
            ],
        )
    )

    if not molotov.empty:

        molotov[
            "utility_type"
        ] = "BURNER"

        molotov[
            "event_name"
        ] = (
            "molotov_detonate"
        )

        frames.append(
            molotov
        )

    print(
        f"Molotov detonações: "
        f"{len(molotov)}"
    )

    # ------------------------------------------------------------------
    # INFERNO
    # ------------------------------------------------------------------

    print()
    print(
        "Lendo inferno_startburn..."
    )

    inferno = pd.DataFrame(
        read_event(
            parser,
            "inferno_startburn",
            [
                "tick",
                "user_name",
                "entityid",
                "x",
                "y",
                "z",
            ],
        )
    )

    if not inferno.empty:

        inferno[
            "utility_type"
        ] = "BURNER"

        inferno[
            "event_name"
        ] = (
            "inferno_startburn"
        )

        frames.append(
            inferno
        )

    print(
        f"Inferno startburn: "
        f"{len(inferno)}"
    )

    # ------------------------------------------------------------------
    # FLASH
    # ------------------------------------------------------------------

    print()
    print(
        "Lendo flashbang_detonate..."
    )

    flash = pd.DataFrame(
        read_event(
            parser,
            "flashbang_detonate",
            [
                "tick",
                "user_name",
                "entityid",
                "x",
                "y",
                "z",
            ],
        )
    )

    if not flash.empty:

        flash[
            "utility_type"
        ] = "FLASH"

        flash[
            "event_name"
        ] = (
            "flashbang_detonate"
        )

        frames.append(
            flash
        )

    print(
        f"Flash detonações: "
        f"{len(flash)}"
    )

    # ------------------------------------------------------------------
    # SMOKE
    # ------------------------------------------------------------------

    print()
    print(
        "Lendo smokegrenade_detonate..."
    )

    smoke = pd.DataFrame(
        read_event(
            parser,
            "smokegrenade_detonate",
            [
                "tick",
                "user_name",
                "entityid",
                "x",
                "y",
                "z",
            ],
        )
    )

    if not smoke.empty:

        smoke[
            "utility_type"
        ] = "SMOKE"

        smoke[
            "event_name"
        ] = (
            "smokegrenade_detonate"
        )

        frames.append(
            smoke
        )

    print(
        f"Smoke detonações: "
        f"{len(smoke)}"
    )

    # ------------------------------------------------------------------
    # DECOY
    # ------------------------------------------------------------------

    print()
    print(
        "Lendo decoy_started..."
    )

    decoy = pd.DataFrame(
        read_event(
            parser,
            "decoy_started",
            [
                "tick",
                "user_name",
                "entityid",
                "x",
                "y",
                "z",
            ],
        )
    )

    if not decoy.empty:

        decoy[
            "utility_type"
        ] = "DECOY"

        decoy[
            "event_name"
        ] = (
            "decoy_started"
        )

        frames.append(
            decoy
        )

    print(
        f"Decoys: "
        f"{len(decoy)}"
    )

    # ------------------------------------------------------------------
    # PLAYER HURT
    # ------------------------------------------------------------------

    print()
    print(
        "Lendo player_hurt..."
    )

    hurt = pd.DataFrame(
        read_event(
            parser,
            "player_hurt",
            [
                "tick",
                "attacker_name",
                "user_name",
                "weapon",
                "dmg_health",
                "dmg_armor",
                "hitgroup",
            ],
        )
    )

    if not hurt.empty:

        hurt[
            "utility_weapon"
        ] = hurt[
            "weapon"
        ].map(
            normalize_weapon
        )

        hurt[
            "utility_type"
        ] = hurt[
            "utility_weapon"
        ].map(
            utility_type
        )

        hurt = hurt[
            hurt[
                "utility_type"
            ].isin(
                [
                    "HE",
                    "BURNER",
                ]
            )
        ].copy()

        hurt[
            "event_name"
        ] = "player_hurt"

        frames.append(
            hurt
        )

    print(
        f"Player hurt de HE/Burner: "
        f"{len(hurt)}"
    )

    if not hurt.empty:
        print(
            "Dano por weapon:"
        )
        print(
            hurt[
                "utility_weapon"
            ]
            .value_counts()
            .sort_index()
            .to_string()
        )

    # ------------------------------------------------------------------
    # PLAYER BLIND
    # ------------------------------------------------------------------

    print()
    print(
        "Lendo player_blind..."
    )

    blind = pd.DataFrame(
        read_event(
            parser,
            "player_blind",
            [
                "tick",
                "attacker_name",
                "user_name",
                "blind_duration",
            ],
        )
    )

    if not blind.empty:

        blind[
            "utility_type"
        ] = "FLASH"

        blind[
            "event_name"
        ] = "player_blind"

        frames.append(
            blind
        )

    print(
        f"Player blind: "
        f"{len(blind)}"
    )

    # ------------------------------------------------------------------
    # PLAYER DEATH
    # ------------------------------------------------------------------

    print()
    print(
        "Lendo player_death..."
    )

    death = pd.DataFrame(
        read_event(
            parser,
            "player_death",
            [
                "tick",
                "attacker_name",
                "user_name",
                "assister_name",
                "assistedflash",
                "weapon",
            ],
        )
    )

    if not death.empty:

        death[
            "event_name"
        ] = "player_death"

        death[
            "utility_type"
        ] = None

        frames.append(
            death
        )

    print(
        f"Player death: "
        f"{len(death)}"
    )

    if not frames:
        return pd.DataFrame()

    events = pd.concat(
        frames,
        ignore_index=True,
        sort=False,
    )

    events[
        "tick"
    ] = pd.to_numeric(
        events[
            "tick"
        ],
        errors="coerce",
    )

    events = events.dropna(
        subset=[
            "tick"
        ]
    ).copy()

    events[
        "tick"
    ] = events[
        "tick"
    ].astype(np.int64)

    return events


# ======================================================================
# THROWS
# ======================================================================


def build_throws(
    events,
    official_rounds,
):
    if events.empty:
        return pd.DataFrame()

    throws = events[
        events[
            "event_name"
        ]
        == "weapon_fire"
    ].copy()

    if throws.empty:
        return pd.DataFrame()

    throws = assign_round_fast(
        throws,
        official_rounds,
    )

    if throws.empty:
        return throws

    throws[
        "player"
    ] = throws[
        "user_name"
    ].map(
        clean_name
    )

    throws = throws[
        throws[
            "player"
        ].notna()
    ].copy()

    throws[
        "weapon"
    ] = throws[
        "weapon"
    ].map(
        normalize_weapon
    )

    throws = throws[
        [
            "tick",
            "round_index",
            "player",
            "weapon",
            "utility_type",
        ]
    ].copy()

    throws = (
        throws
        .sort_values(
            "tick"
        )
        .drop_duplicates(
            subset=[
                "tick",
                "player",
                "utility_type",
            ],
            keep="first",
        )
        .reset_index(
            drop=True
        )
    )

    return throws


# ======================================================================
# PURCHASES
# ======================================================================


def build_purchases(
    events,
    official_rounds,
):
    if events.empty:
        return pd.DataFrame()

    purchases = events[
        events[
            "event_name"
        ]
        == "item_purchase"
    ].copy()

    if purchases.empty:
        return pd.DataFrame()

    purchases = assign_round_fast(
        purchases,
        official_rounds,
    )

    if purchases.empty:
        return purchases

    purchases[
        "player"
    ] = purchases[
        "user_name"
    ].map(
        clean_name
    )

    purchases = purchases[
        purchases[
            "player"
        ].notna()
    ].copy()

    purchases = purchases[
        [
            "tick",
            "round_index",
            "player",
            "utility_type",
        ]
    ].copy()

    return purchases


# ======================================================================
# DAMAGE
# ======================================================================


def build_damage(
    events,
    official_rounds,
    rosters,
):
    if events.empty:
        return pd.DataFrame()

    damage = events[
        events[
            "event_name"
        ]
        == "player_hurt"
    ].copy()

    if damage.empty:
        return pd.DataFrame()

    damage = assign_round_fast(
        damage,
        official_rounds,
    )

    if damage.empty:
        return damage

    damage[
        "attacker"
    ] = damage[
        "attacker_name"
    ].map(
        clean_name
    )

    damage[
        "victim"
    ] = damage[
        "user_name"
    ].map(
        clean_name
    )

    damage[
        "damage_health"
    ] = pd.to_numeric(
        damage[
            "dmg_health"
        ],
        errors="coerce",
    ).fillna(0)

    damage[
        "damage_armor"
    ] = pd.to_numeric(
        damage[
            "dmg_armor"
        ],
        errors="coerce",
    ).fillna(0)

    rows = []

    for _, row in damage.iterrows():

        attacker = row[
            "attacker"
        ]

        victim = row[
            "victim"
        ]

        if attacker is None:
            continue

        if victim is None:
            continue

        if attacker == victim:
            continue

        round_index = int(
            row[
                "round_index"
            ]
        )

        attacker_team = (
            get_player_team(
                rosters,
                round_index,
                attacker,
            )
        )

        victim_team = (
            get_player_team(
                rosters,
                round_index,
                victim,
            )
        )

        if attacker_team is None:
            continue

        if victim_team is None:
            continue

        damage_health = float(
            row[
                "damage_health"
            ]
        )

        damage_armor = float(
            row[
                "damage_armor"
            ]
        )

        if (
            damage_health <= 0
            and damage_armor <= 0
        ):
            continue

        rows.append(
            {
                "tick": int(
                    row[
                        "tick"
                    ]
                ),
                "round_index": round_index,
                "attacker": attacker,
                "victim": victim,
                "attacker_team": attacker_team,
                "victim_team": victim_team,
                "utility_type": row[
                    "utility_type"
                ],
                "weapon": row.get(
                    "utility_weapon"
                ),
                "damage_health": (
                    damage_health
                ),
                "damage_armor": (
                    damage_armor
                ),
                "damage_total": (
                    damage_health
                    +
                    damage_armor
                ),
            }
        )

    return pd.DataFrame(
        rows
    )


# ======================================================================
# FLASH
# ======================================================================


def build_blinds(
    events,
    official_rounds,
    rosters,
):
    if events.empty:
        return pd.DataFrame()

    blind = events[
        events[
            "event_name"
        ]
        == "player_blind"
    ].copy()

    if blind.empty:
        return pd.DataFrame()

    blind = assign_round_fast(
        blind,
        official_rounds,
    )

    if blind.empty:
        return blind

    blind[
        "thrower"
    ] = blind[
        "attacker_name"
    ].map(
        clean_name
    )

    blind[
        "victim"
    ] = blind[
        "user_name"
    ].map(
        clean_name
    )

    blind[
        "blind_duration"
    ] = pd.to_numeric(
        blind[
            "blind_duration"
        ],
        errors="coerce",
    ).fillna(0)

    rows = []

    for _, row in blind.iterrows():

        thrower = row[
            "thrower"
        ]

        victim = row[
            "victim"
        ]

        if thrower is None:
            continue

        if victim is None:
            continue

        round_index = int(
            row[
                "round_index"
            ]
        )

        thrower_team = (
            get_player_team(
                rosters,
                round_index,
                thrower,
            )
        )

        victim_team = (
            get_player_team(
                rosters,
                round_index,
                victim,
            )
        )

        if thrower_team is None:
            continue

        if victim_team is None:
            continue

        duration = float(
            row[
                "blind_duration"
            ]
        )

        if duration <= 0:
            continue

        target_type = (
            "ENEMY"
            if thrower_team
            != victim_team
            else "TEAM"
        )

        rows.append(
            {
                "tick": int(
                    row[
                        "tick"
                    ]
                ),
                "round_index": round_index,
                "thrower": thrower,
                "victim": victim,
                "thrower_team": thrower_team,
                "victim_team": victim_team,
                "blind_duration": duration,
                "target_type": target_type,
            }
        )

    return pd.DataFrame(
        rows
    )


# ======================================================================
# FLASH SUPPORT
# ======================================================================


def build_flash_extra(
    events,
    blind_df,
):
    players = set()

    if not blind_df.empty:

        players.update(
            blind_df[
                "thrower"
            ]
            .dropna()
            .unique()
            .tolist()
        )

    if not events.empty:

        if "assister_name" in events.columns:

            players.update(
                events[
                    "assister_name"
                ]
                .dropna()
                .map(
                    clean_name
                )
                .dropna()
                .unique()
                .tolist()
            )

    flash_assists = defaultdict(int)
    blind_kills = defaultdict(int)

    deaths = events[
        events[
            "event_name"
        ]
        == "player_death"
    ].copy()

    if not deaths.empty:

        for _, row in deaths.iterrows():

            assister = clean_name(
                row.get(
                    "assister_name"
                )
            )

            if assister is None:
                continue

            assisted_flash = row.get(
                "assistedflash"
            )

            try:
                assisted_flash = bool(
                    assisted_flash
                )
            except Exception:
                assisted_flash = False

            if assisted_flash:
                flash_assists[
                    assister
                ] += 1

    if not deaths.empty and not blind_df.empty:

        for _, row in deaths.iterrows():

            attacker = clean_name(
                row.get(
                    "attacker_name"
                )
            )

            victim = clean_name(
                row.get(
                    "user_name"
                )
            )

            if attacker is None:
                continue

            if victim is None:
                continue

            round_value = row.get(
                "round_index"
            )

            if pd.isna(
                round_value
            ):
                continue

            round_index = int(
                round_value
            )

            tick = int(
                row[
                    "tick"
                ]
            )

            recent = blind_df[
                (
                    blind_df[
                        "round_index"
                    ]
                    == round_index
                )
                &
                (
                    blind_df[
                        "thrower"
                    ]
                    != attacker
                )
                &
                (
                    blind_df[
                        "victim"
                    ]
                    == victim
                )
                &
                (
                    blind_df[
                        "target_type"
                    ]
                    == "ENEMY"
                )
                &
                (
                    blind_df[
                        "tick"
                    ]
                    <= tick
                )
                &
                (
                    blind_df[
                        "tick"
                    ]
                    >= tick - 320
                )
            ]

            if not recent.empty:

                thrower = recent.iloc[-1][
                    "thrower"
                ]

                blind_kills[
                    thrower
                ] += 1

    rows = []

    for player in sorted(
        players
    ):

        rows.append(
            {
                "player": player,
                "flash_assists": int(
                    flash_assists[
                        player
                    ]
                ),
                "blind_kills": int(
                    blind_kills[
                        player
                    ]
                ),
            }
        )

    return pd.DataFrame(
        rows
    )


# ======================================================================
# MARCAR SUCESSO
# ======================================================================


def mark_success(
    throws,
    damage,
    blind_df,
):
    if throws.empty:
        return throws

    result = throws.copy()

    result[
        "successful"
    ] = 0

    result[
        "success_type"
    ] = ""

    if not damage.empty:

        damage_groups = set(
            zip(
                damage[
                    "round_index"
                ],
                damage[
                    "attacker"
                ],
                damage[
                    "utility_type"
                ],
            )
        )

        for idx, row in result.iterrows():

            utility = row[
                "utility_type"
            ]

            if utility not in {
                "HE",
                "BURNER",
            }:
                continue

            key = (
                int(
                    row[
                        "round_index"
                    ]
                ),
                row[
                    "player"
                ],
                utility,
            )

            if key in damage_groups:

                result.at[
                    idx,
                    "successful"
                ] = 1

                result.at[
                    idx,
                    "success_type"
                ] = "DAMAGE"

    if not blind_df.empty:

        blind_groups = set(
            zip(
                blind_df[
                    "round_index"
                ],
                blind_df[
                    "thrower"
                ],
            )
        )

        for idx, row in result.iterrows():

            if row[
                "utility_type"
            ] != "FLASH":
                continue

            key = (
                int(
                    row[
                        "round_index"
                    ]
                ),
                row[
                    "player"
                ],
            )

            if key in blind_groups:

                result.at[
                    idx,
                    "successful"
                ] = 1

                result.at[
                    idx,
                    "success_type"
                ] = "BLIND"

    return result


# ======================================================================
# TABELA FINAL
# ======================================================================


def build_final_table(
    players,
    throws,
    purchases,
    damage,
    blind_df,
    flash_extra,
):
    rows = []

    for player in players:

        # ------------------------------------------------------------
        # THROWS
        # ------------------------------------------------------------

        if throws.empty:
            player_throws = pd.DataFrame()
        else:
            player_throws = throws[
                throws[
                    "player"
                ]
                == player
            ]

        he_thrown = int(
            (
                player_throws[
                    "utility_type"
                ]
                == "HE"
            ).sum()
        )

        burner_thrown = int(
            (
                player_throws[
                    "utility_type"
                ]
                == "BURNER"
            ).sum()
        )

        flash_thrown = int(
            (
                player_throws[
                    "utility_type"
                ]
                == "FLASH"
            ).sum()
        )

        smoke_thrown = int(
            (
                player_throws[
                    "utility_type"
                ]
                == "SMOKE"
            ).sum()
        )

        decoy_thrown = int(
            (
                player_throws[
                    "utility_type"
                ]
                == "DECOY"
            ).sum()
        )

        he_successful = int(
            (
                (
                    player_throws[
                        "utility_type"
                    ]
                    == "HE"
                )
                &
                (
                    player_throws[
                        "successful"
                    ]
                    == 1
                )
            ).sum()
        )

        burner_successful = int(
            (
                (
                    player_throws[
                        "utility_type"
                    ]
                    == "BURNER"
                )
                &
                (
                    player_throws[
                        "successful"
                    ]
                    == 1
                )
            ).sum()
        )

        flash_successful = int(
            (
                (
                    player_throws[
                        "utility_type"
                    ]
                    == "FLASH"
                )
                &
                (
                    player_throws[
                        "successful"
                    ]
                    == 1
                )
            ).sum()
        )

        # ------------------------------------------------------------
        # PURCHASE
        # ------------------------------------------------------------

        he_purchased = 0
        burner_purchased = 0

        if not purchases.empty:

            player_purchases = purchases[
                purchases[
                    "player"
                ]
                == player
            ]

            he_purchased = int(
                (
                    player_purchases[
                        "utility_type"
                    ]
                    == "HE"
                ).sum()
            )

            burner_purchased = int(
                (
                    player_purchases[
                        "utility_type"
                    ]
                    == "BURNER"
                ).sum()
            )

        # ------------------------------------------------------------
        # DAMAGE
        # ------------------------------------------------------------

        he_enemy_health = 0.0
        he_enemy_armor = 0.0

        burner_enemy_health = 0.0
        burner_enemy_armor = 0.0

        he_team_health = 0.0
        he_team_armor = 0.0

        burner_team_health = 0.0
        burner_team_armor = 0.0

        if not damage.empty:

            player_damage = damage[
                damage[
                    "attacker"
                ]
                == player
            ]

            # --------------------------------------------------------
            # HE
            # --------------------------------------------------------

            he_damage = player_damage[
                player_damage[
                    "utility_type"
                ]
                == "HE"
            ]

            if not he_damage.empty:

                enemy_he = he_damage[
                    he_damage[
                        "attacker_team"
                    ]
                    != he_damage[
                        "victim_team"
                    ]
                ]

                team_he = he_damage[
                    he_damage[
                        "attacker_team"
                    ]
                    == he_damage[
                        "victim_team"
                    ]
                ]

                he_enemy_health = float(
                    enemy_he[
                        "damage_health"
                    ].sum()
                )

                he_enemy_armor = float(
                    enemy_he[
                        "damage_armor"
                    ].sum()
                )

                he_team_health = float(
                    team_he[
                        "damage_health"
                    ].sum()
                )

                he_team_armor = float(
                    team_he[
                        "damage_armor"
                    ].sum()
                )

            # --------------------------------------------------------
            # BURNER
            # --------------------------------------------------------

            burner_damage = player_damage[
                player_damage[
                    "utility_type"
                ]
                == "BURNER"
            ]

            if not burner_damage.empty:

                enemy_burner = burner_damage[
                    burner_damage[
                        "attacker_team"
                    ]
                    != burner_damage[
                        "victim_team"
                    ]
                ]

                team_burner = burner_damage[
                    burner_damage[
                        "attacker_team"
                    ]
                    == burner_damage[
                        "victim_team"
                    ]
                ]

                burner_enemy_health = float(
                    enemy_burner[
                        "damage_health"
                    ].sum()
                )

                burner_enemy_armor = float(
                    enemy_burner[
                        "damage_armor"
                    ].sum()
                )

                burner_team_health = float(
                    team_burner[
                        "damage_health"
                    ].sum()
                )

                burner_team_armor = float(
                    team_burner[
                        "damage_armor"
                    ].sum()
                )

        # ------------------------------------------------------------
        # FLASH
        # ------------------------------------------------------------

        enemies_flashed = 0
        team_flashes = 0
        enemy_blind_seconds = 0.0
        team_blind_seconds = 0.0

        if not blind_df.empty:

            player_blinds = blind_df[
                blind_df[
                    "thrower"
                ]
                == player
            ]

            enemies = player_blinds[
                player_blinds[
                    "target_type"
                ]
                == "ENEMY"
            ]

            teammates = player_blinds[
                player_blinds[
                    "target_type"
                ]
                == "TEAM"
            ]

            enemies_flashed = int(
                len(enemies)
            )

            team_flashes = int(
                len(teammates)
            )

            enemy_blind_seconds = float(
                enemies[
                    "blind_duration"
                ].sum()
            )

            team_blind_seconds = float(
                teammates[
                    "blind_duration"
                ].sum()
            )

        # ------------------------------------------------------------
        # FLASH EXTRAS
        # ------------------------------------------------------------

        flash_assists = 0
        blind_kills = 0

        if not flash_extra.empty:

            match = flash_extra[
                flash_extra[
                    "player"
                ]
                == player
            ]

            if not match.empty:

                flash_assists = int(
                    match.iloc[0][
                        "flash_assists"
                    ]
                )

                blind_kills = int(
                    match.iloc[0][
                        "blind_kills"
                    ]
                )

        rows.append(
            {
                "player": player,

                # HE
                "he_thrown": he_thrown,
                "he_successful": he_successful,
                "he_purchased": he_purchased,

                "he_enemy_health": round(
                    he_enemy_health,
                    2,
                ),

                "he_enemy_armor": round(
                    he_enemy_armor,
                    2,
                ),

                "he_team_health": round(
                    he_team_health,
                    2,
                ),

                "he_team_armor": round(
                    he_team_armor,
                    2,
                ),

                # BURNER
                "burner_thrown": burner_thrown,
                "burner_successful": (
                    burner_successful
                ),
                "burner_purchased": (
                    burner_purchased
                ),

                "burner_enemy_health": round(
                    burner_enemy_health,
                    2,
                ),

                "burner_enemy_armor": round(
                    burner_enemy_armor,
                    2,
                ),

                "burner_team_health": round(
                    burner_team_health,
                    2,
                ),

                "burner_team_armor": round(
                    burner_team_armor,
                    2,
                ),

                # FLASH
                "flash_thrown": flash_thrown,
                "flash_successful": (
                    flash_successful
                ),
                "enemies_flashed": (
                    enemies_flashed
                ),
                "team_flashes": (
                    team_flashes
                ),
                "flash_assists": (
                    flash_assists
                ),
                "blind_kills": (
                    blind_kills
                ),

                "enemy_blind_seconds": round(
                    enemy_blind_seconds,
                    2,
                ),

                "team_blind_seconds": round(
                    team_blind_seconds,
                    2,
                ),

                # OTHER
                "smokes_thrown": (
                    smoke_thrown
                ),
                "decoys_thrown": (
                    decoy_thrown
                ),
            }
        )

    return pd.DataFrame(
        rows
    )


# ======================================================================
# MAIN
# ======================================================================


def main():

    print(
        "=" * 100
    )
    print(
        "LCP RATING - UTILITY PARSER"
    )
    print(
        "=" * 100
    )

    if not os.path.exists(
        DEMO_PATH
    ):
        raise FileNotFoundError(
            f"Demo não encontrada: "
            f"{DEMO_PATH}"
        )

    parser = DemoParser(
        DEMO_PATH
    )

    # ==================================================================
    # ROUNDS
    # ==================================================================

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

    deaths_for_rounds = pd.DataFrame(
        read_event(
            parser,
            "player_death",
            [
                "tick",
                "attacker_name",
                "user_name",
            ],
        )
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

    print()
    print(
        "Classificando rounds..."
    )

    classified = pd.DataFrame(
        classify_rounds(
            rounds,
            deaths_for_rounds,
            half_events,
        )
    )

    official_rounds = (
        prepare_official_rounds(
            classified
        )
    )

    print(
        f"Rounds oficiais: "
        f"{len(official_rounds)}"
    )

    # ==================================================================
    # ROSTER
    # ==================================================================

    print()
    print(
        "Identificando roster por round..."
    )

    rosters = build_rosters(
        parser,
        official_rounds,
    )

    players = get_all_players(
        rosters
    )

    complete_rounds = sum(
        1
        for roster in rosters.values()
        if len(roster) >= 10
    )

    print(
        f"Jogadores encontrados: "
        f"{len(players)}"
    )

    print(players)

    print(
        f"Rounds com roster completo: "
        f"{complete_rounds}/"
        f"{len(official_rounds)}"
    )

    # ==================================================================
    # EVENTOS
    # ==================================================================

    events = load_utility_events(
        parser
    )

    if events.empty:
        raise RuntimeError(
            "Nenhum evento foi encontrado."
        )

    print()
    print(
        "Associando eventos aos rounds..."
    )

    events = assign_round_fast(
        events,
        official_rounds,
    )

    print(
        f"Eventos nos rounds oficiais: "
        f"{len(events)}"
    )

    print()
    print(
        "Resumo dos eventos:"
    )

    counts = (
        events[
            "event_name"
        ]
        .value_counts()
        .sort_index()
    )

    for event_name, count in (
        counts.items()
    ):
        print(
            f"  {event_name}: {count}"
        )

    # ==================================================================
    # THROWS
    # ==================================================================

    print()
    print(
        "Processando throws..."
    )

    throws = build_throws(
        events,
        official_rounds,
    )

    print(
        f"Throws reconhecidos: "
        f"{len(throws)}"
    )

    if not throws.empty:

        print()
        print(
            "Throws por tipo:"
        )

        print(
            throws[
                "utility_type"
            ]
            .value_counts()
            .sort_index()
            .to_string()
        )

        print()
        print(
            "Burners por jogador:"
        )

        burner_by_player = (
            throws[
                throws[
                    "utility_type"
                ]
                == "BURNER"
            ]
            .groupby(
                "player"
            )
            .size()
            .sort_values(
                ascending=False
            )
        )

        print(
            burner_by_player.to_string()
        )

    # ==================================================================
    # PURCHASES
    # ==================================================================

    print()
    print(
        "Processando compras..."
    )

    purchases = build_purchases(
        events,
        official_rounds,
    )

    print(
        f"Compras reconhecidas: "
        f"{len(purchases)}"
    )

    # ==================================================================
    # DAMAGE
    # ==================================================================

    print()
    print(
        "Processando dano HE/Burner..."
    )

    damage = build_damage(
        events,
        official_rounds,
        rosters,
    )

    print(
        f"Eventos de dano válidos: "
        f"{len(damage)}"
    )

    if not damage.empty:

        print()
        print(
            "Dano de vida por tipo:"
        )

        print(
            damage.groupby(
                "utility_type"
            )[
                "damage_health"
            ]
            .sum()
            .sort_index()
            .to_string()
        )

        print()
        print(
            "Dano de armadura por tipo:"
        )

        print(
            damage.groupby(
                "utility_type"
            )[
                "damage_armor"
            ]
            .sum()
            .sort_index()
            .to_string()
        )

        print()
        print(
            "Dano por weapon:"
        )

        print(
            damage.groupby(
                "weapon"
            )[
                [
                    "damage_health",
                    "damage_armor",
                ]
            ]
            .sum()
            .sort_values(
                "damage_health",
                ascending=False,
            )
            .to_string()
        )

    # ==================================================================
    # FLASH
    # ==================================================================

    print()
    print(
        "Processando flashes / suporte..."
    )

    blind_df = build_blinds(
        events,
        official_rounds,
        rosters,
    )

    print(
        f"Eventos de blind válidos: "
        f"{len(blind_df)}"
    )

    flash_extra = (
        build_flash_extra(
            events,
            blind_df,
        )
    )

    # ==================================================================
    # SUCESSO
    # ==================================================================

    throws = mark_success(
        throws,
        damage,
        blind_df,
    )

    # ==================================================================
    # FINAL
    # ==================================================================

    final = build_final_table(
        players,
        throws,
        purchases,
        damage,
        blind_df,
        flash_extra,
    )

    if final.empty:
        raise RuntimeError(
            "Tabela final vazia."
        )

    final = final.fillna(0)

    integer_columns = [
        "he_thrown",
        "he_successful",
        "he_purchased",

        "burner_thrown",
        "burner_successful",
        "burner_purchased",

        "flash_thrown",
        "flash_successful",
        "enemies_flashed",
        "team_flashes",
        "flash_assists",
        "blind_kills",

        "smokes_thrown",
        "decoys_thrown",
    ]

    for column in integer_columns:

        if column not in final.columns:
            final[
                column
            ] = 0

        final[
            column
        ] = pd.to_numeric(
            final[
                column
            ],
            errors="coerce",
        ).fillna(
            0
        ).round().astype(int)

    final = final.sort_values(
        "player"
    ).reset_index(
        drop=True
    )

    # ==================================================================
    # EXPORTS
    # ==================================================================

    events.to_csv(
        OUTPUT_EVENTS,
        index=False,
    )

    throws.to_csv(
        OUTPUT_THROWS,
        index=False,
    )

    purchases.to_csv(
        OUTPUT_PURCHASES,
        index=False,
    )

    damage.to_csv(
        OUTPUT_DAMAGE,
        index=False,
    )

    blind_df.to_csv(
        OUTPUT_SUPPORT,
        index=False,
    )

    final.to_csv(
        OUTPUT_DATA,
        index=False,
    )

    # ==================================================================
    # RESUMO
    # ==================================================================

    print()
    print(
        "=" * 100
    )
    print(
        "UTILITY - RESUMO"
    )
    print(
        "=" * 100
    )

    print(
        final.to_string(
            index=False
        )
    )

    print()
    print(
        "=" * 100
    )
    print(
        "ARQUIVOS GERADOS"
    )
    print(
        "=" * 100
    )

    print(
        OUTPUT_EVENTS
    )
    print(
        OUTPUT_THROWS
    )
    print(
        OUTPUT_PURCHASES
    )
    print(
        OUTPUT_DAMAGE
    )
    print(
        OUTPUT_SUPPORT
    )
    print(
        OUTPUT_DATA
    )

    print()
    print(
        "Utility parser executado "
        "com sucesso."
    )


if __name__ == "__main__":
    main()