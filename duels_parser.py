import os
import pandas as pd
from demoparser2 import DemoParser

from round_classifier import classify_rounds
from entry_engine import (
    prepare_official_rounds,
    get_entry_events,
)


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
        return "TERRORIST"

    if value == 3:
        return "CT"

    return None


def normalize_weapon(value):

    value = clean_name(value)

    if value is None:
        return None

    return value.lower()


def valid_opponent_duel(
    attacker,
    victim,
    player_teams,
):

    if attacker is None:
        return False

    if victim is None:
        return False

    if attacker == victim:
        return False

    attacker_team = player_teams.get(
        attacker
    )

    victim_team = player_teams.get(
        victim
    )

    if attacker_team is None:
        return False

    if victim_team is None:
        return False

    return (
        attacker_team
        != victim_team
    )


# ================================================================
# ROUND ROSTER
# ================================================================

def get_round_roster(
    parser,
    tick,
):

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


def build_round_rosters(
    parser,
    official_rounds,
):

    round_rosters = {}

    for _, row in official_rounds.iterrows():

        round_index = int(
            row["round_index"]
        )

        tick_start = int(
            row["tick_start"]
        )

        round_rosters[
            round_index
        ] = get_round_roster(
            parser,
            tick_start,
        )

    return round_rosters


def get_all_players(
    round_rosters,
):

    players = set()

    for roster in (
        round_rosters.values()
    ):

        players.update(
            roster.keys()
        )

    return players


# ================================================================
# KILLS
# ================================================================

