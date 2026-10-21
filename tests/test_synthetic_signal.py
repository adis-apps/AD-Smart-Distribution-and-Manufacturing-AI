import pandas as pd
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"

def test_seed_data_has_intentional_price_outcome_signal():
    df = pd.read_csv(DATA / "quote_history.csv")
    rel = (df["quoted_price"] - df["competitor_price"]) / df["competitor_price"]
    # In the generator's intended synthetic process, quoting further above
    # competitor should reduce win probability on average.
    assert rel.corr(df["won"]) < -0.15
    assert df["won"].nunique() == 2

def test_credit_hold_has_expected_direction_in_seed_data():
    df = pd.read_csv(DATA / "quote_history.csv")
    held = df.loc[df["credit_hold"].astype(int) == 1, "won"].mean()
    not_held = df.loc[df["credit_hold"].astype(int) == 0, "won"].mean()
    assert held < not_held
