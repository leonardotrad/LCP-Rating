from pathlib import Path

import pandas as pd
from demoparser2 import DemoParser

from lcp_parser import classify_rounds


# ============================================================
# CONFIGURAÇÃO
# ============================================================

DEMO_FOLDER = Path("demos")


# ============================================================
# LOCALIZAR A DEMO
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
# PEGAR EVENTOS DENTRO DO INTERVALO DE UM ROUND
# ============================================================

def get_events_between_ticks(
    events,
    tick_start,
    tick_end=None,
):
    """
    Retorna eventos entre tick_start e tick_end.

    Se tick_end for None/NaN, retorna tudo até o final da demo.
    """

    if events.empty:
        return events.copy()

    if tick_end is None or pd.isna(tick_end):

        return events[
            events["tick"] >= tick_start
        ].copy()

    return events[
        (events["tick"] >= tick_start)
        &
        (events["tick"] < tick_end)
    ].copy()


# ============================================================
# ASSOCIAR DAMAGE AOS ROUNDS
# ============================================================

def assign_rounds_to_damage(
    damage,
    round_classification,
):
    """
    Associa cada evento player_hurt ao round correspondente.

    Mantemos somente:

    PISTOL
    NORMAL
    OVERTIME
    """

    official_types = {
        "PISTOL",
        "NORMAL",
        "OVERTIME",
    }

    records = []

    for _, round_row in round_classification.iterrows():

        round_type = round_row["round_type"]

        if round_type not in official_types:
            continue

        tick_start = int(
            round_row["tick_start"]
        )

        tick_end = round_row["tick_end"]

        round_damage = get_events_between_ticks(
            damage,
            tick_start,
            tick_end,
        )

        if round_damage.empty:
            continue

        for _, event in round_damage.iterrows():

            records.append({

                # ------------------------------------------------
                # ROUND
                # ------------------------------------------------

                "round_event_index":
                    round_row["event_index"],

                "round_number":
                    round_row["total_rounds_played"],

                "round_type":
                    round_type,

                "round_tick_start":
                    round_row["tick_start"],

                "round_tick_end":
                    round_row["tick_end"],

                # ------------------------------------------------
                # EVENTO
                # ------------------------------------------------

                "tick":
                    event.get("tick"),

                # ------------------------------------------------
                # JOGADORES
                # ------------------------------------------------

                "attacker_name":
                    event.get("attacker_name"),

                "attacker_steamid":
                    event.get("attacker_steamid"),

                "victim_name":
                    event.get("user_name"),

                "victim_steamid":
                    event.get("user_steamid"),

                # ------------------------------------------------
                # WEAPON
                # ------------------------------------------------

                "weapon":
                    event.get("weapon"),

                # ------------------------------------------------
                # DAMAGE
                # ------------------------------------------------

                "dmg_health":
                    event.get("dmg_health"),

                "dmg_armor":
                    event.get("dmg_armor"),

                "health_after_hit":
                    event.get("health"),

                # ------------------------------------------------
                # HIT
                # ------------------------------------------------

                "hitgroup":
                    event.get("hitgroup"),

                # ------------------------------------------------
                # WARMUP
                # ------------------------------------------------

                "is_warmup_period":
                    event.get("is_warmup_period"),
            })

    if not records:
        return pd.DataFrame()

    return pd.DataFrame(records)


# ============================================================
# CRIAR RESUMO DE DAMAGE
# ============================================================

