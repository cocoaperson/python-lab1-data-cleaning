import argparse
import json
import subprocess
import sys

import pandas as pd
import polars as pl

from src.config import INTERIM, RESULTS
from src.measure import measure

PATH = INTERIM / "source_typed.parquet"
GROUP = "organismID"
VALUE = "minimumDistanceAboveSurfaceInMeters"
KEY = "scientificName"


def operations(library):
    if library == "pandas":
        df = pd.read_parquet(PATH)
        ref = df[[KEY, "vernacularName"]].drop_duplicates()
        group = lambda d: (
            d.groupby(GROUP, observed=True)[VALUE].median().reset_index().astype({GROUP: "string"})
        )
        grouped = group(df)
        return {
            "read": lambda: pd.read_parquet(PATH),
            "filter": lambda: df[df[VALUE] >= 0],
            "group": lambda: group(df),
            "sort": lambda: grouped.sort_values([VALUE, GROUP], ascending=[False, True]),
            "join": lambda: df.drop(columns="vernacularName").merge(
                ref, on=KEY, how="left", validate="m:1"
            ),
            "chain": lambda: group(df[df[VALUE] >= 0]).sort_values(
                [VALUE, GROUP], ascending=[False, True]
            ),
        }
    df = pl.read_parquet(PATH)
    ref = df.select(KEY, "vernacularName").unique()
    grouped = (
        df.group_by(GROUP).agg(pl.col(VALUE).median()).with_columns(pl.col(GROUP).cast(pl.String))
    )
    return {
        "read": lambda: pl.read_parquet(PATH),
        "filter": lambda: df.filter(pl.col(VALUE) >= 0),
        "group": lambda: (
            df.group_by(GROUP)
            .agg(pl.col(VALUE).median())
            .with_columns(pl.col(GROUP).cast(pl.String))
        ),
        "group_lazy": lambda: (
            df.lazy()
            .group_by(GROUP)
            .agg(pl.col(VALUE).median())
            .with_columns(pl.col(GROUP).cast(pl.String))
            .collect()
        ),
        "sort": lambda: grouped.sort([VALUE, GROUP], descending=[True, False]),
        "join": lambda: df.drop("vernacularName").join(
            ref, on=KEY, how="left", validate="m:1", maintain_order="left"
        ),
        "chain": lambda: (
            df.lazy()
            .filter(pl.col(VALUE) >= 0)
            .group_by(GROUP)
            .agg(pl.col(VALUE).median())
            .with_columns(pl.col(GROUP).cast(pl.String))
            .sort([VALUE, GROUP], descending=[True, False])
            .collect()
        ),
    }


def verify():
    a, b = operations("pandas"), operations("polars")
    for key in a:
        left, right = a[key](), b[key]().to_pandas()
        if key in ["group", "sort", "chain"]:
            left = left.sort_values(GROUP).reset_index(drop=True)
            right = right.sort_values(GROUP).reset_index(drop=True)
        else:
            left, right = left.reset_index(drop=True), right.reset_index(drop=True)
        right = right[left.columns]
        for col in left:
            if isinstance(left[col].dtype, pd.CategoricalDtype):
                left[col], right[col] = left[col].astype("string"), right[col].astype("string")
        pd.testing.assert_frame_equal(left, right, check_dtype=False, check_categorical=False)
    print("All six operations return equal results", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--library")
    parser.add_argument("--operation")
    args = parser.parse_args()
    if args.library:
        result = measure(operations(args.library)[args.operation])
        print(json.dumps({"library": args.library, "operation": args.operation, **result}))
        return
    results = []
    for library in ["pandas", "polars"]:
        names = ["read", "filter", "group", "sort", "join", "chain"]
        if library == "polars":
            names.append("group_lazy")
        for name in names:
            process = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    "-m",
                    "src.bench_libraries",
                    "--library",
                    library,
                    "--operation",
                    name,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            results.append(json.loads(process.stdout))
            print(library, name, results[-1]["seconds"], flush=True)
    verify()
    (RESULTS / "libraries.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