def parse_kills(
    parser,
    official_rounds,
    round_rosters,
):

    deaths = pd.DataFrame(
        parser.parse_event(
            event_name="player_death",
            player=[
                "tick",
                "attacker_name",
                "user_name",
                "weapon",
                "headshot",
                "dmg_health",
                "dmg_armor",
                "hitgroup",
                "thrusmoke",
                "noscope",
                "attackerblind",
                "attackerinair",
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
        .dropna(
            subset=["tick"]
        )
        .sort_values("tick")
        .reset_index(drop=True)
    )

    rows = []

    for _, round_row in (
        official_rounds.iterrows()
    ):

        round_index = int(
            round_row["round_index"]
        )

        start_tick = int(
            round_row["tick_start"]
        )

        end_value = (
            round_row["tick_end"]
        )

        if pd.isna(end_value):

            round_deaths = deaths[
                deaths["tick"] >= start_tick
            ].copy()

        else:

            end_tick = int(
                end_value
            )

            round_deaths = deaths[
                (
                    deaths["tick"]
                    >= start_tick
                )
                &
                (
                    deaths["tick"]
                    <= end_tick
                )
            ].copy()

        player_teams = (
            round_rosters.get(
                round_index,
                {}
            )
        )

        for _, death in (
            round_deaths.iterrows()
        ):

            attacker = clean_name(
                death[
                    "attacker_name"
                ]
            )

            victim = clean_name(
                death[
                    "user_name"
                ]
            )

            if not valid_opponent_duel(
                attacker,
                victim,
                player_teams,
            ):
                continue

            rows.append(
                {
                    "round_index": round_index,
                    "tick": int(
                        death["tick"]
                    ),
                    "player": attacker,
                    "opponent": victim,
                    "event": "KILL",
                    "weapon": normalize_weapon(
                        death["weapon"]
                    ),
                    "headshot": death.get(
                        "headshot"
                    ),
                    "dmg_health": death.get(
                        "dmg_health",
                        0,
                    ),
                    "dmg_armor": death.get(
                        "dmg_armor",
                        0,
                    ),
                    "hitgroup": death.get(
                        "hitgroup"
                    ),
                    "entry": False,
                    "trade": False,
                }
            )

    return pd.DataFrame(
        rows
    )


# ================================================================
# DAMAGE
# ================================================================

def parse_damage(
    parser,
    official_rounds,
    round_rosters,
):

    hurts = pd.DataFrame(
        parser.parse_event(
            event_name="player_hurt",
            player=[
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

    if hurts.empty:
        return pd.DataFrame()

    hurts["tick"] = pd.to_numeric(
        hurts["tick"],
        errors="coerce",
    )

    hurts["dmg_health"] = (
        pd.to_numeric(
            hurts["dmg_health"],
            errors="coerce",
        )
        .fillna(0)
    )

    hurts["dmg_armor"] = (
        pd.to_numeric(
            hurts["dmg_armor"],
            errors="coerce",
        )
        .fillna(0)
    )

    hurts = (
        hurts
        .dropna(
            subset=["tick"]
        )
        .sort_values("tick")
        .reset_index(drop=True)
    )

    rows = []

    for _, round_row in (
        official_rounds.iterrows()
    ):

        round_index = int(
            round_row["round_index"]
        )

        start_tick = int(
            round_row["tick_start"]
        )

        end_value = (
            round_row["tick_end"]
        )

        if pd.isna(end_value):

            round_hurts = hurts[
                hurts["tick"] >= start_tick
            ].copy()

        else:

            end_tick = int(
                end_value
            )

            round_hurts = hurts[
                (
                    hurts["tick"]
                    >= start_tick
                )
                &
                (
                    hurts["tick"]
                    <= end_tick
                )
            ].copy()

        player_teams = (
            round_rosters.get(
                round_index,
                {}
            )
        )

        for _, hurt in (
            round_hurts.iterrows()
        ):

            attacker = clean_name(
                hurt[
                    "attacker_name"
                ]
            )

            victim = clean_name(
                hurt[
                    "user_name"
                ]
            )

            if not valid_opponent_duel(
                attacker,
                victim,
                player_teams,
            ):
                continue

            damage = float(
                hurt["dmg_health"]
            )

            if damage <= 0:
                continue

            rows.append(
                {
                    "round_index": round_index,
                    "tick": int(
                        hurt["tick"]
                    ),
                    "player": attacker,
                    "opponent": victim,
                    "event": "DAMAGE",
                    "weapon": normalize_weapon(
                        hurt["weapon"]
                    ),
                    "damage": damage,
                    "damage_armor": float(
                        hurt["dmg_armor"]
                    ),
                    "hitgroup": hurt.get(
                        "hitgroup"
                    ),
                }
            )

    return pd.DataFrame(
        rows
    )


# ================================================================
# MARCAR ENTRY
# ================================================================

def mark_entries(
    kill_df,
    first_kills,
):

    kill_df = kill_df.copy()

    kill_df["entry"] = False

    if kill_df.empty:
        return kill_df

    if first_kills.empty:
        return kill_df

    entry_keys = set(
        zip(
            first_kills[
                "round_index"
            ].astype(int),
            first_kills[
                "attacker_name"
            ],
            first_kills[
                "victim_name"
            ],
        )
    )

    for idx, row in (
        kill_df.iterrows()
    ):

        key = (
            int(
                row["round_index"]
            ),
            row["player"],
            row["opponent"],
        )

        if key in entry_keys:

            kill_df.at[
                idx,
                "entry"
            ] = True

    return kill_df


# ================================================================
# TRADE
# ================================================================

def mark_trades(
    kill_df,
):

    kill_df = kill_df.copy()

    kill_df["trade"] = False

    if kill_df.empty:
        return kill_df

    deaths_by_round = {}

    for idx, row in (
        kill_df.iterrows()
    ):

        round_index = int(
            row["round_index"]
        )

        deaths_by_round.setdefault(
            round_index,
            [],
        ).append(
            {
                "idx": idx,
                "tick": int(
                    row["tick"]
                ),
                "player": row["player"],
                "opponent": row["opponent"],
            }
        )

    for _, events in (
        deaths_by_round.items()
    ):

        events.sort(
            key=lambda item: item["tick"]
        )

        for i, event in enumerate(
            events
        ):

            for j in range(
                max(0, i - 5),
                i,
            ):

                previous = events[j]

                elapsed = (
                    event["tick"]
                    -
                    previous["tick"]
                ) / 64.0

                if elapsed < 0:
                    continue

                if elapsed > 5.0:
                    continue

                if (
                    event["opponent"]
                    ==
                    previous["player"]
                ):

                    kill_df.at[
                        event["idx"],
                        "trade"
                    ] = True

                    break

    return kill_df


# ================================================================
# AGREGAÇÃO
# ================================================================

def aggregate_duels(
    kill_df,
    damage_df,
):

    duel_keys = set()

    if not kill_df.empty:

        for _, row in (
            kill_df.iterrows()
        ):

            duel_keys.add(
                (
                    row["player"],
                    row["opponent"],
                )
            )

    if not damage_df.empty:

        for _, row in (
            damage_df.iterrows()
        ):

            duel_keys.add(
                (
                    row["player"],
                    row["opponent"],
                )
            )

    rows = []

    for player, opponent in sorted(
        duel_keys
    ):

        if kill_df.empty:

            player_kills = pd.DataFrame()
            player_deaths = pd.DataFrame()

        else:

            player_kills = kill_df[
                (
                    kill_df["player"]
                    == player
                )
                &
                (
                    kill_df["opponent"]
                    == opponent
                )
            ]

            player_deaths = kill_df[
                (
                    kill_df["player"]
                    == opponent
                )
                &
                (
                    kill_df["opponent"]
                    == player
                )
            ]

        kills = int(
            len(player_kills)
        )

        deaths = int(
            len(player_deaths)
        )

        if damage_df.empty:

            damage = 0.0
            damage_received = 0.0

        else:

            damage = float(
                damage_df[
                    (
                        damage_df["player"]
                        == player
                    )
                    &
                    (
                        damage_df["opponent"]
                        == opponent
                    )
                ]["damage"].sum()
            )

            damage_received = float(
                damage_df[
                    (
                        damage_df["player"]
                        == opponent
                    )
                    &
                    (
                        damage_df["opponent"]
                        == player
                    )
                ]["damage"].sum()
            )

        if player_kills.empty:

            entry_kills = 0
            trade_kills = 0

        else:

            entry_kills = int(
                player_kills[
                    "entry"
                ].sum()
            )

            trade_kills = int(
                player_kills[
                    "trade"
                ].sum()
            )

        if player_deaths.empty:

            entry_deaths = 0
            trade_deaths = 0

        else:

            entry_deaths = int(
                player_deaths[
                    "entry"
                ].sum()
            )

            trade_deaths = int(
                player_deaths[
                    "trade"
                ].sum()
            )

        kd = (
            round(
                kills / deaths,
                2,
            )
            if deaths > 0
            else None
        )

        damage_diff = round(
            damage
            - damage_received,
            2,
        )

        rows.append(
            {
                "player": player,
                "opponent": opponent,
                "kills": kills,
                "deaths": deaths,
                "damage": round(
                    damage,
                    2,
                ),
                "damage_received": round(
                    damage_received,
                    2,
                ),
                "damage_diff": damage_diff,
                "entry_kills": entry_kills,
                "entry_deaths": entry_deaths,
                "trade_kills": trade_kills,
                "trade_deaths": trade_deaths,
                "kd": kd,
            }
        )

    return pd.DataFrame(
        rows
    )


# ================================================================
# VALIDAÇÃO
# ================================================================

def validate_duels(
    duel_df,
):

    print()
    print(
        "=" * 100
    )
    print(
        "VALIDAÇÃO INTERNA DOS DUELOS"
    )
    print(
        "=" * 100
    )

    if duel_df.empty:

        print(
            "Nenhum duelo encontrado."
        )

        return

    errors = []

    for _, row in (
        duel_df.iterrows()
    ):

        player = row["player"]
        opponent = row["opponent"]

        reverse = duel_df[
            (
                duel_df["player"]
                == opponent
            )
            &
            (
                duel_df["opponent"]
                == player
            )
        ]

        if reverse.empty:
            continue

        reverse_row = reverse.iloc[0]

        if (
            row["kills"]
            != reverse_row["deaths"]
        ):

            errors.append(
                (
                    player,
                    opponent,
                    "KILLS_DEATHS",
                )
            )

        if (
            row["damage"]
            != reverse_row[
                "damage_received"
            ]
        ):

            errors.append(
                (
                    player,
                    opponent,
                    "DAMAGE_RECEIVED",
                )
            )

        if (
            row["entry_kills"]
            != reverse_row[
                "entry_deaths"
            ]
        ):

            errors.append(
                (
                    player,
                    opponent,
                    "ENTRY",
                )
            )

        if (
            row["trade_kills"]
            != reverse_row[
                "trade_deaths"
            ]
        ):

            errors.append(
                (
                    player,
                    opponent,
                    "TRADE",
                )
            )

    if not errors:

        print(
            "OK - todas as relações "
            "A→B / B→A estão consistentes."
        )

    else:

        print(
            f"Problemas encontrados: "
            f"{len(errors)}"
        )

        for error in errors[:20]:

            print(
                error
            )


# ================================================================
# RESUMO
# ================================================================

def print_player_summary(
    duels,
):

    if duels.empty:
        return

    print()
    print(
        "=" * 100
    )
    print(
        "RESUMO POR JOGADOR"
    )
    print(
        "=" * 100
    )

    players = sorted(
        set(
            duels["player"]
        )
        |
        set(
            duels["opponent"]
        )
    )

    rows = []

    for player in players:

        outgoing = duels[
            duels["player"] == player
        ]

        kills = int(
            outgoing["kills"].sum()
        )

        deaths = int(
            outgoing["deaths"].sum()
        )

        damage = float(
            outgoing["damage"].sum()
        )

        damage_received = float(
            outgoing[
                "damage_received"
            ].sum()
        )

        entry_kills = int(
            outgoing[
                "entry_kills"
            ].sum()
        )

        entry_deaths = int(
            outgoing[
                "entry_deaths"
            ].sum()
        )

        trade_kills = int(
            outgoing[
                "trade_kills"
            ].sum()
        )

        trade_deaths = int(
            outgoing[
                "trade_deaths"
            ].sum()
        )

        rows.append(
            {
                "player": player,
                "kills": kills,
                "deaths": deaths,
                "damage": round(
                    damage,
                    2,
                ),
                "damage_received": round(
                    damage_received,
                    2,
                ),
                "damage_diff": round(
                    damage
                    - damage_received,
                    2,
                ),
                "entry_kills": entry_kills,
                "entry_deaths": entry_deaths,
                "trade_kills": trade_kills,
                "trade_deaths": trade_deaths,
            }
        )

    summary = pd.DataFrame(
        rows
    )

    print(
        summary.to_string(
            index=False
        )
    )


# ================================================================
# MAIN
# ================================================================

def main():

    print(
        "=" * 100
    )
    print(
        "LCP RATING - DUELS PARSER"
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

    # ============================================================
    # ROUNDS
    # ============================================================

    print()
    print(
        "Lendo rounds..."
    )

    rounds = pd.DataFrame(
        parser.parse_event(
            event_name="round_poststart",
            player=[
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

    # ============================================================
    # DEATHS PARA CLASSIFICAÇÃO
    # ============================================================

    print()
    print(
        "Lendo mortes para "
        "classificação de rounds..."
    )

    deaths_for_rounds = pd.DataFrame(
        parser.parse_event(
            event_name="player_death",
            player=[
                "tick",
                "attacker_name",
                "user_name",
                "weapon",
            ],
        )
    )

    deaths_for_rounds["tick"] = (
        pd.to_numeric(
            deaths_for_rounds["tick"],
            errors="coerce",
        )
    )

    deaths_for_rounds = (
        deaths_for_rounds
        .dropna(
            subset=["tick"]
        )
        .sort_values("tick")
        .reset_index(drop=True)
    )

    # ============================================================
    # HALF
    # ============================================================

    half_events = pd.DataFrame(
        parser.parse_event(
            event_name=(
                "round_announce_last_round_half"
            ),
            player=[
                "tick",
            ],
        )
    )

    # ============================================================
    # CLASSIFICAÇÃO
    # ============================================================

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

    official = (
        prepare_official_rounds(
            classified
        )
    )

    print(
        f"Rounds oficiais: "
        f"{len(official)}"
    )

    # ============================================================
    # ROSTER
    # ============================================================

    print()
    print(
        "Identificando roster por round..."
    )

    round_rosters = (
        build_round_rosters(
            parser,
            official,
        )
    )

    all_players = get_all_players(
        round_rosters
    )

    print(
        f"Jogadores encontrados: "
        f"{len(all_players)}"
    )

    print(
        sorted(all_players)
    )

    complete_rosters = sum(
        1
        for roster
        in round_rosters.values()
        if len(roster) >= 10
    )

    print(
        f"Rounds com roster completo: "
        f"{complete_rosters}/"
        f"{len(official)}"
    )

    # ============================================================
    # ENTRY ENGINE
    # ============================================================

    print()
    print(
        "Calculando Entry pelo Entry Engine..."
    )

    first_kills = get_entry_events(
        parser,
        official,
    )

    entry_total = (
        len(first_kills)
    )

    print(
        f"First kills detectadas: "
        f"{entry_total}"
    )

    # ============================================================
    # KILLS
    # ============================================================

    print()
    print(
        "Lendo kills por adversário..."
    )

    kills = parse_kills(
        parser,
        official,
        round_rosters,
    )

    print(
        f"Kills válidos de duelo: "
        f"{len(kills)}"
    )

    # ============================================================
    # ENTRY
    # ============================================================

    print()
    print(
        "Relacionando Entry..."
    )

    kills = mark_entries(
        kills,
        first_kills,
    )

    entry_total_duels = (
        int(
            kills["entry"].sum()
        )
        if not kills.empty
        else 0
    )

    print(
        f"Entry kills detectadas: "
        f"{entry_total_duels}"
    )

    # ============================================================
    # TRADE
    # ============================================================

    print()
    print(
        "Relacionando Trades..."
    )

    kills = mark_trades(
        kills
    )

    trade_total = (
        int(
            kills["trade"].sum()
        )
        if not kills.empty
        else 0
    )

    print(
        f"Trade kills detectadas: "
        f"{trade_total}"
    )

    # ============================================================
    # DAMAGE
    # ============================================================

    print()
    print(
        "Lendo dano por adversário..."
    )

    damage = parse_damage(
        parser,
        official,
        round_rosters,
    )

    print(
        f"Eventos de dano válidos: "
        f"{len(damage)}"
    )

    # ============================================================
    # AGREGAÇÃO
    # ============================================================

    print()
    print(
        "Agregando duelos..."
    )

    duels = aggregate_duels(
        kills,
        damage,
    )

    # ============================================================
    # TABELA
    # ============================================================

    print()
    print(
        "=" * 100
    )
    print(
        "DUELOS"
    )
    print(
        "=" * 100
    )

    if duels.empty:

        print(
            "Nenhum duelo encontrado."
        )

    else:

        print(
            duels.to_string(
                index=False
            )
        )

    # ============================================================
    # VALIDAÇÃO
    # ============================================================

    validate_duels(
        duels
    )

    # ============================================================
    # RESUMO
    # ============================================================

    print_player_summary(
        duels
    )

    # ============================================================
    # EXPORTAÇÕES
    # ============================================================

    first_kills.to_csv(
        "entry_rounds.csv",
        index=False,
    )

    kills.to_csv(
        "duels_kills_raw.csv",
        index=False,
    )

    damage.to_csv(
        "duels_damage_raw.csv",
        index=False,
    )

    duels.to_csv(
        "data_duels.csv",
        index=False,
    )

    # ============================================================
    # FINAL
    # ============================================================

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
        "entry_rounds.csv"
    )

    print(
        "duels_kills_raw.csv"
    )

    print(
        "duels_damage_raw.csv"
    )

    print(
        "data_duels.csv"
    )

    print()
    print(
        "Duels parser executado com sucesso."
    )


if __name__ == "__main__":
    main()