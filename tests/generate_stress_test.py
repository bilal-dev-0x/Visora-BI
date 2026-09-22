import pandas as pd
import numpy as np

rng = np.random.default_rng(42)

# 10,000 normal rows
n = 10000

dates = pd.date_range("2023-01-01", "2025-12-31", freq="D")
date_col = rng.choice(dates, n).astype(str)

products = rng.choice(
    ["Alpha Widget", "Beta Device", "Gamma Kit", "Delta Pro", "Epsilon Mini"],
    n
)

segments = rng.choice(
    ["Consumer", "SMB", "Enterprise", "Government"],
    n
)

locations = rng.choice(
    ["Lahore", "Karachi", "Islamabad", "Faisalabad",
     "Multan", "Peshawar", "Quetta"],
    n
)

channels = rng.choice(
    ["Online", "Retail", "Partner", "Direct"],
    n
)

units = rng.poisson(20, n).astype(float)
units = np.maximum(units, 1)

revenue = units * rng.normal(1850, 280, n)
cost = revenue * rng.uniform(0.48, 0.88, n)
discount = rng.uniform(0, 30, n)
margin = revenue - cost

df = pd.DataFrame({
    "Date": date_col,
    "Product": products,
    "Segment": segments,
    "Location": locations,
    "Channel": channels,
    "Units": units,
    "Revenue": revenue,
    "Cost": cost,
    "DiscountPct": discount,
    "Margin": margin,
})

# =========================================================
# 1. MASSIVE OUTLIERS
# =========================================================

outliers = rng.choice(n, 25, replace=False)

df.loc[outliers[:10], "Units"] = rng.integers(500, 3000, 10)
df.loc[outliers[:10], "Revenue"] = (
    df.loc[outliers[:10], "Units"]
    * rng.integers(5000, 12000, 10)
)

df.loc[outliers[10:20], "Revenue"] *= rng.integers(8, 20, 10)

# Zero values
df.loc[outliers[20:], "Units"] = 0


# =========================================================
# 2. NEGATIVE VALUES
# =========================================================

negative_rows = rng.choice(
    np.setdiff1d(np.arange(n), outliers),
    15,
    replace=False
)

df.loc[negative_rows, "Revenue"] = -rng.uniform(
    100, 5000, len(negative_rows)
)


# =========================================================
# 3. MISSING VALUES
# =========================================================

for column, amount in [
    ("Units", 90),
    ("Revenue", 80),
    ("Cost", 70),
    ("DiscountPct", 60),
    ("Product", 35),
    ("Segment", 25),
    ("Location", 20),
]:
    indexes = rng.choice(n, amount, replace=False)
    df.loc[indexes, column] = np.nan


# =========================================================
# 4. NaN / INFINITY
# =========================================================

special = rng.choice(n, 12, replace=False)

df.loc[special[:4], "Revenue"] = np.inf
df.loc[special[4:8], "Revenue"] = -np.inf
df.loc[special[8:], "Margin"] = np.inf


# =========================================================
# 5. BAD / MISSING DATES
# =========================================================

bad_dates = rng.choice(n, 8, replace=False)

df.loc[bad_dates[:3], "Date"] = "not-a-date"
df.loc[bad_dates[3:5], "Date"] = "2024-99-99"
df.loc[bad_dates[5:], "Date"] = ""


# =========================================================
# 6. HIGH-CARDINALITY DIMENSION
# =========================================================

df["TransactionID"] = [
    f"TX-{i:06d}-{rng.integers(100000, 999999)}"
    for i in range(n)
]


# =========================================================
# 7. GENUINE 8-DIGIT ID
#    Tests whether Visora incorrectly thinks it's a date
# =========================================================

df["CustomerID_8Digit"] = rng.integers(
    10000000,
    99999999,
    n
)


# =========================================================
# 8. ALMOST CONSTANT COLUMN
# =========================================================

df["TaxRate"] = 15.0

changes = rng.choice(n, 25, replace=False)

df.loc[changes, "TaxRate"] = rng.choice(
    [0.0, 5.0, 18.0],
    len(changes)
)


# =========================================================
# 9. DUPLICATE ROWS
# =========================================================

duplicates = df.iloc[
    rng.choice(df.index, 40, replace=False)
].copy()

df = pd.concat(
    [df, duplicates],
    ignore_index=True
)


# =========================================================
# 10. SHUFFLE EVERYTHING
# =========================================================

df = df.sample(
    frac=1,
    random_state=42
).reset_index(drop=True)


# =========================================================
# SAVE
# =========================================================

df.to_csv(
    "visora_stress_test.csv",
    index=False
)

print("======================================")
print(" VISORA STRESS TEST CREATED")
print("======================================")
print(f"Rows    : {len(df)}")
print(f"Columns : {len(df.columns)}")
print()
print("File: visora_stress_test.csv")