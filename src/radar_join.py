import json

import pandas as pd

from src.config import PROCESSED, RAW, RESULTS


def run():
    tracks = pd.read_csv(RAW / "radar_track.csv", sep=";", dtype="string")
    sites = pd.read_csv(RAW / "radar_site.csv", sep=";", dtype="string")
    species = pd.read_csv(RAW / "radar_species.csv", sep=";", dtype="string")
    # Повторяющиеся коды площадок описывают разные сезоны. Для координат нужен
    # справочник площадок, а не таблица сезонов: берём только постоянные поля.
    static = sites[
        ["SiteCode", "Name", "Country", "Latitude", "Longitude", "Altitude"]
    ].drop_duplicates()
    assert not static.SiteCode.duplicated().any(), "Противоречивые сведения о площадке"
    assert not species.SpeciesCode.duplicated().any()
    bad_coords = {}
    for col in ["Latitude", "Longitude", "Altitude"]:
        old = static[col]
        parsed = pd.to_numeric(old, errors="coerce")
        bad_coords[col] = int((old.notna() & parsed.isna()).sum())
        static[col] = parsed
    result = tracks.merge(
        static,
        how="left",
        left_on="Code",
        right_on="SiteCode",
        validate="m:1",
        indicator="site_join",
    )
    result = result.merge(
        species, how="left", on="SpeciesCode", validate="m:1", indicator="species_join"
    )
    assert len(result) == len(tracks)
    stats = {
        "tracks_before": len(tracks),
        "site_rows": len(sites),
        "unique_sites": len(static),
        "species_rows": len(species),
        "after": len(result),
        "unmatched_sites": int(result.site_join.eq("left_only").sum()),
        "unmatched_species": int(result.species_join.eq("left_only").sum()),
        "bad_site_numbers": bad_coords,
        "note": "Повторные SiteCode — сезоны; координаты соединены с уникальными площадками. Не интерпретировать неизвестный SpeciesCode как пропуск всего наблюдения.",
    }
    result.to_parquet(PROCESSED / "radar_joined.parquet", index=False)
    (RESULTS / "radar_join.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stats


if __name__ == "__main__":
    print(run())
