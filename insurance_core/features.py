"""Turning customer profiles into model inputs.

ProfileEncoder lives here, in a proper module, so a saved model can always find it:
joblib/pickle stores a class by its import path (insurance_core.features.ProfileEncoder),
not by its code. A class defined in a notebook has the path __main__.ProfileEncoder,
which no other program can import.
"""
import numpy as np
import pandas as pd

MODEL_PRODUCTS = ["MTP", "MCP", "HIN", "HFM", "TRV", "HCN", "SHP"]   # products the model was trained on

CAT_COLS = ["gender", "marital_status", "state", "geo_zone", "area_type", "occupation",
            "occupation_category", "vehicle_type", "vehicle_use", "home_status", "risk_appetite"]
NUM_COLS = ["age", "dependents", "monthly_income_ngn", "vehicle_year", "vehicle_value_ngn",
            "property_value_ngn", "foreign_trips_per_year"]
BOOL_COLS = ["employer_hmo", "smoker", "pre_existing_condition", "owns_vehicle", "runs_shop"]
# Deliberately NOT features: customer_id, full_name, phone, email, data_source


class ProfileEncoder:
    """Learns category lists from training data, then encodes any profile the same way."""

    def __init__(self, cat_cols=CAT_COLS, num_cols=NUM_COLS, bool_cols=BOOL_COLS):
        self.cat_cols, self.num_cols, self.bool_cols = list(cat_cols), list(num_cols), list(bool_cols)

    def fit(self, df: pd.DataFrame) -> "ProfileEncoder":
        self.categories_ = {c: sorted(df[c].dropna().unique()) for c in self.cat_cols}
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=df.index)
        for c in self.cat_cols:
            out[c] = pd.Categorical(df[c], categories=self.categories_[c])   # unseen values -> NaN
        for c in self.num_cols:
            out[c] = pd.to_numeric(df[c], errors="coerce")
        for c in self.bool_cols:
            out[c] = pd.to_numeric(df[c].map({True: 1.0, False: 0.0}), errors="coerce")
        return out.reset_index(drop=True)


def build_features(df: pd.DataFrame, encoder: ProfileEncoder, products=MODEL_PRODUCTS) -> pd.DataFrame:
    """Profile features + current holdings (columns prefixed owns_)."""
    holdings = df.reindex(columns=products, fill_value=0).fillna(0).astype(int).reset_index(drop=True)
    return pd.concat([encoder.transform(df), holdings.add_prefix("owns_")], axis=1)


def profile_to_frame(profile: dict, products=MODEL_PRODUCTS) -> pd.DataFrame:
    """One profile dict -> one-row DataFrame with every product column present (0 if not owned)."""
    row = pd.DataFrame([profile])
    for p in products:
        row[p] = int(profile.get(p) or 0)
    return row


def expand_leave_one_out(df: pd.DataFrame, products=MODEL_PRODUCTS):
    """One row per (customer, owned product), with that product hidden and used as the target."""
    matrix = df[products].to_numpy()
    cust_idx, prod_idx = np.nonzero(matrix)
    expanded = df.iloc[cust_idx].reset_index(drop=True).copy()
    owned = matrix[cust_idx].copy()
    owned[np.arange(len(cust_idx)), prod_idx] = 0
    expanded[products] = owned
    return expanded, np.array(products)[prod_idx]