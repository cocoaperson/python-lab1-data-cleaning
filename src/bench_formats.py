import json

import pandas as pd

from src.config import INPUT, INTERIM, RESULTS
from src.measure import measure


def main():
    RESULTS.mkdir(exist_ok=True)
    raw = pd.read_parquet(INTERIM / "source.parquet")
    rows = []
    formats = [
        (
            "CSV",
            INTERIM / "bench.csv",
            lambda p: raw.to_csv(p, index=False),
            lambda p: pd.read_csv(p, float_precision="round_trip"),
        ),
        ("Pickle", INTERIM / "source.pkl", lambda p: raw.to_pickle(p), pd.read_pickle),
        ("Feather", INTERIM / "source.feather", lambda p: raw.to_feather(p), pd.read_feather),
        (
            "Parquet snappy",
            INTERIM / "source.parquet",
            lambda p: raw.to_parquet(p, compression="snappy"),
            pd.read_parquet,
        ),
    ]
    for name, path, writer, reader in formats:
        write = measure(lambda writer=writer, path=path: writer(path))
        read = measure(lambda reader=reader, path=path: reader(path))
        restored = reader(path)
        pd.testing.assert_frame_equal(raw, restored, check_dtype=False)
        del restored
        size = path.stat().st_size
        row = {
            "format": name,
            "mb": size / 1e6,
            "write": write,
            "read": read,
            "ratio_to_csv": size / INPUT.stat().st_size,
            "equal": True,
        }
        rows.append(row)
        print(name, round(write["seconds"], 3), round(read["seconds"], 3), flush=True)
    three = ["eventDate", "scientificName", "decimalLatitude"]
    partial = measure(lambda: pd.read_parquet(INTERIM / "source.parquet", columns=three))
    pd.testing.assert_frame_equal(
        raw[three], pd.read_parquet(INTERIM / "source.parquet", columns=three)
    )
    rows.append(
        {
            "format": "Parquet 3 columns",
            "mb": rows[-1]["mb"],
            "write": None,
            "read": partial,
            "ratio_to_csv": rows[-1]["ratio_to_csv"],
            "equal": True,
        }
    )
    (RESULTS / "formats.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    typed = pd.read_parquet(INTERIM / "source_typed.parquet")
    optimization = []
    for label, df, path in [
        ("before", raw, INTERIM / "source.parquet"),
        ("after", typed, INTERIM / "source_typed.parquet"),
    ]:
        row = {
            "state": label,
            "disk_mb": path.stat().st_size / 1e6,
            "memory_mb": int(df.memory_usage(deep=True).sum()) / 1e6,
            "categories": len(df.select_dtypes("category").columns),
            "read": measure(lambda path=path: pd.read_parquet(path)),
            "group": measure(
                lambda df=df: df.groupby("organismID", observed=True)[
                    "minimumDistanceAboveSurfaceInMeters"
                ].median()
            ),
        }
        optimization.append(row)
    pd.testing.assert_series_equal(
        raw.groupby("organismID")["minimumDistanceAboveSurfaceInMeters"].median().sort_index(),
        typed.groupby("organismID", observed=True)["minimumDistanceAboveSurfaceInMeters"]
        .median()
        .set_axis(typed.groupby("organismID", observed=True).size().index.astype("str"))
        .sort_index(),
        check_index_type=False,
    )
    (RESULTS / "optimization.json").write_text(json.dumps(optimization, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
