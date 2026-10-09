import json
import logging
import re

import pandas as pd

from src.config import CUTOFF, SCHEMA


def snake(name):
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"([A-Z])([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def assign_types(df):
    """Типы определены предметной областью; ошибки разбора остаются пропусками."""
    df = df.copy()
    failures = 0
    for original, dtype in SCHEMA.items():
        col = original if original in df else snake(original)
        old = df[col].notna()
        if original == "eventDate":
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)
        elif dtype in ("float64", "Int32"):
            values = pd.to_numeric(df[col], errors="coerce")
            if dtype == "Int32":
                valid = values.between(-2147483648, 2147483647) & (values % 1 == 0)
                values = values.where(valid)
            df[col] = values.astype(dtype)
        else:
            df[col] = df[col].astype(dtype)
        failures += int((old & df[col].isna()).sum())
    return df, {"changed": failures, "parse_failures": failures}


def names(df):
    return df.rename(columns=snake), {"changed": 0, "note": "Переименованы столбцы"}


def hidden_missing(df):
    changed = pd.Series(False, index=df.index)
    for col in df.select_dtypes(include=["str", "string", "object", "category"]):
        values = df[col].astype("string[pyarrow]")
        mask = values.str.strip().str.lower().isin(["", "-", "нет данных", "null", "n/a"])
        changed |= mask
        if mask.any():
            df[col] = values.mask(mask)
    # Нулевая высота и отрицательная высота GPS не являются строковыми заменителями.
    return df, {"changed": int(changed.sum())}


def missing(df):
    required = ["id", "organism_id", "event_date", "decimal_latitude", "decimal_longitude"]
    valid = df[required].notna().all(axis=1)
    df = df.loc[valid].copy()
    # Пол и высота не восстанавливаются догадкой: сохраняем NA.
    height = df["minimum_distance_above_surface_in_meters"].isna()
    sex = df["sex"].isna()
    old_height = df.get("height_missing", pd.Series(False, index=df.index))
    old_sex = df.get("sex_missing", pd.Series(False, index=df.index))
    changed = int((height.ne(old_height) | sex.ne(old_sex)).sum())
    df["height_missing"], df["sex_missing"] = height, sex
    return df, {"changed": changed}


def duplicates(df):
    full = int(df.duplicated().sum())
    df = df.drop_duplicates()
    keys = int(df.id.duplicated().sum())
    if keys:
        # Дата обновления отсутствует; выбираем позднее событие, при равенстве последнюю строку.
        df = df.sort_values("event_date", kind="stable").drop_duplicates("id", keep="last")
    return df, {"changed": 0, "full_duplicates": full, "key_duplicates": keys}


def categories(df):
    changed = pd.Series(False, index=df.index)
    for col in [snake(c) for c, t in SCHEMA.items() if t == "category"]:
        old = df[col].astype("string[pyarrow]")
        new = old.str.strip()
        if col in ["sex", "life_stage", "taxon_rank"]:
            new = new.str.lower().replace({"m": "male", "f": "female"})
        changed |= old.fillna("").ne(new.fillna(""))
        df[col] = new.astype("str").astype("category")
    # Оба вида значимы; редкие биологические категории не объединяем.
    return df, {"changed": int(changed.sum())}


def text_field(df):
    # Роль свободного TEXT в этом наборе выполняет имя птицы.
    col = "organism_name"
    old = df[col].astype("string[pyarrow]")
    new = old.str.replace(r"<[^>]*>", "", regex=True)
    new = new.str.replace(r"\s+", " ", regex=True).str.strip()
    new = new.mask(new.str.lower().isin(["", "unknown", "нет данных", "-"]))
    df[col] = new
    return df, {"changed": int(old.fillna("").ne(new.fillna("")).sum())}


def constraints(df):
    bad = ~df.decimal_latitude.between(-90, 90)
    bad |= ~df.decimal_longitude.between(-180, 180)
    bad |= df.event_date > pd.Timestamp(CUTOFF)
    bad |= df.coordinate_uncertainty_in_meters.lt(0).fillna(False)
    # Все расстояния уже в метрах, координаты WGS84 в градусах; пересчёт не нужен.
    negative = df.minimum_distance_above_surface_in_meters.lt(0).fillna(False)
    previous = df.get("height_negative", pd.Series(False, index=df.index))
    changed = int(negative.ne(previous).sum())
    df["height_negative"] = negative
    values = {
        text: json.loads(text)["seconds_since_last_occurrence"]
        for text in df.sampling_effort.unique()
    }
    seconds = pd.to_numeric(df.sampling_effort.map(values), errors="coerce")
    seconds = seconds.where(seconds.between(0, 2147483647) & (seconds % 1 == 0))
    old_seconds = df.get("seconds_since_previous")
    if old_seconds is None:
        changed = int((negative | seconds.isna()).sum())
    df["seconds_since_previous"] = seconds.astype("Int32")
    return df.loc[~bad].copy(), {
        "changed": changed,
        "invalid_domain": int(bad.sum()),
        "negative_height": int(negative.sum()),
        "missing_interval": int(seconds.isna().sum()),
    }


def outliers(df):
    x = df.minimum_distance_above_surface_in_meters
    q1, q3 = x.quantile([0.25, 0.75])
    lo, hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    median = x.median()
    mad = (x - median).abs().median()
    iqr = ((x < lo) | (x > hi)).fillna(False)
    robust = ((0.67448975 * (x - median).abs() / mad) > 3.5).fillna(False)
    if mad == 0:
        robust = x.ne(median) & x.notna()
    old_iqr = df.get("height_iqr_flag", pd.Series(False, index=df.index))
    old_mad = df.get("height_mad_flag", pd.Series(False, index=df.index))
    changed = int((iqr.ne(old_iqr) | robust.ne(old_mad)).sum())
    df["height_iqr_flag"], df["height_mad_flag"] = iqr, robust
    return df, {
        "changed": changed,
        "iqr_low": float(lo),
        "iqr_high": float(hi),
        "median": float(median),
        "mad": float(mad),
        "iqr": int(iqr.sum()),
        "mad_count": int(robust.sum()),
        "both": int((iqr & robust).sum()),
    }


STEPS = [
    names,
    assign_types,
    hidden_missing,
    missing,
    duplicates,
    categories,
    text_field,
    constraints,
    outliers,
]


def apply_step(df, function):
    before = len(df)
    df, info = function(df)
    stats = {
        "stage": function.__name__,
        "processed": before,
        "after": len(df),
        "deleted": before - len(df),
        **info,
    }
    logging.getLogger(__name__).info("%s", stats)
    return df.reset_index(drop=True), stats
