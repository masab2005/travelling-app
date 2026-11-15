"""Reproducible frozen sentence-embedding comparison.

Requirements:
    pip install sentence-transformers scikit-learn numpy
"""

from __future__ import annotations

import csv
import re
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import sklearn
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import StratifiedGroupKFold


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "labeling_training.csv"
OUTPUT = Path(__file__).resolve().parent
SEEDS = [42, 43, 44, 45, 46]
N_SPLITS = 5
PRIMARY_C = 1.0
SENSITIVITY_CS = [0.1, 1.0, 10.0]
MODELS = [
    "sentence-transformers/all-MiniLM-L6-v2",
    "BAAI/bge-small-en-v1.5",
    "sentence-transformers/all-mpnet-base-v2",
]
MONTHS = (
    "january|february|march|april|may|june|july|august|september|"
    "october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|"
    "oct|nov|dec"
)


def load_data() -> tuple[list[dict[str, str]], np.ndarray, np.ndarray]:
    with INPUT.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    expected = ["canonical_segment_id", "segment_text", "label"]
    if not rows or list(rows[0]) != expected:
        raise ValueError(f"Expected columns exactly {expected}.")
    ids = [row["canonical_segment_id"] for row in rows]
    texts = [row["segment_text"] for row in rows]
    labels = np.asarray([int(row["label"]) for row in rows])
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate canonical_segment_id values found.")
    if any(not text.strip() for text in texts):
        raise ValueError("Blank segment_text value found.")
    if set(labels) != {1, 2}:
        raise ValueError("Labels must contain only 1 and 2.")
    print(f"Input rows: {len(rows)}")
    print(f"Class counts: {dict(sorted(Counter(labels.tolist()).items()))}")
    return rows, np.asarray(texts), labels


def group_key(text: str) -> str:
    value = text.lower()
    value = re.sub(rf"\b(?:{MONTHS})\b", " ", value)
    value = re.sub(r"\d+(?:st|nd|rd|th)?", " ", value)
    value = re.sub(r"[^a-z]+", " ", value)
    return " ".join(value.split())


def make_splits(labels: np.ndarray, texts: np.ndarray) -> list[tuple[int, int, int, int]]:
    groups = np.asarray([group_key(text) for text in texts])
    splits = []
    for seed in SEEDS:
        splitter = StratifiedGroupKFold(
            n_splits=N_SPLITS, shuffle=True, random_state=seed
        )
        for fold, (train, test) in enumerate(splitter.split(texts, labels, groups), 1):
            splits.append((seed, fold, train, test))
    return splits


def model_slug(model_name: str) -> str:
    return model_name.rsplit("/", 1)[-1]


