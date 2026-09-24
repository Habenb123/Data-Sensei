"""FastAPI Application for DataPilot / DataCrew.
Full-featured Analytics Workspace backend supporting multi-agent analysis, auto-EDA, dynamic dashboards, and report generation.
"""

from __future__ import annotations
import os
import shutil
import json
import time
import pandas as pd
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, File, UploadFile, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel
import requests

from src.database.duckdb_manager import DuckDBManager
from src.agents.lightweight_crew import LightweightDataCrew

app = FastAPI(title="DataPilot // AI Data Analyst Workspace")

# In-memory shared database instance
db_manager = DuckDBManager(table_name="dataset")

# Static files directory
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class AnalyzeRequest(BaseModel):
    question: str
    provider: str = "Ollama (Local)"
    model_name: str = "qwen2.5-coder:14b"
    api_key: Optional[str] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None


class SQLRequest(BaseModel):
    sql: str


class ReportRequest(BaseModel):
    dataset_name: str
    saved_insights: List[Dict[str, Any]]
    notes: Optional[str] = ""


@app.get("/", response_class=HTMLResponse)
async def index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return "<h1>DataPilot static files loading...</h1>"


@app.get("/api/dataset-info")
async def get_dataset_info():
    if not db_manager.loaded:
        return {"loaded": False}
    profile = db_manager.get_detailed_schema_profile()
    preview_df = db_manager.get_dataframe_preview(8)
    if not preview_df.empty:
        try:
            preview_records = json.loads(preview_df.to_json(orient="records", date_format="iso"))
        except Exception:
            preview_records = preview_df.fillna("").to_dict(orient="records")
    else:
        preview_records = []

    return {
        "loaded": True,
        "filename": db_manager.source_filename,
        "file_size_mb": db_manager.file_size_mb,
        "row_count": db_manager.row_count,
        "column_count": db_manager.column_count,
        "profile": profile,
        "preview": preview_records
    }


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        # File type validation
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in [".csv", ".parquet", ".xlsx", ".xls"]:
            raise HTTPException(status_code=400, detail="Invalid format. Supported formats: .csv, .parquet, .xlsx, .xls")

        temp_dir = os.path.join(os.path.dirname(__file__), "temp_uploads")
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, file.filename)

        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = os.path.getsize(temp_path)
        success, msg = db_manager.load_file(temp_path, file.filename, file_size)

        try:
            os.remove(temp_path)
        except Exception:
            pass

        if not success:
            raise HTTPException(status_code=400, detail=msg)

        return await get_dataset_info()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File processing error: {str(e)}")


@app.post("/api/load-sample")
async def load_sample():
    sample_path = os.path.join(os.path.dirname(__file__), "sample_data", "ecommerce_sales.csv")
    if not os.path.exists(sample_path):
        raise HTTPException(status_code=404, detail="Sample dataset not found.")

    file_size = os.path.getsize(sample_path)
    success, msg = db_manager.load_file(sample_path, "ecommerce_sales.csv", file_size)
    if not success:
        raise HTTPException(status_code=500, detail=msg)

    return await get_dataset_info()


@app.post("/api/reset-dataset")
async def reset_dataset():
    global db_manager
    db_manager = DuckDBManager(table_name="dataset")
    return {"loaded": False, "message": "Dataset reset successfully."}


@app.get("/api/dashboard-kpis")
async def get_dashboard_kpis():
    if not db_manager.loaded:
        raise HTTPException(status_code=400, detail="No dataset loaded.")
    return db_manager.get_dashboard_kpis()


@app.get("/api/auto-eda")
async def get_auto_eda():
    if not db_manager.loaded:
        raise HTTPException(status_code=400, detail="No dataset loaded.")
    return db_manager.get_auto_eda_data()


@app.get("/api/suggest-questions")
async def get_suggested_questions():
    if not db_manager.loaded:
        return {"suggestions": []}
    crew = LightweightDataCrew(db_manager=db_manager)
    return {"suggestions": crew.generate_suggested_questions()}


@app.get("/api/ollama-models")
async def list_ollama_models():
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        if resp.status_code == 200:
            models = [m.get("name") for m in resp.json().get("models", [])]
            return {"online": True, "models": models}
    except Exception:
        pass
    return {"online": False, "models": ["qwen2.5-coder:14b", "qwen2.5:7b", "llama3.1"]}


class CustomChartRequest(BaseModel):
    x_col: str
    y_col: str
    agg_func: str = "SUM"
    chart_type: str = "bar"


@app.get("/api/visualizations-gallery")
async def get_visualizations_gallery():
    if not db_manager.loaded:
        raise HTTPException(status_code=400, detail="No dataset loaded.")
    return {
        "gallery": db_manager.get_visualizations_gallery(),
        "numeric_cols": db_manager.numeric_cols,
        "categorical_cols": db_manager.categorical_cols
    }


@app.post("/api/custom-chart")
async def generate_custom_chart(req: CustomChartRequest):
    if not db_manager.loaded:
        raise HTTPException(status_code=400, detail="No dataset loaded.")
    res = db_manager.build_custom_chart(req.x_col, req.y_col, req.agg_func, req.chart_type)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@app.post("/api/analyze")
