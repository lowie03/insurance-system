"""Offline evaluation: hide one owned product per customer, check where it ranks."""
import numpy as np
import pandas as pd


def hide_one_product(df: pd.DataFrame, products, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    matrix = df[products].to_numpy().copy()
    hidden = []
    for row in matrix:
        pick = rng.choice(np.flatnonzero(row))
        row[pick] = 0
        hidden.append(products[pick])
    masked = df.copy()
    masked[products] = matrix
    masked["hidden_product"] = hidden
    return masked


def evaluate(score_matrix: np.ndarray, masked_df: pd.DataFrame, products) -> dict:
    """Hit@1, Hit@3 and MRR of the hidden product. Already-owned products are never recommended."""
    scores = score_matrix.astype(float).copy()
    scores[masked_df[products].to_numpy() == 1] = -np.inf
    ranking = np.argsort(-scores, axis=1)
    target = masked_df["hidden_product"].map(list(products).index).to_numpy()
    rank = (ranking == target[:, None]).argmax(axis=1) + 1
    return {"Hit@1": float(np.mean(rank <= 1)), "Hit@3": float(np.mean(rank <= 3)),
            "MRR": float(np.mean(1 / rank))}


def scores_from_model(model, X: pd.DataFrame, products) -> np.ndarray:
    """predict_proba only has columns for classes seen in training; map them back into `products` order."""
    proba = model.predict_proba(X)
    scores = np.zeros((len(X), len(products)))
    for col, cls in enumerate(model.classes_):
        scores[:, list(products).index(cls)] = proba[:, col]
    return scores


def popularity_scores(train_df: pd.DataFrame, n_rows: int, products) -> np.ndarray:
    return np.tile(train_df[products].mean().to_numpy(), (n_rows, 1))


def cooccurrence_scores(train_df: pd.DataFrame, masked_df: pd.DataFrame, products) -> np.ndarray:
    matrix = train_df[products].to_numpy().astype(float)
    together = matrix.T @ matrix
    cond = together / np.maximum(np.diag(together)[:, None], 1)
    np.fill_diagonal(cond, 0)
    popularity = train_df[products].mean().to_numpy()
    return masked_df[products].to_numpy().astype(float) @ cond + 1e-6 * popularity