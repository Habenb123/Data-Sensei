"""Data Profiler module for dataset health check.
"""

from __future__ import annotations
from typing import Dict, Any
import pandas as pd


def profile_dataset(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {}

    total_rows = len(df)
    total_cols = len(df.columns)
    duplicate_rows = df.duplicated().sum()
    duplicate_pct = (duplicate_rows / total_rows * 100) if total_rows > 0 else 0

    col_profiles = []
    for col in df.columns:
        null_count = df[col].isnull().sum()
        null_pct = (null_count / total_rows * 100) if total_rows > 0 else 0
        distinct_count = df[col].nunique()
        dtype = str(df[col].dtype)

        col_profiles.append({
            "Column": col,
            "Type": dtype,
            "Distinct": distinct_count,
            "Missing Count": null_count,
            "Missing %": round(null_pct, 2)
        })

    col_df = pd.DataFrame(col_profiles)

    return {
        "total_rows": total_rows,
        "total_cols": total_cols,
        "duplicate_rows": duplicate_rows,
        "duplicate_pct": round(duplicate_pct, 2),
        "column_summary_df": col_df
    }
