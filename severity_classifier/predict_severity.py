"""Predict severity with the cleaned frozen MiniLM model."""

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
