"""ЛР2: воспроизводимый разведочный анализ очищенных GPS-наблюдений."""

from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
from time import perf_counter

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow

TARGET = "minimum_distance_above_surface_in_meters"
DATE = "event_date"
GROUP = "scientific_name"
RARE_SHARE = 0.01
IQR_FACTOR = 1.5
# Предметное правило задано заранее: отрицательная высота требует проверки.
# Оно не означает, что каждое такое наблюдение ошибочно и должно быть удалено.
DOMAIN_LIMIT = 0.0
COLUMNS = [TARGET, DATE, GROUP, "organism_id", "height_iqr_flag", "height_negative"]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_data(path):
    frame = pd.read_parquet(path, columns=COLUMNS)
    if not pd.api.types.is_numeric_dtype(frame[TARGET]):
        raise TypeError("Целевой признак должен быть числовым")
    if not isinstance(frame[DATE].dtype, pd.DatetimeTZDtype):
        raise TypeError("Ожидается готовый datetime с часовым поясом из ЛР1")
    if frame[DATE].isna().any() or frame[GROUP].isna().any():
        raise ValueError("Для этого анализа дата и вид не должны содержать пропуски")
    return frame


def target_summary(frame):
    x = frame[TARGET]
    q = x.quantile([0.25, 0.5, 0.75])
    return pd.DataFrame(
        [
            {
                "observations": len(x),
                "valid": int(x.count()),
                "missing": int(x.isna().sum()),
                "min_m": x.min(),
                "q1_m": q.loc[0.25],
                "median_m": q.loc[0.5],
                "mean_m": x.mean(),
                "q3_m": q.loc[0.75],
                "max_m": x.max(),
                "skewness": x.skew(),
                "skew_direction": "правосторонняя" if x.skew() > 0 else "левосторонняя",
            }
        ]
    )


def time_summary(frame):
    # UTC уже задан в ЛР1; строковое преобразование дат не выполняется.
    month = frame[DATE].dt.tz_convert("UTC").dt.tz_localize(None).dt.to_period("M")
    calendar = pd.period_range(month.min(), month.max(), freq="M")
    result = (
        frame.groupby(month, observed=True)[TARGET]
        .agg(count="size", valid="count", median_m="median", mean_m="mean")
        .reindex(calendar)
    )
    result[["count", "valid"]] = result[["count", "valid"]].fillna(0).astype("int64")
    result.index.name = "period"
    return result


def group_summary(frame):
    result = frame.groupby(GROUP, observed=True)[TARGET].agg(
        count="size", valid="count", median_m="median", mean_m="mean"
    )
    result["missing"] = result["count"] - result["valid"]
    result["missing_fraction"] = result["missing"] / result["count"]
    result["share"] = result["count"] / len(frame)
    return result.sort_values("count", ascending=False)


def chart_groups(frame, threshold=RARE_SHARE):
    counts = frame[GROUP].value_counts()
    rare = counts[counts / len(frame) < threshold].index.tolist()
    labels = frame[GROUP].astype("object").where(~frame[GROUP].isin(rare), "прочие")
    return labels, rare


def median_pivot(frame, periods):
    month = frame[DATE].dt.tz_convert("UTC").dt.tz_localize(None).dt.to_period("M")
    pivot = frame.assign(_month=month).pivot_table(
        index=GROUP, columns="_month", values=TARGET, aggfunc="median", observed=True
    )
    return pivot.reindex(columns=periods)


def anomaly_rules(values):
    """Маски длины N; пропуски не считаются аномалиями; границы строгие."""
    q1, q3 = values.quantile([0.25, 0.75])
    lower, upper = q1 - IQR_FACTOR * (q3 - q1), q3 + IQR_FACTOR * (q3 - q1)
    iqr = ((values < lower) | (values > upper)).fillna(False)
    negative = (values < DOMAIN_LIMIT).fillna(False)
    overlap = int((iqr & negative).sum())
    table = pd.DataFrame(
        [
            {
                "rule": "1.5 IQR",
                "count": int(iqr.sum()),
                "fraction": float(iqr.mean()),
                "overlap": overlap,
            },
            {
                "rule": "Высота < 0 м",
                "count": int(negative.sum()),
                "fraction": float(negative.mean()),
                "overlap": overlap,
            },
            {
                "rule": "Пересечение",
                "count": overlap,
                "fraction": overlap / len(values),
                "overlap": overlap,
            },
        ]
    )
    return {"iqr": iqr, "negative": negative}, table, (float(lower), float(upper))


