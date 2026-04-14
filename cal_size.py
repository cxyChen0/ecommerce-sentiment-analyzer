import pandas as pd

df = pd.read_csv("cleaned_snack.csv", encoding="utf-8-sig")
print(len(df))