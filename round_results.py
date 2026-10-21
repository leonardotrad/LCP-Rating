from pathlib import Path

import pandas as pd
from demoparser2 import DemoParser


DEMO_FOLDER = Path("demos")
ROUNDS_FILE = Path("data_rounds.csv")
OUTPUT_FILE = Path("round_results.csv")


def find_demo():
    demos = list(DEMO_FOLDER.glob("*.dem"))

    if not demos:
        raise FileNotFoundError(
            "Nenhuma demo encontrada na pasta 'demos'."
        )

    if len(demos) > 1:
        print("Foram encontradas várias demos:")
        for demo in demos:
            print(f" - {demo}")

        raise RuntimeError(
            "Deixe apenas uma demo na pasta 'demos'."
        )

    return demos[0]


def load_round_classification():
    if not ROUNDS_FILE.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {ROUNDS_FILE}"
        )

    df = pd.read_csv(ROUNDS_FILE)

    required = {
        "event_index",
        "tick_start",
        "tick_end",
        "total_rounds_played",
        "half",
        "is_warmup_period",
        "round_type",
        "kill_events",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"data_rounds.csv não possui as colunas esperadas: {sorted(missing)}"
        )

    return df


def load_round_end(demo_path):
    parser = DemoParser(str(demo_path))

    print("Lendo evento round_end...")
    round_end = parser.parse_event("round_end")

    if not isinstance(round_end, pd.DataFrame):
        raise TypeError(
            f"round_end retornou {type(round_end).__name__}, "
            "mas era esperado um DataFrame."
        )

    if round_end.empty:
        raise RuntimeError(
            "Nenhum evento round_end foi encontrado na demo."
        )

    required = {
        "round",
        "tick",
        "winner",
        "reason",
    }

    missing = required - set(round_end.columns)

    if missing:
        raise ValueError(
            f"round_end não possui as colunas esperadas: {sorted(missing)}"
        )

    return round_end.copy()


