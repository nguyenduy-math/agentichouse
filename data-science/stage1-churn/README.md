# Stage 1 — Telco Customer Churn (end-to-end workflow practice)

The goal of this project is **not** to build the best churn model. It's to wire together the 8-step data science workflow so it becomes reflex:

1. Frame the question
2. Load + inspect
3. EDA
4. Clean + feature engineer
5. Baseline model
6. Evaluate
7. Iterate
8. Communicate

We're focusing on items **3–8**. Items 1 and 2 are covered briefly in `01_load_and_inspect.ipynb` so we have data to work with.

## The question (item 1, brief)

> Given a customer's account attributes (tenure, services, contract type, billing), can we predict whether they will churn in the next billing cycle?

It's a **binary classification** problem. We care about churners (the positive class) more than non-churners because acting on a churn prediction is what generates business value.

## Setup

### 1. Create and activate a virtual environment (PowerShell)

```powershell
cd c:\Users\CuaHangVatTu\Documents\dshouse\agentichouse\data-science\stage1-churn
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If activation is blocked by execution policy, run once per user:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Download the data

```powershell
python download_data.py
```

This pulls the IBM Telco Customer Churn CSV (~7043 rows, 21 columns) from a public GitHub mirror into `data/telco_churn.csv`. No Kaggle account needed.

### 4. Launch Jupyter

```powershell
jupyter lab
```

Or open the notebooks directly in VS Code (the Jupyter extension handles `.ipynb` files natively).

## Notebook order

| # | Notebook | Workflow step |
|---|----------|---------------|
| 01 | `01_load_and_inspect.ipynb` | Items 1–2 (framing + load/inspect) |
| 02 | `02_eda.ipynb` | Item 3 — EDA |
| 03 | `03_clean_and_features.ipynb` | Item 4 — Clean + feature engineer |
| 04 | `04_baseline.ipynb` | Item 5 — Baseline model |
| 05 | `05_evaluate.ipynb` | Item 6 — Evaluate |
| 06 | `06_iterate.ipynb` | Item 7 — Iterate |
| 07 | `07_summary.md` | Item 8 — Communicate |

We build these **one at a time**. Don't rush ahead — the point is to feel each step.
