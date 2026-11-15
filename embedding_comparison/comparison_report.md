# Frozen sentence-embedding comparison

## Data check
- Rows: 359
- Class counts: {1: 237, 2: 122}
- Blank text: 0; duplicate IDs: 0; labels outside 1/2: 0.
- Protocol: 5-fold StratifiedGroupKFold repeated with seeds 42-46 (25 paired splits).

## Primary results (LogisticRegression, C=1.0)

| Model | Dim | Encode seconds | Parameter MB | Macro-F1 mean +/- SD | Class 2 recall | Class 2 precision | Class 2 F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| all-MiniLM-L6-v2 | 384 | 15.812 | 86.64 | 0.9666 +/- 0.0225 | 0.9701 +/- 0.0344 | 0.9428 +/- 0.0464 | 0.9555 +/- 0.0308 |
| bge-small-en-v1.5 | 384 | 34.559 | 127.26 | 0.9560 +/- 0.0195 | 0.9548 +/- 0.0337 | 0.9312 +/- 0.0514 | 0.9417 +/- 0.0274 |
| all-mpnet-base-v2 | 768 | 119.217 | 417.66 | 0.9586 +/- 0.0185 | 0.9769 +/- 0.0247 | 0.9187 +/- 0.0542 | 0.9456 +/- 0.0256 |

## Paired macro-F1 comparison

- `all-MiniLM-L6-v2` minus `bge-small-en-v1.5`: mean difference 0.0106; wins 15 vs 4; ties 6.
- `all-MiniLM-L6-v2` minus `all-mpnet-base-v2`: mean difference 0.0081; wins 15 vs 8; ties 2.
- `bge-small-en-v1.5` minus `all-mpnet-base-v2`: mean difference -0.0025; wins 6 vs 12; ties 7.

## Seed 42 pooled confusion matrices

### all-MiniLM-L6-v2

Rows = actual class; columns = predicted class; order = [1, 2].

```text
[[230   7]
 [  4 118]]
```

### bge-small-en-v1.5

Rows = actual class; columns = predicted class; order = [1, 2].

```text
[[229   8]
 [  5 117]]
```

### all-mpnet-base-v2

Rows = actual class; columns = predicted class; order = [1, 2].

```text
[[227  10]
 [  3 119]]
```

## C sensitivity check

See `results_c_sensitivity.csv` for every split and C value.

## Selection rule

The highest mean macro-F1 is `all-MiniLM-L6-v2` (0.9666 +/- 0.0225).
The models within one standard deviation of that result are `all-MiniLM-L6-v2`, `bge-small-en-v1.5`, `all-mpnet-base-v2`.
Applying the fixed recall tie-break selects `all-mpnet-base-v2` (0.9769 mean class-2 recall). This is not a claim of statistical significance.

## Caveats

The dataset is small, so repeated grouped CV estimates can be noisy. Embeddings were frozen, no data was fit before each fold, and no final model training or hyperparameter selection was performed.