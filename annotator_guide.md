# Travel Advisory Hazard Classification Guide

## 1. What you are doing

We are building a travel app for 9 tourist areas in northern Pakistan (Hunza, Skardu, Gilgit, Naran, Swat, Murree/Galliyat, Chitral, Dir, Neelum Valley).

Roughly every 10 days, NDMA and PMD publish a hazard advisory. Our system pulls out each forecast sentence, and your labels teach a model to judge how serious each sentence is. In the app:

- Class 1 shows a yellow "Be Cautious" notice.
- Class 2 shows a red alert with a "Repair My Plan" button.

Because advisories come only every week or two, red alerts will be rare. Do not worry about over-alerting. **When you are unsure about a serious hazard, lean toward class 2.** A missed warning is worse than an extra alert.

## 2. The two classes

### Class 1: Potential Disruption

The sentence describes weather only: rain, snow, wind, hail, fog, or temperature changes. It does not predict landslides, floods, or any impact on roads.

Examples:

- "Scattered rain-wind/thunderstorm is expected in Dir, Chitral, Swat from 2nd to 5th June with occasional gaps."
- "Day temperatures are likely to remain 07-08°C above normal in Khyber Pakhtunkhwa, Gilgit-Baltistan and Kashmir."

### Class 2: High Alert

The sentence predicts or states any of the following: landslide, mudslide, rockfall, avalanche, flash flood, urban flooding, GLOF, or any impact on roads and travel (closure, blockage, disruption).

Examples:

- "Snowfall may cause road closure/slippery conditions in Naran, Kaghan, Dir, Swat..."
- "Heavy rainfall may trigger flash floods and landslides in vulnerable areas of Murree, Galliyat, Khyber Pakhtunkhwa..."

## 3. The decision rule

Ask one question: **does this sentence warn about a hazard that could trap, block, or endanger a traveler?** That means landslides, floods, or road problems.

- Weather alone (rain, snow, wind) → Class 1
- Landslide, flood, or road impact warned or stated → Class 2

## 4. Tricky cases

These are real sentences where the choice is not obvious. Study the reasoning, not just the answer. There are only a few of these on purpose: most sentences should be judged by the rule in section 3, not by matching examples.

1. "Possibility of landslides in hilly areas of Khyber Pakhtunkhwa, Gilgit-Baltistan and Kashmir cannot be ruled out." → **2**. The wording is cautious ("cannot be ruled out"), but a landslide warning is still a landslide warning. Do not downgrade a hazard just because the author hedged.

2. "In Gilgit-Baltistan and Khyber Pakhtunkhwa, the water flows will increase in rivers and nullahs due to high rate of snow and ice melting." → **1**. Rising water is described, but no flood or landslide is predicted. Label what is written, not what might follow.

3. "Windstorms may damage loose structures at vulnerable locations." → **1**. Damage to buildings or crops is not a traveler-blocking hazard. Only roads, landslides, and floods trigger class 2.

4. "Travelers and tourists are advised to remain extra cautious during the forecast period." → **1** on its own. Advice to be careful is not a hazard prediction. If the same sentence also predicts a landslide, it becomes 2.

## 5. Mistakes to avoid

1. Do not downgrade a sentence because it "sounds routine." NDMA repeats landslide warnings often. Repetition does not make them less serious.
2. Do not upgrade plain weather. "Very heavy rain expected" with no mention of floods or landslides is still class 1, even if it sounds scary.
3. Do not guess what happened on the ground. Label only what the sentence says.
4. Do not let the official tone sway you either way. Every sentence here comes from an official advisory, so that fact tells you nothing.

## 6. How to fill the spreadsheet

- **segment_text**: the sentence you are classifying. Read this, nothing else.
- **is_in_kappa_sample**: if True, both annotators label the row independently in their own column. If False, put your label directly in **label**.
- **annotator_1_label / annotator_2_label**: your class (1 or 2) for the 130 double-labeled rows.
- **weak_label_hint**: a computer's rough guess. Do not trust it. Trust your own reading.
- **label_notes**: optional. Use it when a sentence felt like a close call.
- The rest of the columns are tracking data. Ignore them while labeling.

## 7. When you are unsure

Apply the decision rule once more. If it is still a genuine 50/50, pick your best guess, lean toward 2 for landslide or flood related sentences, and write a short note in **label_notes**. We will review the notes together.
