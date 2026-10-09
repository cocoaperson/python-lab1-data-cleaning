import pandas as pd

from src.config import INTERIM
from src.database import main as load_databases
from src.pipeline import run
from src.radar_join import run as join_radar


def main():
    run()
    join_radar()
    df = pd.read_parquet(INTERIM / "source.parquet")
    df.to_pickle(INTERIM / "source.pkl")
    df.to_feather(INTERIM / "source.feather")
    df.to_csv(INTERIM / "bench.csv", index=False)
    del df
    load_databases()


if __name__ == "__main__":
    main()
