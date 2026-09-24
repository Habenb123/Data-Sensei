"""Plotly chart builder and parser for DataCrew responses.
"""

from __future__ import annotations
import json
import re
from typing import Optional, Dict, Any
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def extract_chart_spec(report_text: str) -> Optional[Dict[str, Any]]:
    try:
        pattern = r"```(?:chart_spec|json)\s*(\{.*?\})\s*```"
        match = re.search(pattern, report_text, re.DOTALL | re.IGNORECASE)
        if match:
            return json.loads(match.group(1).strip())
    except Exception:
        pass
    return None


def extract_sql_query(report_text: str) -> Optional[str]:
    try:
        pattern = r"```sql\s*(.*?)\s*```"
        match = re.search(pattern, report_text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return None


def render_plotly_chart(df: pd.DataFrame, chart_spec: Optional[Dict[str, Any]] = None) -> Optional[go.Figure]:
    if df is None or df.empty or len(df.columns) < 1:
        return None

    cols = list(df.columns)
    chart_type = "bar"
    title = "Data Visualization"
    x_col = cols[0]
    y_col = cols[1] if len(cols) > 1 else cols[0]
    color_col = None

    if chart_spec and isinstance(chart_spec, dict):
        chart_type = chart_spec.get("chart_type", "bar").lower()
        title = chart_spec.get("title", title)
        col_map = {c.lower(): c for c in cols}
        if chart_spec.get("x_col") and str(chart_spec["x_col"]).lower() in col_map:
            x_col = col_map[str(chart_spec["x_col"]).lower()]
        if chart_spec.get("y_col"):
            spec_y = chart_spec["y_col"]
            if isinstance(spec_y, list):
                valid = [col_map[str(y).lower()] for y in spec_y if str(y).lower() in col_map]
                if valid:
                    y_col = valid if len(valid) > 1 else valid[0]
            elif str(spec_y).lower() in col_map:
                y_col = col_map[str(spec_y).lower()]
        if chart_spec.get("color_col") and str(chart_spec["color_col"]).lower() in col_map:
            color_col = col_map[str(chart_spec["color_col"]).lower()]

    try:
        template = "plotly_dark"
        if chart_type in ["line", "trend"]:
            fig = px.line(df, x=x_col, y=y_col, color=color_col, markers=True, title=title, template=template)
        elif chart_type in ["scatter"]:
            fig = px.scatter(df, x=x_col, y=y_col, color=color_col, title=title, template=template)
        elif chart_type in ["pie", "donut"]:
            fig = px.pie(df, names=x_col, values=y_col, title=title, template=template)
        else:
            fig = px.bar(df, x=x_col, y=y_col, color=color_col, title=title, template=template)

        fig.update_layout(
            margin=dict(l=20, r=20, t=50, b=20),
            title_font=dict(size=15, family="Arial, sans-serif")
        )
        return fig
    except Exception:
        try:
            if len(cols) >= 2:
                return px.bar(df, x=cols[0], y=cols[1], title=title, template="plotly_dark")
        except Exception:
            pass
        return None