def normalize_round_end(round_end):
    df = round_end.copy()

    # Remove o registro round 0, que representa o estado inicial.
    df = df[df["round"] > 0].copy()

    # Garante tipos numéricos consistentes.
    df["round"] = pd.to_numeric(
        df["round"],
        errors="coerce"
    )

    df["tick"] = pd.to_numeric(
        df["tick"],
        errors="coerce"
    )

    # Mantemos apenas resultados com vencedor conhecido.
    df = df[df["winner"].notna()].copy()

    df["winner"] = (
        df["winner"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["reason"] = (
        df["reason"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    df = df.sort_values(
        ["round", "tick"]
    ).reset_index(drop=True)

    return df


def build_round_results(rounds, round_end):
    """
    Cruza a classificação dos rounds com o resultado oficial
    fornecido pelo evento round_end.

    A correspondência é feita pelo número lógico do round:
        total_rounds_played + 1
    para o round oficial seguinte.

    Como o arquivo data_rounds.csv também contém eventos de
    transição/warmup, filtramos apenas os rounds oficiais.
    """

    official_types = {
        "PISTOL",
        "NORMAL",
        "OVERTIME",
    }

    classified = rounds[
        rounds["round_type"].isin(official_types)
    ].copy()

    if classified.empty:
        raise RuntimeError(
            "Nenhum round oficial encontrado em data_rounds.csv."
        )

    # O campo total_rounds_played representa a quantidade
    # de rounds oficiais concluídos antes daquele evento.
    #
    # Assim:
    #   0 -> round 1
    #   1 -> round 2
    #   2 -> round 3
    classified["round"] = (
        pd.to_numeric(
            classified["total_rounds_played"],
            errors="coerce"
        )
        + 1
    )

    classified["round"] = (
        classified["round"]
        .astype("Int64")
    )

    # O vencedor e casado pelo TICK do round_end, que e exatamente o ultimo
    # tick do round (tick_end - 1, borda exclusiva). Antes casava pelo campo
    # "round" do evento, que nao zera depois de restart/aquecimento: em 37 das
    # 39 partidas cada round recebia o resultado do round anterior.
    classified["tick_fim"] = (
        pd.to_numeric(classified["tick_end"], errors="coerce") - 1
    ).astype("Int64")

    fins = round_end[["tick", "winner", "reason"]].copy()
    fins["tick_fim"] = pd.to_numeric(fins["tick"], errors="coerce").astype("Int64")
    fins = fins.drop_duplicates("tick_fim")

    results = classified.merge(
        fins,
        on="tick_fim",
        how="left",
    ).drop(columns=["tick_fim"])

    # Renomeia o tick do round_end para deixar explícito
    # que ele representa o momento do encerramento.
    results = results.rename(
        columns={
            "tick": "tick_end_actual",
        }
    )

    # Verificação de integridade.
    missing_winner = results["winner"].isna()

    if missing_winner.any():
        print()
        print("ATENÇÃO: existem rounds oficiais sem vencedor:")
        print(
            results.loc[
                missing_winner,
                [
                    "round",
                    "event_index",
                    "total_rounds_played",
                    "round_type",
                ]
            ].to_string(index=False)
        )
        print()

    duplicated = results["round"].duplicated(
        keep=False
    )

    if duplicated.any():
        print()
        print("ATENÇÃO: existem rounds duplicados:")
        print(
            results.loc[
                duplicated,
                [
                    "round",
                    "event_index",
                    "round_type",
                ]
            ].to_string(index=False)
        )
        print()

    return results


def validate_results(results):
    print()
    print("=" * 80)
    print("VALIDAÇÃO")
    print("=" * 80)
    print()

    total = len(results)
    with_winner = results["winner"].notna().sum()
    without_winner = results["winner"].isna().sum()

    print(f"Rounds oficiais encontrados: {total}")
    print(f"Rounds com vencedor:        {with_winner}")
    print(f"Rounds sem vencedor:        {without_winner}")
    print()

    if "winner" in results.columns:
        print("Distribuição de vencedores:")

        print(
            results["winner"]
            .fillna("SEM_RESULTADO")
            .value_counts()
            .to_string()
        )

        print()

    if "reason" in results.columns:
        print("Distribuição dos motivos:")

        print(
            results["reason"]
            .fillna("SEM_RESULTADO")
            .value_counts()
            .to_string()
        )

        print()

    # Verifica se o tick final oficial faz sentido.
    valid_ticks = results[
        results["tick_end_actual"].notna()
    ].copy()

    if not valid_ticks.empty:
        inconsistent = valid_ticks[
            valid_ticks["tick_end_actual"]
            < valid_ticks["tick_start"]
        ]

        print(
            "Rounds com tick final anterior ao início:",
            len(inconsistent),
        )

        if not inconsistent.empty:
            print(
                inconsistent[
                    [
                        "round",
                        "tick_start",
                        "tick_end_actual",
                    ]
                ].to_string(index=False)
            )

        print()


def main():
    print()
    print("=" * 80)
    print("LCP - ROUND RESULTS")
    print("=" * 80)
    print()

    demo_path = find_demo()

    print("Demo:")
    print(demo_path)
    print()

    rounds = load_round_classification()

    print(
        f"data_rounds.csv carregado: {len(rounds)} registros"
    )
    print()

    round_end = load_round_end(demo_path)

    print(
        f"round_end carregado: {len(round_end)} registros"
    )
    print()

    round_end = normalize_round_end(round_end)

    print(
        f"round_end após normalização: {len(round_end)} rounds"
    )
    print()

    results = build_round_results(
        rounds,
        round_end,
    )

    validate_results(results)

    # Ordenação final.
    columns = [
        "round",
        "event_index",
        "tick_start",
        "tick_end",
        "tick_end_actual",
        "total_rounds_played",
        "half",
        "is_warmup_period",
        "round_type",
        "kill_events",
        "winner",
        "reason",
    ]

    columns = [
        column
        for column in columns
        if column in results.columns
    ]

    results = results[columns].sort_values(
        "round"
    ).reset_index(drop=True)

    results.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print("=" * 80)
    print("PRIMEIROS 10 ROUNDS")
    print("=" * 80)
    print()

    print(
        results.head(10).to_string(index=False)
    )

    print()

    print("=" * 80)
    print("ARQUIVO GERADO")
    print("=" * 80)
    print()

    print(OUTPUT_FILE)

    print()
    print("=" * 80)
    print("ROUND RESULTS CONCLUÍDO")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()