def metrics(y_true: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    return {
        "macro_f1": f1_score(y_true, predicted, average="macro", zero_division=0),
        "class2_recall": recall_score(y_true, predicted, pos_label=2, zero_division=0),
        "class2_precision": precision_score(y_true, predicted, pos_label=2, zero_division=0),
        "class2_f1": f1_score(y_true, predicted, pos_label=2, zero_division=0),
    }


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict], dimension: int, encode_time: float, size_mb: float) -> dict:
    result = {
        "model": rows[0]["model"],
        "dimension": dimension,
        "encode_time_seconds": f"{encode_time:.3f}",
        "parameter_size_mb": f"{size_mb:.2f}",
    }
    for metric in ("macro_f1", "class2_recall", "class2_precision", "class2_f1"):
        values = np.asarray([float(row[metric]) for row in rows])
        result[f"{metric}_mean"] = f"{values.mean():.4f}"
        result[f"{metric}_std"] = f"{values.std(ddof=1):.4f}"
    return result


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows, texts, labels = load_data()
    splits = make_splits(labels, texts)
    print(f"Generated and fixed {len(splits)} train/test splits.")
    print(f"sentence-transformers={__import__('sentence_transformers').__version__}")
    print(f"scikit-learn={sklearn.__version__}; numpy={np.__version__}")

    per_split = []
    sensitivity = []
    summaries = []
    confusion = {}
    errors = []
    previous_encode_times = {}
    previous_summary = OUTPUT / "results_summary.csv"
    if previous_summary.exists():
        with previous_summary.open(encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                previous_encode_times[row["model"]] = row["encode_time_seconds"]

    for model_name in MODELS:
        slug = model_slug(model_name)
        cache_path = OUTPUT / f"embeddings_{slug}.npy"
        try:
            model = SentenceTransformer(model_name)
            parameter_bytes = sum(
                parameter.numel() * parameter.element_size()
                for parameter in model.parameters()
            )
            size_mb = parameter_bytes / (1024 * 1024)
            if cache_path.exists():
                embeddings = np.load(cache_path)
                encode_time = float(previous_encode_times.get(slug, "0"))
                print(f"{model_name}: loaded cache {cache_path.name}")
            else:
                started = time.perf_counter()
                embeddings = model.encode(
                    texts.tolist(),
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                    show_progress_bar=True,
                )
                encode_time = time.perf_counter() - started
                np.save(cache_path, embeddings)
                print(f"{model_name}: encoded in {encode_time:.3f}s")
            if embeddings.shape[0] != len(rows):
                raise ValueError("Cached embedding row count does not match input.")
            dimension = int(embeddings.shape[1])

            model_rows = []
            for seed, fold, train, test in splits:
                classifier = LogisticRegression(
                    C=PRIMARY_C, class_weight="balanced", max_iter=2000
                )
                classifier.fit(embeddings[train], labels[train])
                values = metrics(labels[test], classifier.predict(embeddings[test]))
                model_rows.append(
                    {"model": slug, "seed": seed, "fold": fold, **values}
                )
            per_split.extend(model_rows)
            summaries.append(summarize(model_rows, dimension, encode_time, size_mb))

            seed42 = [item for item in splits if item[0] == 42]
            actual = []
            predicted = []
            for _, _, train, test in seed42:
                classifier = LogisticRegression(
                    C=PRIMARY_C, class_weight="balanced", max_iter=2000
                )
                classifier.fit(embeddings[train], labels[train])
                actual.extend(labels[test])
                predicted.extend(classifier.predict(embeddings[test]))
            confusion[slug] = confusion_matrix(actual, predicted, labels=[1, 2])

            for c_value in SENSITIVITY_CS:
                for seed, fold, train, test in splits:
                    classifier = LogisticRegression(
                        C=c_value, class_weight="balanced", max_iter=2000
                    )
                    classifier.fit(embeddings[train], labels[train])
                    values = metrics(labels[test], classifier.predict(embeddings[test]))
                    sensitivity.append(
                        {
                            "model": slug,
                            "C": c_value,
                            "seed": seed,
                            "fold": fold,
                            **values,
                        }
                    )
        except Exception as error:
            errors.append(f"- `{model_name}`: `{type(error).__name__}: {error}`")
            print(f"{model_name} failed: {error}", file=sys.stderr)

    write_csv(
        OUTPUT / "results_per_split.csv",
        ["model", "seed", "fold", "macro_f1", "class2_recall", "class2_precision", "class2_f1"],
        per_split,
    )
    write_csv(
        OUTPUT / "results_summary.csv",
        [
            "model", "dimension", "encode_time_seconds", "parameter_size_mb",
            "macro_f1_mean", "macro_f1_std", "class2_recall_mean", "class2_recall_std",
            "class2_precision_mean", "class2_precision_std", "class2_f1_mean", "class2_f1_std",
        ],
        summaries,
    )
    write_csv(
        OUTPUT / "results_c_sensitivity.csv",
        ["model", "C", "seed", "fold", "macro_f1", "class2_recall", "class2_precision", "class2_f1"],
        sensitivity,
    )
    write_report(rows, labels, summaries, per_split, sensitivity, confusion, errors)


def write_report(rows, labels, summaries, per_split, sensitivity, confusion, errors) -> None:
    lines = [
        "# Frozen sentence-embedding comparison",
        "",
        "## Data check",
        f"- Rows: {len(rows)}",
        f"- Class counts: {dict(sorted(Counter(labels.tolist()).items()))}",
        "- Blank text: 0; duplicate IDs: 0; labels outside 1/2: 0.",
        "- Protocol: 5-fold StratifiedGroupKFold repeated with seeds 42-46 (25 paired splits).",
        "",
        "## Primary results (LogisticRegression, C=1.0)",
        "",
        "| Model | Dim | Encode seconds | Parameter MB | Macro-F1 mean +/- SD | Class 2 recall | Class 2 precision | Class 2 F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summaries:
        lines.append(
            f"| {row['model']} | {row['dimension']} | {row['encode_time_seconds']} | "
            f"{row['parameter_size_mb']} | {row['macro_f1_mean']} +/- {row['macro_f1_std']} | "
            f"{row['class2_recall_mean']} +/- {row['class2_recall_std']} | "
            f"{row['class2_precision_mean']} +/- {row['class2_precision_std']} | "
            f"{row['class2_f1_mean']} +/- {row['class2_f1_std']} |"
        )
    lines.extend(["", "## Paired macro-F1 comparison", ""])
    for index, left in enumerate(summaries):
        for right in summaries[index + 1:]:
            left_values = np.asarray(
                [float(r["macro_f1"]) for r in per_split if r["model"] == left["model"]]
            )
            right_values = np.asarray(
                [float(r["macro_f1"]) for r in per_split if r["model"] == right["model"]]
            )
            differences = left_values - right_values
            lines.append(
                f"- `{left['model']}` minus `{right['model']}`: mean difference "
                f"{differences.mean():.4f}; wins {int((differences > 0).sum())} vs "
                f"{int((differences < 0).sum())}; ties {int((differences == 0).sum())}."
            )
    lines.extend(["", "## Seed 42 pooled confusion matrices", ""])
    for model, matrix in confusion.items():
        lines.extend(
            [
                f"### {model}",
                "",
                "Rows = actual class; columns = predicted class; order = [1, 2].",
                "",
                "```text",
                str(matrix),
                "```",
                "",
            ]
        )
    lines.extend(["## C sensitivity check", "", "See `results_c_sensitivity.csv` for every split and C value.", ""])
    if summaries:
        macro_leader = max(summaries, key=lambda row: float(row["macro_f1_mean"]))
        leader_mean = float(macro_leader["macro_f1_mean"])
        close = [
            row for row in summaries
            if abs(float(row["macro_f1_mean"]) - leader_mean)
            <= max(float(row["macro_f1_std"]), float(macro_leader["macro_f1_std"]))
        ]
        best = max(
            close,
            key=lambda row: (
                float(row["class2_recall_mean"]),
                -float(row["parameter_size_mb"]),
                -float(row["encode_time_seconds"]),
            ),
        )
        close_names = ", ".join(f"`{row['model']}`" for row in close)
        lines.extend(
            [
                "## Selection rule",
                "",
                f"The highest mean macro-F1 is `{macro_leader['model']}` "
                f"({macro_leader['macro_f1_mean']} +/- {macro_leader['macro_f1_std']}).",
                f"The models within one standard deviation of that result are "
                f"{close_names}.",
                f"Applying the fixed recall tie-break selects `{best['model']}` "
                f"({best['class2_recall_mean']} mean class-2 recall). This is not a claim "
                "of statistical significance.",
            ]
        )
    if errors:
        lines.extend(["", "## Model errors", *errors])
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "The dataset is small, so repeated grouped CV estimates can be noisy. "
            "Embeddings were frozen, no data was fit before each fold, and no final model "
            "training or hyperparameter selection was performed.",
        ]
    )
    (OUTPUT / "comparison_report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
