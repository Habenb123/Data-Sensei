"""DuckDB Manager module for DataCrew / DataPilot.
Handles safe query execution, read-only SQL validation, schema profiling, and automated EDA calculations.
"""

from __future__ import annotations
import os
import re
import time
import duckdb
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, Optional, List


class DuckDBManager:
    """Manages an in-memory DuckDB instance with robust profiling and safe analytical querying."""

    def __init__(self, table_name: str = "dataset"):
        self.table_name = table_name
        self.conn = duckdb.connect(database=":memory:", read_only=False)
        self.loaded = False
        self.source_filename = ""
        self.file_size_mb = 0.0
        self.row_count = 0
        self.column_count = 0
        self.numeric_cols: List[str] = []
        self.categorical_cols: List[str] = []
        self.date_cols: List[str] = []

    def load_file(self, file_path_or_buffer: Any, filename: str, file_size_bytes: int = 0) -> Tuple[bool, str]:
        """Ingests CSV, Parquet, or Excel files into DuckDB."""
        try:
            self.source_filename = filename
            self.file_size_mb = round(file_size_bytes / (1024 * 1024), 2) if file_size_bytes > 0 else 0.5
            ext = os.path.splitext(filename)[1].lower()

            if ext == ".csv":
                if isinstance(file_path_or_buffer, str):
                    self.conn.execute(
                        f"CREATE OR REPLACE TABLE {self.table_name} AS SELECT * FROM read_csv_auto('{file_path_or_buffer}')"
                    )
                else:
                    df = pd.read_csv(file_path_or_buffer)
                    self.conn.register("temp_df", df)
                    self.conn.execute(f"CREATE OR REPLACE TABLE {self.table_name} AS SELECT * FROM temp_df")
                    self.conn.unregister("temp_df")

            elif ext == ".parquet":
                if isinstance(file_path_or_buffer, str):
                    self.conn.execute(
                        f"CREATE OR REPLACE TABLE {self.table_name} AS SELECT * FROM read_parquet('{file_path_or_buffer}')"
                    )
                else:
                    df = pd.read_parquet(file_path_or_buffer)
                    self.conn.register("temp_df", df)
                    self.conn.execute(f"CREATE OR REPLACE TABLE {self.table_name} AS SELECT * FROM temp_df")
                    self.conn.unregister("temp_df")

            elif ext in [".xlsx", ".xls"]:
                df = pd.read_excel(file_path_or_buffer)
                self.conn.register("temp_df", df)
                self.conn.execute(f"CREATE OR REPLACE TABLE {self.table_name} AS SELECT * FROM temp_df")
                self.conn.unregister("temp_df")

            else:
                return False, f"Unsupported format: '{ext}'. Please upload a CSV, Excel, or Parquet file."

            # Update row count and columns
            res = self.conn.execute(f"SELECT COUNT(*) FROM {self.table_name}").fetchone()
            self.row_count = res[0] if res else 0

            cols_meta = self.conn.execute(f"DESCRIBE {self.table_name}").fetchall()
            self.column_count = len(cols_meta)
            self._categorize_columns(cols_meta)
            self.loaded = True

            return True, f"Successfully loaded '{filename}' ({self.row_count:,} rows, {self.column_count} columns)."

        except Exception as e:
            self.loaded = False
            return False, f"Failed to load dataset: {str(e)}"

    def _categorize_columns(self, cols_meta: List[Tuple]):
        """Categorizes columns into numeric, categorical, and date/time."""
        self.numeric_cols = []
        self.categorical_cols = []
        self.date_cols = []

        for col_name, col_type, *_ in cols_meta:
            ctype = str(col_type).upper()
            if any(t in ctype for t in ["INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "BIGINT", "HUGEINT"]):
                self.numeric_cols.append(col_name)
            elif any(t in ctype for t in ["DATE", "TIME", "TIMESTAMP"]):
                self.date_cols.append(col_name)
            else:
                # Check if text column might be a date
                if "date" in col_name.lower() or "time" in col_name.lower() or "day" in col_name.lower():
                    self.date_cols.append(col_name)
                else:
                    self.categorical_cols.append(col_name)

    def validate_sql_security(self, sql_query: str) -> Tuple[bool, Optional[str]]:
        """Restricts SQL to read-only analytical operations (SELECT, WITH)."""
        forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "CREATE", "ATTACH", "DETACH", "COPY", "EXPORT", "IMPORT", "PRAGMA", "LOAD", "INSTALL"]
        cleaned = re.sub(r"--.*$", "", sql_query, flags=re.MULTILINE)
        cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL).strip()

        words = [w.strip().upper() for w in re.split(r"[\s;(),]+", cleaned) if w.strip()]
        for f in forbidden:
            if f in words:
                return False, f"Security Violation: Query contains forbidden operational command '{f}'. Only read-only analytical queries are permitted."

        if not cleaned.upper().startswith(("SELECT", "WITH", "DESCRIBE", "EXPLAIN", "SUMMARIZE")):
            return False, "Security Violation: Query must begin with a SELECT or WITH analytical statement."

        return True, None

    def execute_query(self, sql_query: str) -> Tuple[Optional[pd.DataFrame], float, Optional[str]]:
        """Safely executes SQL query against DuckDB."""
        if not self.loaded:
            return None, 0.0, "No dataset loaded into DuckDB."

        # Clean SQL markdown syntax
        cleaned_sql = sql_query.strip()
        if cleaned_sql.startswith("```sql"):
            cleaned_sql = cleaned_sql[6:]
        elif cleaned_sql.startswith("```"):
            cleaned_sql = cleaned_sql[3:]
        if cleaned_sql.endswith("```"):
            cleaned_sql = cleaned_sql[:-3]
        cleaned_sql = cleaned_sql.strip()

        # Security check
        is_safe, sec_error = self.validate_sql_security(cleaned_sql)
        if not is_safe:
            return None, 0.0, sec_error

        start_time = time.perf_counter()
        try:
            df = self.conn.execute(cleaned_sql).df()
            exec_time = time.perf_counter() - start_time
            return df, exec_time, None
        except Exception as e:
            exec_time = time.perf_counter() - start_time
            return None, exec_time, str(e)

    def get_detailed_schema_profile(self) -> Dict[str, Any]:
        """Computes comprehensive schema statistics for the Dataset Overview."""
        if not self.loaded:
            return {}

        df = self.get_full_dataframe()
        total_rows = len(df)
        duplicate_rows = int(df.duplicated().sum())
        duplicate_pct = round((duplicate_rows / total_rows * 100), 2) if total_rows > 0 else 0.0

        schema_list = []
        issues = []
        missing_col_count = 0

        for col in df.columns:
            null_count = int(df[col].isnull().sum())
            null_pct = round((null_count / total_rows * 100), 2) if total_rows > 0 else 0.0
            if null_count > 0:
                missing_col_count += 1

            distinct_count = int(df[col].nunique())
            dtype = str(df[col].dtype)
            samples = [str(x) for x in df[col].dropna().unique()[:3]]

            schema_list.append({
                "column_name": col,
                "type": dtype,
                "null_count": null_count,
                "null_pct": null_pct,
                "distinct_count": distinct_count,
                "sample_values": ", ".join(samples)
            })

        if missing_col_count > 0:
            issues.append(f"{missing_col_count} columns contain missing values")
        else:
            issues.append("Zero missing values across all columns")

        if duplicate_rows > 0:
            issues.append(f"{duplicate_rows:,} duplicate rows detected ({duplicate_pct}%)")
        else:
            issues.append("No duplicate rows found")

        return {
            "total_rows": total_rows,
            "total_cols": len(df.columns),
            "file_size_mb": self.file_size_mb,
            "duplicate_rows": duplicate_rows,
            "duplicate_pct": duplicate_pct,
            "numeric_count": len(self.numeric_cols),
            "categorical_count": len(self.categorical_cols),
            "date_count": len(self.date_cols),
            "columns": schema_list,
            "quality_issues": issues
        }

    def get_auto_eda_data(self) -> Dict[str, Any]:
        """Generates comprehensive exploratory data analysis (distributions, top values, correlations)."""
        if not self.loaded:
            return {}

        df = self.get_full_dataframe()
        eda = {}

        # 1. Numeric Distributions
        numeric_summaries = []
        for col in self.numeric_cols[:6]:
            s = df[col].dropna()
            if not s.empty:
                numeric_summaries.append({
                    "column": col,
                    "mean": round(float(s.mean()), 2),
                    "std": round(float(s.std()), 2) if len(s) > 1 else 0.0,
                    "min": round(float(s.min()), 2),
                    "q25": round(float(s.quantile(0.25)), 2),
                    "median": round(float(s.median()), 2),
                    "q75": round(float(s.quantile(0.75)), 2),
                    "max": round(float(s.max()), 2),
                    "skew": round(float(s.skew()), 2) if len(s) > 2 else 0.0
                })
        eda["numeric_summaries"] = numeric_summaries

        # 2. Categorical Distributions (Top 5 values per column)
        cat_summaries = []
        for col in self.categorical_cols[:6]:
            counts = df[col].value_counts().head(5)
            cat_summaries.append({
                "column": col,
                "top_values": [{"label": str(k), "count": int(v), "pct": round(v / len(df) * 100, 1)} for k, v in counts.items()]
            })
        eda["categorical_summaries"] = cat_summaries

        # 3. Correlation Matrix
        if len(self.numeric_cols) >= 2:
            sub_num = self.numeric_cols[:8]
            corr = df[sub_num].corr().fillna(0).round(2)
            eda["correlation_matrix"] = {
                "columns": list(corr.columns),
                "data": corr.values.tolist()
            }
        else:
            eda["correlation_matrix"] = None

        return eda

    def get_dashboard_kpis(self) -> Dict[str, Any]:
        """Dynamically identifies top KPIs and high-level charts for the Dashboard mode."""
        if not self.loaded:
            return {}

        df = self.get_full_dataframe()
        kpis = []

        # Row count KPI
        kpis.append({"label": "Total Records", "value": f"{len(df):,}", "change": "Active Dataset", "positive": True})

        # Numeric sum/avg KPIs
        for col in self.numeric_cols[:3]:
            total_val = float(df[col].sum())
            avg_val = float(df[col].mean())
            if total_val > 1000:
                kpis.append({"label": f"Total {col.replace('_', ' ').title()}", "value": f"{total_val:,.2f}", "change": f"Avg: {avg_val:,.2f}", "positive": True})
            else:
                kpis.append({"label": f"Avg {col.replace('_', ' ').title()}", "value": f"{avg_val:,.2f}", "change": f"Max: {df[col].max():.2f}", "positive": True})

        # Top chart overview
        primary_cat = self.categorical_cols[0] if self.categorical_cols else None
        primary_num = self.numeric_cols[0] if self.numeric_cols else None
        overview_chart = None

        if primary_cat and primary_num:
            agg_df = df.groupby(primary_cat)[primary_num].sum().reset_index().sort_values(by=primary_num, ascending=False).head(8)
            overview_chart = {
                "title": f"{primary_num.title()} by {primary_cat.title()}",
                "labels": agg_df[primary_cat].astype(str).tolist(),
                "values": agg_df[primary_num].round(2).tolist(),
                "x_label": primary_cat,
                "y_label": primary_num
            }

        return {
            "kpis": kpis[:4],
            "overview_chart": overview_chart
        }

    def get_schema_summary(self) -> str:
        """Returns a concise schema summary string for LLMs."""
        if not self.loaded:
            return "No dataset loaded."

        schema_df = self.conn.execute(f"DESCRIBE {self.table_name}").df()
        preview_df = self.conn.execute(f"SELECT * FROM {self.table_name} LIMIT 3").df()

        schema_str = f"Table: `{self.table_name}` ({self.row_count:,} rows, {self.column_count} columns)\n"
        schema_str += f"Numeric Columns: {', '.join(self.numeric_cols) if self.numeric_cols else 'None'}\n"
        schema_str += f"Categorical Columns: {', '.join(self.categorical_cols) if self.categorical_cols else 'None'}\n"
        schema_str += f"Date/Time Columns: {', '.join(self.date_cols) if self.date_cols else 'None'}\n\nColumns & Types:\n"

        for _, row in schema_df.iterrows():
            col_name = row["column_name"]
            col_type = row["column_type"]
            samples = preview_df[col_name].dropna().tolist()[:3]
            sample_str = ", ".join([repr(s) for s in samples])
            schema_str += f"- `{col_name}` ({col_type}) | Samples: [{sample_str}]\n"

        return schema_str

    def get_visualizations_gallery(self) -> List[Dict[str, Any]]:
        """Generates 4 pre-built multidimensional visualization configurations."""
        if not self.loaded:
            return []

        df = self.get_full_dataframe()
        gallery = []

        # Chart 1: Primary Category vs Primary Numeric Sum
        if self.categorical_cols and self.numeric_cols:
            cat = self.categorical_cols[0]
            num = self.numeric_cols[0]
            agg = df.groupby(cat)[num].sum().reset_index().sort_values(by=num, ascending=False).head(10)
            gallery.append({
                "id": "gallery_1",
                "title": f"Total {num.replace('_', ' ').title()} by {cat.replace('_', ' ').title()}",
                "subtitle": f"Aggregated sum across {cat}",
                "type": "bar",
                "labels": agg[cat].astype(str).tolist(),
                "values": agg[num].round(2).tolist(),
                "label": num.title()
            })

        # Chart 2: Secondary Category or Donut Share
        cat2 = self.categorical_cols[1] if len(self.categorical_cols) > 1 else (self.categorical_cols[0] if self.categorical_cols else None)
        num_target = self.numeric_cols[0] if self.numeric_cols else None
        if cat2 and num_target:
            agg2 = df.groupby(cat2)[num_target].sum().reset_index().sort_values(by=num_target, ascending=False).head(6)
            gallery.append({
                "id": "gallery_2",
                "title": f"Distribution by {cat2.replace('_', ' ').title()}",
                "subtitle": f"Proportional share of {num_target}",
                "type": "doughnut",
                "labels": agg2[cat2].astype(str).tolist(),
                "values": agg2[num_target].round(2).tolist(),
                "label": num_target.title()
            })

        # Chart 3: Time Series / Date Trend if date column exists
        if self.date_cols and self.numeric_cols:
            dt = self.date_cols[0]
            num = self.numeric_cols[0]
            try:
                # Group by date
                agg_dt = df.groupby(dt)[num].sum().reset_index().sort_values(by=dt).head(15)
                gallery.append({
                    "id": "gallery_3",
                    "title": f"{num.replace('_', ' ').title()} Timeline Trend",
                    "subtitle": f"Chronological trend across {dt}",
                    "type": "line",
                    "labels": agg_dt[dt].astype(str).tolist(),
                    "values": agg_dt[num].round(2).tolist(),
                    "label": num.title()
                })
            except Exception:
                pass

        # Chart 4: Secondary Numeric or Profit/Average Metric
        if len(self.numeric_cols) >= 2 and self.categorical_cols:
            cat = self.categorical_cols[0]
            num2 = self.numeric_cols[1]
            agg4 = df.groupby(cat)[num2].mean().reset_index().sort_values(by=num2, ascending=False).head(8)
            gallery.append({
                "id": "gallery_4",
                "title": f"Average {num2.replace('_', ' ').title()} by {cat.replace('_', ' ').title()}",
                "subtitle": f"Mean calculation per category",
                "type": "bar",
                "labels": agg4[cat].astype(str).tolist(),
                "values": agg4[num2].round(2).tolist(),
                "label": f"Avg {num2.title()}"
            })

        return gallery

    def build_custom_chart(self, x_col: str, y_col: str, agg_func: str = "SUM", chart_type: str = "bar") -> Dict[str, Any]:
        """Calculates custom aggregated chart data directly in DuckDB."""
        if not self.loaded:
            return {}

        valid_aggs = ["SUM", "AVG", "COUNT", "MIN", "MAX"]
        agg = agg_func.upper() if agg_func.upper() in valid_aggs else "SUM"

        sql = f"SELECT {x_col}, ROUND({agg}({y_col}), 2) AS val FROM {self.table_name} GROUP BY 1 ORDER BY val DESC LIMIT 20"
        df, _, error = self.execute_query(sql)

        if error or df is None or df.empty:
            return {"error": error or "No data returned"}

        return {
            "title": f"{agg} of {y_col} by {x_col}",
            "type": chart_type,
            "labels": df[x_col].astype(str).tolist(),
            "values": df["val"].tolist(),
            "x_col": x_col,
            "y_col": y_col,
            "agg": agg
        }

    def get_dataframe_preview(self, limit: int = 10) -> pd.DataFrame:
        if not self.loaded:
            return pd.DataFrame()
        return self.conn.execute(f"SELECT * FROM {self.table_name} LIMIT {limit}").df()

    def get_full_dataframe(self) -> pd.DataFrame:
        if not self.loaded:
            return pd.DataFrame()
        return self.conn.execute(f"SELECT * FROM {self.table_name}").df()
