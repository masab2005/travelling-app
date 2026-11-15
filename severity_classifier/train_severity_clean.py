"""Train the cleaned MiniLM severity classifier from scratch."""

from __future__ import annotations

import csv
import re
import time
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedGroupKFold


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(__file__).resolve().parent
INPUT = ROOT / "labeling_training.csv"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDINGS_PATH = OUTPUT / "embeddings_all-MiniLM-L6-v2.npy"
MAX_TOKENS = 256
SEEDS = [42, 43, 44, 45, 46]
C_VALUES = [0.3, 1, 3, 10]
MONTHS = (
    "january|february|march|april|may|june|july|august|september|"
    "october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|"
    "oct|nov|dec"
)


def load_training_data():
    with INPUT.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    expected = ["canonical_segment_id", "segment_text", "label"]
    if not rows or list(rows[0]) != expected:
        raise ValueError(f"Expected columns exactly {expected}.")
    ids = [row["canonical_segment_id"] for row in rows]
    texts = np.asarray([row["segment_text"] for row in rows])
    labels = np.asarray([int(row["label"]) for row in rows])
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate canonical_segment_id values found.")
    if any(not text.strip() for text in texts):
        raise ValueError("Blank segment_text value found.")
    if set(labels) != {1, 2}:
        raise ValueError("Labels must contain only 1 and 2.")
    return rows, texts, labels


def group_key(text: str) -> str:
    value = text.lower()
    value = re.sub(rf"\b(?:{MONTHS})\b", " ", value)
    value = re.sub(r"\d+(?:st|nd|rd|th)?", " ", value)
    value = re.sub(r"[^a-z]+", " ", value)
    return " ".join(value.split())


def split_text_for_embedding(text: str, tokenizer):
    token_ids = tokenizer(text, add_special_tokens=False, truncation=False)["input_ids"]
    if len(token_ids) <= MAX_TOKENS:
        return [text], False
    chunks = []
    for start in range(0, len(token_ids), MAX_TOKENS):
        chunk_ids = token_ids[start : start + MAX_TOKENS]
        chunks.append(tokenizer.decode(chunk_ids, skip_special_tokens=True))
    return chunks, True


