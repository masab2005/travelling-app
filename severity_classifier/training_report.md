# Cleaned severity classifier training report

## Data check
- Rows: 355
- Class counts: {1: 233, 2: 122}
- Labels are only 1 and 2; no blank text; no duplicate IDs.
- Rows chunked because they exceeded 256 tokenizer tokens: 4.
- Chunked IDs: G7s87he8JlyBLs4FTWW3_03, b3J7aGFlMAMzhp0AG1lQ_07, h5pLxGUCwdEE4B9eblSG_01, sltYMsJRA9xs2bNzp7hp_01

## Nested grouped outer CV

Five outer folds repeated with seeds 42-46. C was selected inside each training fold using grouped 3-fold CV and the one-standard-error rule. The threshold was fixed at 0.5.

| Metric | Mean +/- SD |
|---|---:|
| Macro-F1 | 0.9844 +/- 0.0182 |
| Class 2 recall | 0.9862 +/- 0.0281 |
| Class 2 precision | 0.9747 +/- 0.0373 |
| False negatives | 0.3600 +/- 0.7572 |

- Final C selected on all cleaned rows: `10`.
- Scores above are from outer folds only.

## Robustness diagnostic

- Cases: 30; accuracy: 0.733.
- `guide_tricky_cases`: 4/5 correct
- `hedged_hazards`: 4/5 correct
- `mixed_boundary_cases`: 3/5 correct
- `negation`: 3/5 correct
- `plain_weather`: 4/5 correct
- `without_usual_keywords`: 4/5 correct

Failures:
- R01: expected 1, predicted 2; No landslide is expected in the upper valleys during the forecast period.
- R03: expected 1, predicted 2; Heavy rain is expected, but no flooding or road impact is forecast.
- R07: expected 1, predicted 2; Water levels will rise in rivers due to snowmelt, with no flood warning.
- R11: expected 1, predicted 2; Tourists should remain cautious during the forecast period.
- R16: expected 1, predicted 2; There is little chance of an avalanche, and roads remain open.
- R24: expected 1, predicted 2; Snow showers are expected over passes with no road effects mentioned.
- R28: expected 1, predicted 2; The advisory recommends caution because of changing weather.
- R30: expected 1, predicted 2; Hail may damage vehicles parked outdoors, but roads remain usable.

## Seed-42 outer-fold misclassifications

- `4zaJEoGNf1i5ELNiQ0Qm_02` probability=0.730058, actual=1, predicted=2: In Gilgit-Baltistan and Khyber Pakhtunkhwa, the water flows will increase in rivers and nullahs due to high rate of snow and ice melting.
- `6a60af7f0ced2_01` probability=0.512318, actual=1, predicted=2: Dated: 22 July 2026 Subject: Significant Increase in Water Levels in Rivers, Streams and Nullahs Across the Glaciated Regions Pakistan Meteorological Department (PMD) has issued a press release (Annex-A) stating that a significant increase in water levels has been observed in rivers, streams and nullahs across the glaciated regions of Gilgit Baltistan and Khyber Pakhtunkhwa.
- `G7s87he8JlyBLs4FTWW3_03` probability=0.427249, actual=2, predicted=1: o Rain-windstorm/thundershower (solated heavy fall) are expected in Rawalpindi, Murree, Attock, Chakwal, Jhelum, Sargodha, Hafizabad, M. B Din, Sialkot, Narowal, Lahore, Gujranwala, Gujrat, Sheikhupura, Faisalabad, Jhang. T.T Singh, Okara, Sahiwal and Bahawalnagar from 30 June to 4 July 2022 (Thursday to Monday). Sindh Rain-windstorm/thundershower (lsolated heavy falls) are expected in Karachi, Hyderabad, Thatta, Badin, Dadu from 1-5 July 2022 (Friday to Tuesday). Gilgit-Baltistan oRain-windstorm/thundershower (lsolated heavy falls) are expected in Gilit Baltistan from 30 June to 4 July 2022 (Thursday to Monday). Azad Jamnmu & Kashmir Rain-windstorm/thundershower (lsolated heavy falls) are expected in Kashmir from 30 June to 4 July 2022 (Thursday to Monday) Possible Impacts Heavy falls may generate urban flooding in Islamabad, Rawalpindi, Lahore, Gujranwala, Sialkot, Faisalabad from 2-4 July & in Karachi and Hyderabad from 3-5 July. Fishermen are advised to remain careful due to rough sea conditions from 3-5 July. Flash flooding is also expected in local nullahs of Kashmir, Khuzdar, Lasbella, Naseerabad, Awaran, Barkhan and Kohlu during the forecast period. Heavy rainfall may trigger landslides in Kashmir, Galliyat and Murree. The rising temperatures are likely to subside during the forecast period. Windstorms may damage loose structures at vulnerable locations. Rainwater will be beneficial for the sowing of rice crop. Travelers and tourists are advised to remain extra cautious during the forecast period. NOTE All concerned authorities are advised to remain ALERT during the forecast period.
- `GCXcjinOgLHmvLapOSzG_04` probability=0.539447, actual=1, predicted=2: (4) Windstorms / Hailstorms may damage crops, loose structures, etc. GB

## Final model

- Embedding: `sentence-transformers/all-MiniLM-L6-v2`, frozen and L2-normalized.
- C: `10`; threshold: `0.5`.
- Long rows use independently embedded chunks of at most 256 tokenizer tokens, averaged and re-normalized.
- Robustness cases were diagnostic only and were not used for tuning.

## Caveats

The cleaned dataset remains modest, and the hand-written robustness set is not a held-out statistical benchmark. Results may be noisy; Class 2 recall remains the operational priority.