def mean_python(values):
    total = 0.0
    for value in values:
        total += float(value)
    return total / len(values)


def mean_numpy(values):
    return float(np.mean(values))


def benchmark(values):
    # Один и тот же float64-массив без 11 пропусков; подготовка не входит в замер.
    array = values.dropna().to_numpy(dtype="float64", copy=True)
    python_value, numpy_value = mean_python(array), mean_numpy(array)
    if not np.isclose(python_value, numpy_value, rtol=1e-12, atol=1e-12):
        raise AssertionError("Результаты двух реализаций различаются")
    mean_python(array)  # Один прогрев каждой реализации, результат не учитывается.
    mean_numpy(array)
    samples = {"python": [], "numpy": []}
    # Чередование порядка уменьшает систематическое влияние очередности.
    for repeat in range(3):
        order = [("python", mean_python), ("numpy", mean_numpy)]
        if repeat % 2:
            order.reverse()
        for name, function in order:
            start = perf_counter()
            function(array)
            samples[name].append(perf_counter() - start)
    py_time, np_time = (float(np.median(samples[key])) for key in ("python", "numpy"))
    return {
        "n": len(array),
        "python_value": python_value,
        "numpy_value": numpy_value,
        "python_seconds": py_time,
        "numpy_seconds": np_time,
        "speedup": py_time / np_time,
        "warmups": 1,
        "repeats": 3,
        "samples_seconds": samples,
        "rtol": 1e-12,
        "atol": 1e-12,
        "versions": {
            "Python": platform.python_version(),
            "NumPy": np.__version__,
            "pandas": pd.__version__,
            "Matplotlib": matplotlib.__version__,
            "PyArrow": pyarrow.__version__,
        },
        "platform": platform.platform(),
        "processor": platform.processor(),
    }


def setup_style():
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.dpi": 120,
            "savefig.dpi": 180,
            "axes.grid": True,
            "grid.alpha": 0.2,
        }
    )


def save_figure(figure, folder, name):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    figure.savefig(folder / name, bbox_inches="tight", facecolor="white")
    return figure


def plot_histogram(frame, folder):
    x = frame[TARGET].dropna()
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
    axes[0].hist(x, bins=100, color="#315b83")
    axes[0].set(title="Полный диапазон", xlabel="Высота, м", ylabel="Наблюдения, шт.")
    axes[1].hist(x, bins=np.arange(-100, 305, 5), color="#315b83")
    axes[1].set(
        title="Увеличение участка от −100 до 300 м", xlabel="Высота, м", ylabel="Наблюдения, шт."
    )
    axes[1].set_xlim(-100, 300)
    fig.suptitle("Распределение высоты GPS-наблюдений")
    return save_figure(fig, folder, "01_histogram.png")


def plot_group_distribution(frame, folder):
    labels, _ = chart_groups(frame)
    names = sorted(labels.unique())
    stats = []
    for name in names:
        values = frame.loc[labels == name, TARGET].dropna()
        q1, med, q3 = values.quantile([0.25, 0.5, 0.75])
        low, high = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
        inside = values.between(low, high)
        stats.append(
            {
                "label": str(name),
                "q1": q1,
                "med": med,
                "q3": q3,
                "whislo": values[inside].min(),
                "whishi": values[inside].max(),
                # Совпадающие высоты рисуются одной точкой; строки не удаляются.
                "fliers": np.unique(values[~inside].to_numpy()),
            }
        )
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
    for ax in axes:
        ax.bxp(
            stats,
            patch_artist=True,
            boxprops={"facecolor": "#aec8df"},
            flierprops={"markersize": 1.8, "alpha": 0.35},
        )
        ax.set(xlabel="Вид птицы", ylabel="Высота, м")
    axes[0].set_title("Полный диапазон")
    axes[1].set(title="Увеличение участка от −50 до 150 м", ylim=(-50, 150))
    fig.suptitle("Распределение высоты по видам")
    return save_figure(fig, folder, "02_groups.png")


