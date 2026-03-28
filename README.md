# Singapore Hawker Reviews — NLP Notebooks

This project contains **four Jupyter notebooks** for preprocessing hawker-centre review text, running transformer-based sentiment inference, measuring inter-annotator agreement, and evaluating model quality against manual labels.

## Prerequisites

- **Python 3** (3.9+ recommended)
- Core libraries: `pandas`, `re` (stdlib)

Install the libraries your chosen notebooks need in your Python environment (virtualenv or conda recommended). Typical extras:

| Notebook                             | Main dependencies                                             |
| ------------------------------------ | ------------------------------------------------------------- |
| `hawker_review_preprocessing.ipynb`  | `pandas`                                                      |
| `sota_roberta_sentiment.ipynb`       | `torch`, `transformers`, `tqdm`                               |
| `inter_annotator_agreement.ipynb`    | `pandas`, `scikit-learn`, `openpyxl`                          |
| `sentiment_evaluation_metrics.ipynb` | `pandas`, `scikit-learn`, `matplotlib`, `seaborn`, `openpyxl` |


Example:

```bash
python3 -m pip install pandas torch transformers tqdm scikit-learn matplotlib seaborn openpyxl
```

## Input data (expected in this folder)


| File                                                                  | Description                                                                                                 |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `hawker_corpus_final10k.csv`                                          | Raw corpus: at minimum `hawker_centre`, `stall_name`, `review_text` (and optional columns such as ratings). |
| `hawker_corpus_final10k_cleaned.csv`                                  | Produced by preprocessing; must include `cleaned_review` for inference.                                     |
| `full_dataset_with_predictions.csv`                                   | Produced by the RoBERTa notebook; used for evaluation.                                                      |
| `Hand_Labeling_Task_Trurong.xlsx` / `Hand_Labeling_Task_Huiling.xlsx` | Two annotators’ sheets (1,000 rows each), aligned by `Review_ID`.                                           |
| `Hand_Labeling_Task_Resolved.xlsx`                                    | Final gold labels after disagreement resolution (1,000 rows).                                               |


Paths and filenames are set inside each notebook; adjust the variables at the top of the relevant cells if your files differ.

---

## Notebook overview (recommended order)

### 1. `hawker_review_preprocessing.ipynb`

**Purpose:** Clean `review_text` for downstream sentiment use.

**What it does:**

- Loads the main CSV and ensures `review_text` is string-typed.
- Optional: adds a unique `Review_ID` column and saves back to the source CSV (if you use that cell).
- Removes HTML/URLs/noise, normalises elongated characters (e.g. “sooooo” → “soo”), lowercases, tokenises, removes a small English stopword list while **keeping negations** (`not`, `never`, `no`, etc.), and preserves local vocabulary by **not** autocorrecting Singlish terms.
- Writes `cleaned_review` to `**hawker_corpus_final10k_cleaned.csv`**.

**Optional cells** (if present in your copy): export a 1,000-row Excel file for manual labelling (`Hand_Labeling_Task.xlsx`).

---

### 2. `sota_roberta_sentiment.ipynb`

**Purpose:** Score all cleaned reviews with a pre-trained sentiment model.

**What it does:**

- Reads `**hawker_corpus_final10k_cleaned.csv`** and uses column `**cleaned_review**`.
- Loads `**cardiffnlp/twitter-roberta-base-sentiment-latest**` via Hugging Face `transformers`.
- Runs **batched inference** (default batch size 16), reports **wall-clock time** and **records per second (RPS)**.
- Maps model outputs to `**pred_polarity`** (−1 / 0 / 1) and `**pred_subjectivity**` (rule using neutral confidence vs threshold).
- Saves `**full_dataset_with_predictions.csv**`.

Run this **after** preprocessing so the cleaned column exists.

---

### 3. `inter_annotator_agreement.ipynb`

**Purpose:** Quantify agreement between two annotators before or after reconciliation.

**What it does:**

- Loads two Excel files (e.g. `**Hand_Labeling_Task_Trurong.xlsx`** and `**Hand_Labeling_Task_Huiling.xlsx**`).
- Merges on `**Review_ID**` and compares `**Subjectivity**` and `**Polarity**`.
- Prints **simple percentage agreement** and **Cohen’s κ** for each task.
- Exports disagreement rows to `**Labeling_Discrepancies.xlsx`** for review.

Use this once both annotators have submitted their 1,000-row files.

---

### 4. `sentiment_evaluation_metrics.ipynb`

**Purpose:** Evaluate the model against resolved manual labels.

**What it does:**

- Loads `**Hand_Labeling_Task_Resolved.xlsx`** (gold: `Subjectivity` / `Polarity` renamed internally to `manual_*`) and `**full_dataset_with_predictions.csv**`.
- Inner-merges on `**Review_ID**` (expects 1,000 aligned rows).
- Prints `**classification_report**` and `**confusion_matrix**` for Subjectivity and Polarity; reports **macro / weighted / micro** F1 (and related summaries for polarity).
- Plots confusion matrices with **seaborn** heatmaps.

Run this **after** you have `**Hand_Labeling_Task_Resolved.xlsx`** and `**full_dataset_with_predictions.csv**`.

---

## Quick pipeline checklist

1. Run `**hawker_review_preprocessing.ipynb**` → `hawker_corpus_final10k_cleaned.csv`
2. Run `**sota_roberta_sentiment.ipynb**` → `full_dataset_with_predictions.csv`
3. (Annotate independently; resolve conflicts → `Hand_Labeling_Task_Resolved.xlsx`)
4. Optional: `**inter_annotator_agreement.ipynb**` on the two raw annotator files
5. Run `**sentiment_evaluation_metrics.ipynb**` for precision/recall/F1 vs gold

---

## Notes

- If package installation fails due to permissions, use a virtual environment or conda.
- RoBERTa inference time depends strongly on **CPU vs GPU**, **batch size**, and `**max_length`**; adjust those in `sota_roberta_sentiment.ipynb` for your hardware.

