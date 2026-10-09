import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from src.cleaning import STEPS, apply_step, assign_types
from src.config import INPUT, INTERIM, PROCESSED, ROOT, SAMPLE_SIZE, SCHEMA


def read_input(path, limit=None, typed=False):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Исходный файл не найден: {path}")
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path).head(limit) if limit else pd.read_parquet(path)
    if path.suffix.lower() != ".csv":
        raise ValueError("Поддерживаются только CSV и Parquet")
    # Числа пока читаются строками: некорректные значения обрабатывает assign_types.
    dtypes = None
    if typed:
        dtypes = {
            c: (t if t in ["category", "string[pyarrow]"] else "string[pyarrow]")
            for c, t in SCHEMA.items()
        }
    df = pd.read_csv(
        path, encoding="utf-8", sep=",", nrows=limit, dtype=dtypes, on_bad_lines="error"
    )
    if not set(SCHEMA).issubset(df.columns):
        raise ValueError("CSV не содержит обязательные столбцы набора INBO")
    return df


def run(input_path=INPUT, output=PROCESSED / "clean.parquet", mode="full"):
    output = Path(output)
    if output.resolve() == Path(input_path).resolve() or "raw" in output.parts:
        raise ValueError("Запись поверх исходных данных запрещена")
    INTERIM.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    limit = SAMPLE_SIZE if mode == "debug" else None
    if Path(input_path).suffix.lower() == ".csv":
        sample = pd.read_csv(input_path, nrows=SAMPLE_SIZE, encoding="utf-8")
        sample.to_csv(INTERIM / "sample.csv", index=False, encoding="utf-8")
    raw = read_input(input_path, limit)
    raw.to_parquet(INTERIM / "source.parquet", compression="snappy")
    typed, type_info = assign_types(read_input(input_path, limit, typed=True))
    typed.to_parquet(INTERIM / "source_typed.parquet", compression="snappy")
    del raw
    audit = []
    df = typed
    for step in STEPS:
        df, stats = apply_step(df, step)
        audit.append(stats)
    df.to_parquet(output, compression="snappy", index=False)
    audit_path = output.with_suffix(".audit.json")
    audit_path.write_text(
        json.dumps(
            {
                "mode": mode,
                "initial_types": type_info,
                "rows": len(df),
                "columns": len(df.columns),
                "stages": audit,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return df


def main():
    parser = argparse.ArgumentParser(description="Очистка GPS-наблюдений INBO")
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--output", type=Path, default=PROCESSED / "clean.parquet")
    parser.add_argument("--mode", choices=["full", "debug"], default="full")
    args = parser.parse_args()
    (ROOT / "logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(ROOT / "logs/pipeline.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    try:
        df = run(args.input, args.output, args.mode)
    except (OSError, ValueError, pd.errors.ParserError) as error:
        logging.getLogger(__name__).error("Обработка остановлена: %s", error)
        raise SystemExit(1)
    logging.getLogger(__name__).info("Готово: %d строк, %d столбцов", *df.shape)


if __name__ == "__main__":
    main()