def plot_time(series, folder):
    dates = series.index.to_timestamp()
    fig, axes = plt.subplots(2, 1, figsize=(10, 5), sharex=True, layout="constrained")
    axes[0].bar(dates, series["count"], width=24, color="#315b83")
    axes[0].set(ylabel="Наблюдения, шт.", title="Число наблюдений и высота по месяцам")
    axes[1].plot(dates, series["median_m"], "o-", label="Медиана", markersize=3)
    axes[1].plot(dates, series["mean_m"], "s-", label="Среднее", markersize=3, color="#b86726")
    axes[1].set(xlabel="Месяц регистрации, UTC", ylabel="Высота, м")
    axes[1].legend(ncol=2)
    return save_figure(fig, folder, "03_time.png")


def plot_group_counts(frame, folder):
    labels, rare = chart_groups(frame)
    counts = labels.value_counts()
    fig, ax = plt.subplots(figsize=(10, 3.8), layout="constrained")
    bars = ax.barh(counts.index, counts.values, color=["#315b83", "#b86726"][: len(counts)])
    ax.bar_label(
        bars, labels=[f"{n:,} ({n / len(frame):.2%})".replace(",", " ") for n in counts], padding=5
    )
    ax.set(
        xlim=(0, counts.max() * 1.3),
        xlabel="Наблюдения, шт.",
        ylabel="Вид птицы",
        title=f"Число наблюдений по видам · порог редкости 1% · объединено {len(rare)}",
    )
    ax.invert_yaxis()
    return save_figure(fig, folder, "04_group_counts.png")


def plot_heatmap(pivot, folder):
    fig, ax = plt.subplots(figsize=(11, 3.8), layout="constrained")
    cmap = plt.get_cmap("YlGnBu").copy()
    cmap.set_bad("#d6d6d6")
    image = ax.imshow(np.ma.masked_invalid(pivot.to_numpy(dtype=float)), aspect="auto", cmap=cmap)
    ticks = np.arange(0, len(pivot.columns), 3)
    ax.set_xticks(ticks, [str(pivot.columns[i]) for i in ticks], rotation=45, ha="right")
    ax.set_yticks(np.arange(len(pivot)), pivot.index)
    ax.set(
        xlabel="Месяц регистрации, UTC", ylabel="Вид птицы", title="Медиана высоты по виду и месяцу"
    )
    ax.grid(False)
    fig.colorbar(image, ax=ax, label="Медиана высоты, м")
    fig.text(
        0.01,
        -0.03,
        "Серый цвет — нет наблюдений; нулевая высота входит в цветовую шкалу.",
        fontsize=9,
    )
    return save_figure(fig, folder, "05_heatmap.png")


def anomaly_frequencies(frame, masks):
    """Частоты высот по готовым маскам; пороги здесь не пересчитываются."""
    for name in ("iqr", "negative"):
        mask = masks[name]
        if not isinstance(mask, pd.Series) or not mask.index.equals(frame.index):
            raise ValueError("Маска должна иметь длину и индекс исходной таблицы")
        if not pd.api.types.is_bool_dtype(mask) or mask.isna().any():
            raise ValueError("Маска должна содержать только булевы значения без пропусков")
    category = masks["iqr"].astype("int8") + 2 * masks["negative"].astype("int8")
    return (
        frame[[TARGET]]
        .assign(category=category)
        .dropna(subset=[TARGET])
        .groupby([TARGET, "category"], observed=True)
        .size()
        .rename("count")
        .reset_index()
    )


def plot_anomalies(frame, masks, bounds, folder):
    # Все значения представлены частотами, без случайной подвыборки.
    frequencies = anomaly_frequencies(frame, masks)
    values = frequencies[TARGET].to_numpy()
    counts = frequencies["count"].to_numpy()
    categories = frequencies["category"].to_numpy()
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), layout="constrained")
    colors = ["#77919c", "#c55535", "#c89b24", "#754b92"]
    names = ["Не отмечены", "Только IQR", "Только < 0 м", "Оба правила"]
    for ax in axes:
        for category, (color, name) in enumerate(zip(colors, names)):
            flag = categories == category
            ax.scatter(values[flag], counts[flag], s=9, color=color, label=name, alpha=0.8)
        for boundary in bounds:
            ax.axvline(boundary, color="#c55535", linestyle="--", linewidth=1)
        ax.axvline(0, color="#c89b24", linestyle=":", linewidth=1)
        ax.set(xlabel="Высота, м", ylabel="Частота значения, шт.")
    axes[0].set_title("Полный диапазон")
    axes[1].set(title="Увеличение участка от −100 до 150 м", xlim=(-100, 150))
    fig.suptitle("Значения, отмеченные двумя правилами")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="outside lower center", ncol=4, fontsize=9)
    return save_figure(fig, folder, "06_anomalies.png")


