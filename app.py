import pandas as pd

df = pd.read_csv("data/sales_data.csv")
df["Order Date"] = pd.to_datetime(df["Order Date"])

missing_values = df.isnull().sum(axis=0)
missing_rows = df.isnull().all(axis=1).sum()
duplicate = df.duplicated().sum()

# print(df.head())
# print(df.info())
# print(missing_values)
# print(missing_rows)
# print(duplicate)
# print(df.describe())

product_name = df["Product Name"].unique()
categories = df["Category"].unique()
regions = df["Region"].unique()

# print("\nUnique Product Names:\n", product_name)
# print("\nUnique Categories:\n", categories)
# print("\nUnique Regions:\n", regions)

print("\n" + "=" * 40)
print("        VISORA BI — DATA PROFILE")
print("=" * 40)

print(f"Rows              : {len(df)}")
print(f"Columns           : {len(df.columns)}")
print(f"Missing Values    : {missing_values.sum()}")
print(f"Duplicate Rows    : {duplicate}")

print(f"Products          : {len(product_name)}")
print(f"Categories        : {len(categories)}")
print(f"Regions           : {len(regions)}")

print(f"Earliest Date     : {df['Order Date'].min().date()}")
print(f"Latest Date       : {df['Order Date'].max().date()}")

print("=" * 40)