def create_damage_summary(
    official_damage,
):
    """
    Soma dano causado por jogador.

    Neste primeiro estágio usamos dmg_health.
    Não somamos dmg_armor ao damage.
    """

    if official_damage.empty:
        return pd.DataFrame()

    damage = official_damage.copy()

    # Garantir números
    damage["dmg_health"] = pd.to_numeric(
        damage["dmg_health"],
        errors="coerce",
    ).fillna(0)

    damage["dmg_armor"] = pd.to_numeric(
        damage["dmg_armor"],
        errors="coerce",
    ).fillna(0)

    # Remover eventos sem atacante
    damage = damage[
        damage["attacker_name"].notna()
    ].copy()

    if damage.empty:
        return pd.DataFrame()

    # --------------------------------------------------------
    # DAMAGE POR JOGADOR
    # --------------------------------------------------------

    summary = (
        damage
        .groupby(
            "attacker_name",
            as_index=False,
        )
        .agg(
            Damage=(
                "dmg_health",
                "sum",
            ),
            ArmorDamage=(
                "dmg_armor",
                "sum",
            ),
            HitEvents=(
                "dmg_health",
                "count",
            ),
        )
    )

    # --------------------------------------------------------
    # ORDENAR
    # --------------------------------------------------------

    summary = summary.sort_values(
        by="Damage",
        ascending=False,
    ).reset_index(drop=True)

    return summary


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 90)
    print("LCP RATING - DAMAGE PARSER")
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
    #
    # Precisamos delas porque o nosso classificador utiliza
    # a primeira fase da demo para detectar a knife round.
    # ========================================================

    print("\nLendo player_death...")

    deaths = parser.parse_event(
        "player_death",
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
    # CLASSIFICAR ROUNDS
    # ========================================================

    print("\nClassificando rounds...")

    round_classification = classify_rounds(
        round_events,
        deaths,
    )


    print("\nResumo dos rounds:")

    print(
        round_classification[
            "round_type"
        ]
        .value_counts()
        .to_string()
    )


    # ========================================================
    # PLAYER_HURT
    # ========================================================

    print("\nLendo player_hurt...")

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
    # ASSOCIAR DAMAGE AOS ROUNDS OFICIAIS
    # ========================================================

    print(
        "\nAssociando dano aos rounds oficiais..."
    )

    official_damage = assign_rounds_to_damage(
        hurt,
        round_classification,
    )


    # ========================================================
    # RESULTADO
    # ========================================================

    print("\n")
    print("=" * 90)
    print("DAMAGE OFICIAL")
    print("=" * 90)

    print(
        "Eventos de dano oficiais:",
        len(official_damage),
    )


    # ========================================================
    # MOSTRAR PRIMEIROS EVENTOS
    # ========================================================

    if not official_damage.empty:

        print("\nPrimeiros 30 eventos:\n")

        print(
            official_damage
            .head(30)
            .to_string(index=False)
        )


    # ========================================================
    # RESUMO POR JOGADOR
    # ========================================================

    damage_summary = create_damage_summary(
        official_damage,
    )


    print("\n")
    print("=" * 90)
    print("DAMAGE POR JOGADOR")
    print("=" * 90)

    if damage_summary.empty:

        print(
            "Nenhum dano oficial encontrado."
        )

    else:

        print(
            damage_summary.to_string(
                index=False
            )
        )


    # ========================================================
    # DAMAGE POR ROUND
    # ========================================================

    if not official_damage.empty:

        damage_per_round = (
            official_damage
            .assign(
                dmg_health=pd.to_numeric(
                    official_damage["dmg_health"],
                    errors="coerce",
                ).fillna(0)
            )
            .groupby(
                [
                    "round_number",
                    "round_type",
                ],
                dropna=False,
            )
            ["dmg_health"]
            .sum()
            .reset_index(
                name="Damage"
            )
        )

        print("\n")
        print("=" * 90)
        print("DAMAGE POR ROUND")
        print("=" * 90)

        print(
            damage_per_round.to_string(
                index=False
            )
        )


    # ========================================================
    # SALVAR EVENTOS BRUTOS TRATADOS
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
    # SALVAR RESUMO
    # ========================================================

    summary_output = Path(
        "damage_summary.csv"
    )

    damage_summary.to_csv(
        summary_output,
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
        damage_output
    )

    print(
        summary_output
    )

    print("\nDamage parser executado com sucesso.")


# ============================================================
# EXECUTAR
# ============================================================

if __name__ == "__main__":
    main()