def observations(frame, summary, series, groups, pivot, anomalies, bounds):
    missing_cells = int(pivot.isna().sum().sum())
    peak = series["count"].idxmax()
    iqr_n, negative_n = map(int, anomalies["count"].iloc[:2])
    outside = int((~frame[TARGET].between(-100, 300) & frame[TARGET].notna()).sum())
    peak_group, peak_month = pivot.stack().idxmax()
    peak_median = pivot.loc[peak_group, peak_month]
    return [
        f"Медиана высоты — {summary.iloc[0]['median_m']:.0f} м, среднее — {summary.iloc[0]['mean_m']:.2f} м; распределение имеет длинный правый хвост. За пределами увеличенного участка {outside:,} значений.",
        f"Медиана Larus argentatus — {groups.loc['Larus argentatus', 'median_m']:.0f} м, Larus fuscus — {groups.loc['Larus fuscus', 'median_m']:.0f} м. Разность 9 м описывает эти наблюдения, а не доказанное различие популяций.",
        f"Наибольшее число наблюдений приходится на {peak}: {series.loc[peak, 'count']:,}; календарь содержит {len(series)} месяцев, пустых — {int((series['count'] == 0).sum())}.",
        f"Larus argentatus составляет {groups.loc['Larus argentatus', 'share']:.2%} наблюдений; порог 1% не объединяет ни одну из двух категорий.",
        f"Максимальная месячная медиана — {peak_median:.0f} м у {peak_group} в {peak_month}. Сводная таблица содержит {pivot.shape[0]} вида × {pivot.shape[1]} месяцев; пустых сочетаний — {missing_cells}.",
        f"IQR отмечает {iqr_n:,} строк за границами [{bounds[0]:.0f}; {bounds[1]:.0f}] м; отрицательная высота встречается в {negative_n:,} строках. Пересечение — {int(anomalies.iloc[0]['overlap']):,} строк.",
    ]


def run_analysis(root):
    root = Path(root)
    for name in ("results", "logs", "plots"):
        (root / name).mkdir(parents=True, exist_ok=True)
    path = root / "data/processed/clean.parquet"
    before = sha256(path)
    frame = load_data(path)
    summary, series, groups = target_summary(frame), time_summary(frame), group_summary(frame)
    pivot = median_pivot(frame, series.index)
    masks, anomalies, bounds = anomaly_rules(frame[TARGET])
    timing = benchmark(frame[TARGET])
    conclusions = observations(frame, summary, series, groups, pivot, anomalies, bounds)
    comparison = {
        "iqr_matches_lr1": bool(np.array_equal(masks["iqr"], frame["height_iqr_flag"])),
        "negative_matches_lr1": bool(np.array_equal(masks["negative"], frame["height_negative"])),
    }
    assert all(comparison.values()), "Правила должны совпадать с сохраненными флагами ЛР1"
    for name, table in (
        ("table1_target", summary),
        ("table2_time_full", series),
        ("table3_groups", groups),
        ("pivot_medians", pivot),
        ("table4_anomalies", anomalies),
    ):
        table.to_csv(root / f"results/{name}.csv", encoding="utf-8-sig")
    (root / "results/benchmark.json").write_text(
        json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    record = {
        "target": TARGET,
        "date": DATE,
        "group": GROUP,
        "rows": len(frame),
        "birds": int(frame["organism_id"].nunique()),
        "date_min": str(frame[DATE].min()),
        "date_max": str(frame[DATE].max()),
        "iqr_bounds": bounds,
        "rare_threshold": RARE_SHARE,
        "merged_categories": chart_groups(frame)[1],
        "conclusions": conclusions,
        "sha256_before": before,
        "sha256_after": sha256(path),
        **comparison,
    }
    assert record["sha256_before"] == record["sha256_after"]
    (root / "results/analysis.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (root / "logs/eda.log").write_text(
        json.dumps(
            {**record, "anomalies": anomalies.to_dict("records")}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    return frame, summary, series, groups, pivot, masks, anomalies, bounds, timing, conclusions