async def analyze_data(req: AnalyzeRequest):
    if not db_manager.loaded:
        raise HTTPException(status_code=400, detail="Please upload a dataset first.")

    try:
        crew = LightweightDataCrew(
            db_manager=db_manager,
            provider=req.provider,
            model_name=req.model_name,
            api_key=req.api_key
        )
        result = crew.run_analysis(req.question, req.conversation_history)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/query-sql")
async def execute_raw_sql(req: SQLRequest):
    if not db_manager.loaded:
        raise HTTPException(status_code=400, detail="No dataset loaded.")

    df, exec_time, error = db_manager.execute_query(req.sql)
    if error:
        return {"success": False, "error": error, "exec_time": round(exec_time, 4)}

    if df is not None and not df.empty:
        try:
            rows = json.loads(df.to_json(orient="records", date_format="iso"))
        except Exception:
            rows = df.fillna("").to_dict(orient="records")
    else:
        rows = []

    return {
        "success": True,
        "exec_time": round(exec_time, 4),
        "row_count": len(df) if df is not None else 0,
        "columns": list(df.columns) if df is not None else [],
        "rows": rows
    }


@app.post("/api/generate-report")
async def generate_executive_report(req: ReportRequest):
    """Compiles saved insights and dataset metrics into a clean, printable HTML report."""
    if not db_manager.loaded:
        raise HTTPException(status_code=400, detail="No dataset loaded.")

    profile = db_manager.get_detailed_schema_profile()

    insights_html = ""
    for idx, ins in enumerate(req.saved_insights, 1):
        findings_bullets = "".join([f"<li style='margin-bottom:6px;'>{f}</li>" for f in ins.get("key_findings", [])])
        insights_html += f"""
        <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:20px; margin-bottom:24px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <h3 style="margin:0; font-size:16px; color:#0f172a;">#{idx}: {ins.get('question')}</h3>
                <span style="font-family:monospace; font-size:12px; color:#64748b;">{ins.get('time', '')}</span>
            </div>
            <p style="font-size:14px; color:#334155; line-height:1.6; margin-bottom:12px;"><strong>Summary:</strong> {ins.get('summary', '')}</p>
            <div style="margin-bottom:12px;">
                <strong style="font-size:13px; color:#0f172a;">Key Findings:</strong>
                <ul style="margin:8px 0 0 20px; color:#475569; font-size:13px;">{findings_bullets}</ul>
            </div>
            <div style="background:#0f172a; color:#38bdf8; font-family:monospace; font-size:12px; padding:12px; border-radius:8px; overflow-x:auto;">
                <code>{ins.get('sql', '')}</code>
            </div>
        </div>
        """

    report_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>DataSensei Executive Intelligence Report - {req.dataset_name} 🥋</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1e293b; line-height: 1.6; padding: 40px; max-width: 900px; margin: 0 auto; background: #ffffff; }}
        .header {{ border-bottom: 2px solid #e11d48; padding-bottom: 20px; margin-bottom: 30px; display: flex; justify-content: space-between; align-items: flex-end; }}
        .badge {{ background: #e11d48; color: white; font-family: monospace; font-size: 11px; padding: 4px 8px; border-radius: 4px; font-weight: bold; }}
        .stat-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 30px; }}
        .stat-card {{ background: #f1f5f9; padding: 16px; border-radius: 8px; text-align: center; }}
        .stat-val {{ font-size: 20px; font-weight: bold; color: #0f172a; }}
        .stat-lbl {{ font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 600; margin-top: 4px; }}
        @media print {{ body {{ padding: 0; }} }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <span class="badge">🥋 DATA SENSEI // SENSE AI</span>
            <h1 style="margin: 8px 0 0 0; font-size: 28px; color: #0f172a;">Executive Intelligence Report</h1>
            <p style="margin: 4px 0 0 0; color: #64748b; font-size: 13px;">Dataset: {req.dataset_name} · Generated on {time.strftime('%B %d, %Y at %H:%M')}</p>
        </div>
    </div>

    <div class="stat-grid">
        <div class="stat-card">
            <div class="stat-val">{profile.get('total_rows', 0):,}</div>
            <div class="stat-lbl">Total Records</div>
        </div>
        <div class="stat-card">
            <div class="stat-val">{profile.get('total_cols', 0)}</div>
            <div class="stat-lbl">Total Columns</div>
        </div>
        <div class="stat-card">
            <div class="stat-val">{len(req.saved_insights)}</div>
            <div class="stat-lbl">Saved Insights</div>
        </div>
        <div class="stat-card">
            <div class="stat-val">{profile.get('duplicate_pct', 0)}%</div>
            <div class="stat-lbl">Duplicate Rate</div>
        </div>
    </div>

    <h2 style="font-size: 20px; color: #0f172a; margin-top: 30px; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px;">Saved Analytical Insights ({len(req.saved_insights)})</h2>
    {insights_html if req.saved_insights else "<p style='color:#64748b;'>No insights saved in this session.</p>"}

    <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; text-align: center;">
        "With big data comes big responsibilities." 🕷️ · Generated by DataSensei AI Master & DuckDB Engine.
    </div>
</body>
</html>
"""
    return HTMLResponse(content=report_html)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Launching DataSensei Workspace on port {port} ...")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