def encode_texts(model, texts):
    vectors = []
    chunked_ids = []
    for index, text in enumerate(texts):
        chunks, was_chunked = split_text_for_embedding(text, model.tokenizer)
        if was_chunked:
            chunked_ids.append(index)
        encoded = model.encode(
            chunks,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        vector = np.mean(np.atleast_2d(encoded), axis=0)
        vector = vector / np.linalg.norm(vector)
        vectors.append(vector)
    return np.asarray(vectors, dtype=np.float32), chunked_ids


def make_splits(labels, texts, seed, folds):
    groups = np.asarray([group_key(text) for text in texts])
    splitter = StratifiedGroupKFold(
        n_splits=folds, shuffle=True, random_state=seed
    )
    return list(splitter.split(texts, labels, groups))


def evaluate(actual, probabilities):
    predicted = np.where(probabilities >= 0.5, 2, 1)
    return {
        "macro_f1": float(f1_score(actual, predicted, average="macro", zero_division=0)),
        "class2_recall": float(
            recall_score(actual, predicted, pos_label=2, zero_division=0)
        ),
        "class2_precision": float(
            precision_score(actual, predicted, pos_label=2, zero_division=0)
        ),
        "false_negatives": int(((actual == 2) & (predicted == 1)).sum()),
    }


def choose_c(x, y, texts, seed):
    scores = []
    for c_value in C_VALUES:
        fold_scores = []
        for train, test in make_splits(y, texts, seed + 1000, 3):
            classifier = LogisticRegression(
                C=c_value, class_weight="balanced", max_iter=5000
            )
            classifier.fit(x[train], y[train])
            probabilities = classifier.predict_proba(x[test])[:, 1]
            fold_scores.append(evaluate(y[test], probabilities)["macro_f1"])
        scores.append(
            {
                "C": c_value,
                "mean_macro_f1": float(np.mean(fold_scores)),
                "sd_macro_f1": float(np.std(fold_scores, ddof=1)),
                "se_macro_f1": float(np.std(fold_scores, ddof=1) / np.sqrt(len(fold_scores))),
            }
        )
    best = max(scores, key=lambda row: row["mean_macro_f1"])
    cutoff = best["mean_macro_f1"] - best["se_macro_f1"]
    eligible = [row for row in scores if row["mean_macro_f1"] >= cutoff]
    chosen = min(eligible, key=lambda row: row["C"])
    return chosen["C"], scores, best, cutoff


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_robustness():
    path = OUTPUT / "robustness_test.csv"
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    required = {"case_id", "group", "segment_text", "expected_label", "needs_team_review", "reason"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("robustness_test.csv is missing required test-case columns.")
    return rows


def write_predictor():
    (OUTPUT / "predict_severity.py").write_text(
        '''"""Predict severity with the cleaned frozen MiniLM model."""

from pathlib import Path

import joblib
import numpy as np
from sentence_transformers import SentenceTransformer


ROOT = Path(__file__).resolve().parent
ARTIFACT = joblib.load(ROOT / "severity_model.joblib")
MODEL = SentenceTransformer(ARTIFACT["embedding_model"])
MAX_TOKENS = ARTIFACT["max_tokens"]


def _embedding(text):
    ids = MODEL.tokenizer(
        text, add_special_tokens=False, truncation=False
    )["input_ids"]
    if len(ids) <= MAX_TOKENS:
        chunks = [text]
    else:
        chunks = [
            MODEL.tokenizer.decode(
                ids[i : i + MAX_TOKENS], skip_special_tokens=True
            )
            for i in range(0, len(ids), MAX_TOKENS)
        ]
    vectors = MODEL.encode(
        chunks,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    vector = np.mean(np.atleast_2d(vectors), axis=0)
    return vector / np.linalg.norm(vector)


def predict(list_of_texts):
    results = []
    threshold = ARTIFACT["threshold"]
    for text in list_of_texts:
        probability = float(
            ARTIFACT["classifier"].predict_proba([_embedding(text)])[0, 1]
        )
        results.append(
            {
                "label": 2 if probability >= threshold else 1,
                "class2_probability": probability,
                "uncertain": abs(probability - threshold) <= 0.15,
            }
        )
    return results
''',
        encoding="utf-8",
    )


def write_report(rows, labels, chunked_rows, outer_results, selected, robustness, errors):
    def summary(field):
        values = np.asarray([float(row[field]) for row in outer_results])
        return f"{values.mean():.4f} +/- {values.std(ddof=1):.4f}"

    groups = sorted({row["group"] for row in robustness})
    failures = [row for row in robustness if not row["correct"]]
    lines = [
        "# Cleaned severity classifier training report",
        "",
        "## Data check",
        f"- Rows: {len(rows)}",
        f"- Class counts: {dict(sorted(Counter(labels.tolist()).items()))}",
        "- Labels are only 1 and 2; no blank text; no duplicate IDs.",
        f"- Rows chunked because they exceeded {MAX_TOKENS} tokenizer tokens: {len(chunked_rows)}.",
        f"- Chunked IDs: {', '.join(chunked_rows) if chunked_rows else 'None.'}",
        "",
        "## Nested grouped outer CV",
        "",
        "Five outer folds repeated with seeds 42-46. C was selected inside each "
        "training fold using grouped 3-fold CV and the one-standard-error rule. "
        "The threshold was fixed at 0.5.",
        "",
        "| Metric | Mean +/- SD |",
        "|---|---:|",
        f"| Macro-F1 | {summary('macro_f1')} |",
        f"| Class 2 recall | {summary('class2_recall')} |",
        f"| Class 2 precision | {summary('class2_precision')} |",
        f"| False negatives | {summary('false_negatives')} |",
        "",
        f"- Final C selected on all cleaned rows: `{selected}`.",
        "- Scores above are from outer folds only.",
        "",
        "## Robustness diagnostic",
        "",
        f"- Cases: {len(robustness)}; accuracy: {np.mean([row['correct'] for row in robustness]):.3f}.",
    ]
    for group in groups:
        subset = [row for row in robustness if row["group"] == group]
        lines.append(
            f"- `{group}`: {sum(row['correct'] for row in subset)}/{len(subset)} correct"
        )
    lines.append("")
    lines.append("Failures:")
    lines.extend(
        f"- {row['case_id']}: expected {row['expected_label']}, predicted {row['predicted_label']}; {row['segment_text']}"
        for row in failures
    )
    if not failures:
        lines.append("- None.")
    lines.extend(["", "## Seed-42 outer-fold misclassifications", ""])
    lines.extend(
        f"- `{row['canonical_segment_id']}` probability={row['class2_probability']}, "
        f"actual={row['actual_label']}, predicted={row['predicted_label']}: {row['segment_text']}"
        for row in errors
    )
    if not errors:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Final model",
            "",
            f"- Embedding: `{MODEL_NAME}`, frozen and L2-normalized.",
            f"- C: `{selected}`; threshold: `0.5`.",
            "- Long rows use independently embedded chunks of at most 256 tokenizer tokens, averaged and re-normalized.",
            "- Robustness cases were diagnostic only and were not used for tuning.",
            "",
            "## Caveats",
            "",
            "The cleaned dataset remains modest, and the hand-written robustness set is not "
            "a held-out statistical benchmark. Results may be noisy; Class 2 recall remains "
            "the operational priority.",
        ]
    )
    (OUTPUT / "training_report.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows, texts, labels = load_training_data()
    print(f"Rows: {len(rows)}; class counts: {dict(sorted(Counter(labels.tolist()).items()))}")
    model = SentenceTransformer(MODEL_NAME)
    started = time.perf_counter()
    embeddings, chunked_indexes = encode_texts(model, texts)
    encode_seconds = time.perf_counter() - started
    np.save(EMBEDDINGS_PATH, embeddings)
    chunked_rows = [rows[index]["canonical_segment_id"] for index in chunked_indexes]
    print(f"Embedding dimension: {embeddings.shape[1]}; encode seconds: {encode_seconds:.2f}")
    print(f"Chunked rows ({len(chunked_rows)}): {chunked_rows}")

    outer_results = []
    selected_parameters = []
    errors = []
    for seed in SEEDS:
        for fold, (train, test) in enumerate(make_splits(labels, texts, seed, 5), 1):
            chosen, inner_scores, best, cutoff = choose_c(
                embeddings[train], labels[train], texts[train], seed
            )
            selected_parameters.append(
                {
                    "seed": seed,
                    "fold": fold,
                    "chosen_C": chosen,
                    "best_mean_macro_f1": best["mean_macro_f1"],
                    "one_se_cutoff": cutoff,
                }
            )
            classifier = LogisticRegression(C=chosen, class_weight="balanced", max_iter=5000)
            classifier.fit(embeddings[train], labels[train])
            probabilities = classifier.predict_proba(embeddings[test])[:, 1]
            metrics = evaluate(labels[test], probabilities)
            outer_results.append({"seed": seed, "fold": fold, "C": chosen, **metrics})
            if seed == 42:
                predicted = np.where(probabilities >= 0.5, 2, 1)
                for index, probability, prediction in zip(test, probabilities, predicted):
                    if prediction != labels[index]:
                        errors.append(
                            {
                                "canonical_segment_id": rows[index]["canonical_segment_id"],
                                "segment_text": texts[index],
                                "actual_label": labels[index],
                                "predicted_label": prediction,
                                "class2_probability": f"{probability:.6f}",
                                "seed": seed,
                                "fold": fold,
                            }
                        )

    write_csv(OUTPUT / "nested_outer_results.csv", outer_results)
    write_csv(OUTPUT / "nested_selected_parameters.csv", selected_parameters)
    write_csv(OUTPUT / "misclassified.csv", errors)

    final_c, final_scores, _, _ = choose_c(embeddings, labels, texts, 42)
    write_csv(OUTPUT / "inner_c_scores.csv", final_scores)
    classifier = LogisticRegression(C=final_c, class_weight="balanced", max_iter=5000)
    classifier.fit(embeddings, labels)
    joblib.dump(
        {
            "classifier": classifier,
            "C": final_c,
            "threshold": 0.5,
            "embedding_model": MODEL_NAME,
            "label_mapping": {1: "Potential Disruption", 2: "Direct Travel Restriction"},
            "max_tokens": MAX_TOKENS,
        },
        OUTPUT / "severity_model.joblib",
    )
    write_predictor()

    robustness = load_robustness()
    robustness_embeddings, _ = encode_texts(
        model, np.asarray([row["segment_text"] for row in robustness])
    )
    probabilities = classifier.predict_proba(robustness_embeddings)[:, 1]
    for row, probability in zip(robustness, probabilities):
        prediction = 2 if probability >= 0.5 else 1
        row["predicted_label"] = prediction
        row["class2_probability"] = f"{probability:.6f}"
        row["correct"] = int(prediction == int(row["expected_label"]))
    write_csv(OUTPUT / "robustness_test.csv", robustness)
    write_report(rows, labels, chunked_rows, outer_results, final_c, robustness, errors)
    print(f"Final C={final_c}; threshold=0.5; outer errors seed 42={len(errors)}.")


if __name__ == "__main__":
    print(f"sentence-transformers={__import__('sentence_transformers').__version__}")
    print(f"scikit-learn={sklearn.__version__}; numpy={np.__version__}")
    main()
