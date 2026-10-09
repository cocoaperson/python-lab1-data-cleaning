import io
import json
import os
import sqlite3
import time

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

from src.config import PROCESSED, RESULTS, ROOT
from src.measure import measure

META = [
    "type",
    "language",
    "license",
    "rights_holder",
    "access_rights",
    "dataset_id",
    "institution_code",
    "dataset_name",
    "owner_institution_code",
    "basis_of_record",
    "information_withheld",
    "sampling_protocol",
    "geodetic_datum",
    "georeference_sources",
    "georeference_verification_status",
]


def tables(df):
    assert df.id.astype("str").eq(df.occurrence_id.astype("str")).all()
    dataset = df[META].drop_duplicates().reset_index(drop=True)
    assert len(dataset) == 1
    dataset.insert(0, "dataset_pk", 1)
    species = (
        df[["scientific_name", "vernacular_name", "kingdom", "taxon_rank"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    assert species.scientific_name.is_unique
    species.insert(0, "species_pk", range(1, len(species) + 1))
    bird = df[
        ["organism_id", "organism_name", "sex", "life_stage", "scientific_name"]
    ].drop_duplicates()
    assert bird.organism_id.is_unique
    bird = bird.merge(
        species[["scientific_name", "species_pk"]], on="scientific_name", validate="m:1"
    ).drop(columns="scientific_name")
    prop = df[["organism_id", "dynamic_properties"]].drop_duplicates().reset_index(drop=True)
    prop.insert(0, "deployment_pk", range(1, len(prop) + 1))
    parsed = prop.dynamic_properties.map(json.loads)
    for obj in parsed:
        assert set(obj) == {"device_info_serial", "catch_location", "tracking_started_at"}
    deployment = prop[["deployment_pk", "organism_id"]].copy()
    deployment["device_serial"] = parsed.map(lambda x: x["device_info_serial"])
    deployment["catch_location"] = parsed.map(lambda x: x["catch_location"])
    deployment["tracking_start"] = parsed.map(lambda x: x["tracking_started_at"])
    lookup = prop.set_index("dynamic_properties").deployment_pk
    assert lookup.index.is_unique
    obs = df[
        [
            "id",
            "event_date",
            "minimum_elevation_in_meters",
            "minimum_distance_above_surface_in_meters",
            "decimal_latitude",
            "decimal_longitude",
            "coordinate_uncertainty_in_meters",
        ]
    ].copy()
    obs.columns = [
        "observation_id",
        "event_date",
        "elevation_m",
        "height_m",
        "latitude",
        "longitude",
        "uncertainty_m",
    ]
    obs["event_date"] = obs.event_date.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    obs["dataset_pk"] = 1
    obs["deployment_pk"] = df.dynamic_properties.map(lookup).astype("int32")
    effort = {value: json.loads(value) for value in df.sampling_effort.unique()}
    assert all(set(v) == {"seconds_since_last_occurrence"} for v in effort.values())
    obs["seconds_since_previous"] = df.seconds_since_previous
    return {
        "datasets": dataset,
        "species": species,
        "birds": bird,
        "deployments": deployment,
        "observations": obs,
    }


def schema(engine):
    real = "DOUBLE PRECISION" if engine == "postgres" else "REAL"
    date = "TIMESTAMPTZ" if engine == "postgres" else "TEXT"
    meta = ",\n".join(c + " TEXT NOT NULL" for c in META)
    return f"""CREATE TABLE datasets (dataset_pk INTEGER PRIMARY KEY, {meta}, UNIQUE(dataset_id));
CREATE TABLE species (species_pk INTEGER PRIMARY KEY, scientific_name VARCHAR(128) NOT NULL UNIQUE,
vernacular_name VARCHAR(128) NOT NULL, kingdom VARCHAR(64) NOT NULL, taxon_rank VARCHAR(64) NOT NULL);
CREATE TABLE birds (organism_id VARCHAR(64) PRIMARY KEY, organism_name TEXT,
sex VARCHAR(16), life_stage VARCHAR(32), species_pk INTEGER NOT NULL REFERENCES species(species_pk));
CREATE TABLE deployments (deployment_pk INTEGER PRIMARY KEY,
organism_id VARCHAR(64) NOT NULL REFERENCES birds(organism_id), device_serial INTEGER NOT NULL,
catch_location TEXT NOT NULL, tracking_start DATE NOT NULL);
CREATE TABLE observations (observation_id VARCHAR(64) PRIMARY KEY, event_date {date} NOT NULL,
elevation_m INTEGER, height_m {real}, latitude {real} NOT NULL CHECK(latitude BETWEEN -90 AND 90),
longitude {real} NOT NULL CHECK(longitude BETWEEN -180 AND 180), uncertainty_m INTEGER CHECK(uncertainty_m>=0),
dataset_pk INTEGER NOT NULL REFERENCES datasets(dataset_pk),
deployment_pk INTEGER NOT NULL REFERENCES deployments(deployment_pk), seconds_since_previous INTEGER);
"""


AGG = """SELECT s.scientific_name, COUNT(*), AVG(o.height_m)
FROM observations o JOIN deployments d ON d.deployment_pk=o.deployment_pk
JOIN birds b ON b.organism_id=d.organism_id JOIN species s ON s.species_pk=b.species_pk
GROUP BY s.scientific_name ORDER BY s.scientific_name"""
RANGE = "SELECT COUNT(*) FROM observations WHERE event_date >= '2014-01-01T00:00:00Z' AND event_date < '2014-01-02T00:00:00Z'"


def fetch(connection, query):
    cursor = connection.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()
    return rows


def load_batches(connection, frames, engine):
    started = time.perf_counter()
    cursor = connection.cursor()
    for name, frame in frames.items():
        columns = ",".join(frame.columns)
        for start in range(0, len(frame), 10000):
            part = frame.iloc[start : start + 10000].astype(object)
            part = part.where(pd.notna(part), None)
            rows = list(part.itertuples(index=False, name=None))
            if engine == "sqlite":
                placeholders = ",".join(["?"] * len(frame.columns))
                cursor.executemany(f"INSERT INTO {name} ({columns}) VALUES ({placeholders})", rows)
            else:
                execute_values(
                    cursor, f"INSERT INTO {name} ({columns}) VALUES %s", rows, page_size=10000
                )
    connection.commit()
    cursor.close()
    return time.perf_counter() - started


def main():
    load_dotenv(ROOT / ".env")
    df = pd.read_parquet(PROCESSED / "clean.parquet")
    frames = tables(df)
    del df
    for engine in ["sqlite", "postgres"]:
        (ROOT / f"sql/schema_{engine}.sql").write_text(schema(engine), encoding="utf-8")
    (ROOT / "sql/control.sql").write_text(
        "SELECT COUNT(*) FROM observations;\n" + AGG + ";\n" + RANGE + ";\n", encoding="utf-8"
    )
    sqlite_path = PROCESSED / "dataset.db"
    sq = sqlite3.connect(sqlite_path)
    sq.execute("PRAGMA foreign_keys=ON")
    for name in reversed(frames):
        sq.execute(f"DROP TABLE IF EXISTS {name}")
    sq.executescript(schema("sqlite"))
    result = {"tables": {k: len(v) for k, v in frames.items()}}
    result["sqlite"] = {
        "insert_seconds": load_batches(sq, frames, "sqlite"),
        "version": sqlite3.sqlite_version,
    }
    pg = psycopg2.connect(
        host=os.environ["PG_HOST"],
        port=os.environ["PG_PORT"],
        dbname=os.environ["PG_DB"],
        user=os.environ["PG_USER"],
        password=os.environ["PG_PASSWORD"],
        options="-c timezone=UTC",
    )
    with pg.cursor() as cursor:
        for name in reversed(frames):
            cursor.execute(f"DROP TABLE IF EXISTS {name} CASCADE")
        cursor.execute(schema("postgres"))
    pg.commit()
    result["postgres"] = {
        "insert_seconds": load_batches(pg, frames, "postgres"),
        "version": fetch(pg, "SHOW server_version")[0][0],
    }
    print("Batch loads completed", flush=True)
    with pg.cursor() as cursor:
        cursor.execute("TRUNCATE observations, deployments, birds, species, datasets CASCADE")
    pg.commit()
    started = time.perf_counter()
    with pg.cursor() as cursor:
        for name, frame in frames.items():
            for start in range(0, len(frame), 100000):
                buffer = io.StringIO()
                frame.iloc[start : start + 100000].to_csv(
                    buffer, index=False, header=False, na_rep="\\N"
                )
                buffer.seek(0)
                cursor.copy_expert(
                    f"COPY {name} ({','.join(frame.columns)}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')",
                    buffer,
                )
    pg.commit()
    result["postgres"]["copy_seconds"] = time.perf_counter() - started
    for label, connection in [("sqlite", sq), ("postgres", pg)]:
        r = result[label]
        cursor = connection.cursor()
        cursor.execute("ANALYZE")
        connection.commit()
        cursor.close()
        r["count"] = fetch(connection, "SELECT COUNT(*) FROM observations")[0][0]
        r["aggregate_result"] = fetch(connection, AGG)
        r["date_result"] = fetch(connection, RANGE)[0][0]
        r["aggregate"] = measure(lambda connection=connection: fetch(connection, AGG))
        r["date_before"] = measure(lambda connection=connection: fetch(connection, RANGE))
        cursor = connection.cursor()
        cursor.execute("CREATE INDEX idx_observations_date ON observations(event_date)")
        cursor.execute("CREATE INDEX idx_observations_deployment ON observations(deployment_pk)")
        connection.commit()
        r["date_after"] = measure(lambda connection=connection: fetch(connection, RANGE))
        explain = "EXPLAIN QUERY PLAN " if label == "sqlite" else "EXPLAIN "
        r["indexed_plan"] = fetch(connection, explain + RANGE)
        if label == "sqlite":
            r["storage_mb"] = sqlite_path.stat().st_size / 1e6
            assert not fetch(connection, "PRAGMA foreign_key_check")
        else:
            r["storage_mb"] = (
                fetch(connection, "SELECT pg_database_size(current_database())")[0][0] / 1e6
            )
    assert result["sqlite"]["count"] == result["postgres"]["count"] == len(frames["observations"])
    assert result["sqlite"]["date_result"] == result["postgres"]["date_result"]
    for a, b in zip(result["sqlite"]["aggregate_result"], result["postgres"]["aggregate_result"]):
        assert a[:2] == b[:2] and abs(a[2] - b[2]) < 1e-8
    sq.close()
    pg.close()
    (RESULTS / "database.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
