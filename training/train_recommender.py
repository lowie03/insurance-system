"""Train the Nigerian recommender from the synthetic data and save it as a bundle.

Reproduces Colab Cell 11 exactly (same splits, seeds and settings), then saves the model with
insurance_core.model_io so the backend can load it.

Usage:
    python training/train_recommender.py
    python training/train_recommender.py --data data/synthetic/synthetic_ng_customers.csv --version ng_recommender_v1
"""
import argparse
import warnings
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from insurance_core.evaluation import (cooccurrence_scores, evaluate, hide_one_product,
                                       popularity_scores, scores_from_model)
from insurance_core.features import CAT_COLS, MODEL_PRODUCTS, ProfileEncoder, build_features, expand_leave_one_out
from insurance_core.model_io import save_bundle
from insurance_core.settings import PROJECT_ROOT

LGBM_PARAMS = dict(
    n_estimators=2000, learning_rate=0.03, num_leaves=15, min_child_samples=30,
    min_child_weight=1.0, reg_lambda=5.0, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
    cat_smooth=20, min_data_per_group=50, max_cat_threshold=16, random_state=42, verbose=-1,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default=PROJECT_ROOT / "data/synthetic/synthetic_ng_customers.csv")
    parser.add_argument("--version", default="ng_recommender_v1")
    parser.add_argument("--out-dir", default=PROJECT_ROOT / "artifacts")
    args = parser.parse_args()

    df = pd.read_csv(args.data, dtype={"phone": str})
    products = MODEL_PRODUCTS
    customers = df[df[products].sum(axis=1) >= 1].reset_index(drop=True)
    print(f"{len(df):,} rows | {len(customers):,} customers with 1+ products")

    # Same splits as Colab: by customer, then an early-stopping slice of the training customers
    fit_c, val_c = train_test_split(customers, test_size=0.2, random_state=42)
    inner_c, es_c = train_test_split(fit_c, test_size=0.15, random_state=0)
    fit_c, val_c, inner_c, es_c = [d.reset_index(drop=True) for d in (fit_c, val_c, inner_c, es_c)]

    encoder = ProfileEncoder().fit(fit_c)
    inner_rows, y_in = expand_leave_one_out(inner_c, products)
    es_rows, y_es = expand_leave_one_out(es_c, products)
    X_in, X_es = build_features(inner_rows, encoder, products), build_features(es_rows, encoder, products)

    model = lgb.LGBMClassifier(**LGBM_PARAMS)
    # LightGBM 4.7+ marks eval_set as deprecated in favour of eval_X/eval_y, but the new
    # arguments don't handle text labels like "HFM" yet, so we keep eval_set and hide the warning.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*eval_set.*deprecated.*")
        model.fit(X_in, y_in, eval_set=[(X_es, y_es)], categorical_feature=CAT_COLS,
                  callbacks=[lgb.early_stopping(50, verbose=False)])
    print(f"Trained on {len(X_in):,} rows | best number of trees: {model.best_iteration_}")

    # Evaluate against both baselines, split by cold start vs has history
    val_masked = hide_one_product(val_c, products)
    X_val = build_features(val_masked, encoder, products)
    cold = (val_masked[products].sum(axis=1) == 0).to_numpy()
    all_scores = {
        "Popularity": popularity_scores(fit_c, len(val_masked), products),
        "Co-occurrence": cooccurrence_scores(fit_c, val_masked, products),
        "LightGBM": scores_from_model(model, X_val, products),
    }
    rows = []
    for name, s in all_scores.items():
        for segment, mask in [("All", np.ones(len(cold), bool)), ("Cold start", cold), ("Has history", ~cold)]:
            rows.append({"segment": segment, "model": name, "customers": int(mask.sum()),
                         **evaluate(s[mask], val_masked[mask].reset_index(drop=True), products)})
    metrics = pd.DataFrame(rows)
    print(metrics.set_index(["segment", "model"]).round(3))

    reports = Path(args.out_dir) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(reports / f"{args.version}_metrics.csv", index=False)

    path = save_bundle(
        Path(args.out_dir) / "models" / f"{args.version}.joblib",
        model=model, encoder=encoder, products=products, model_version=args.version,
        metrics=metrics.to_dict(orient="records"),
        data_info={"source": str(args.data), "rows": len(df), "training_customers": len(inner_c)},
    )
    print(f"Saved {path}")


if __name__ == "__main__":
    main()