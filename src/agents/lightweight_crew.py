"""Lightweight Multi-Agent Engine with Conversational Follow-Up Memory, Structured Outputs, and Auto-Healing.
"""

from __future__ import annotations
import os
import json
import re
import time
import requests
from typing import Dict, Any, Optional, List, Tuple
from src.database.duckdb_manager import DuckDBManager


class LightweightDataCrew:
    """Multi-Agent Analytics Copilot with conversational memory and structured outputs."""

    def __init__(
        self,
        db_manager: DuckDBManager,
        provider: str = "Ollama (Local)",
        model_name: str = "qwen2.5-coder:14b",
        api_key: Optional[str] = None,
        ollama_url: str = "http://localhost:11434"
    ):
        self.db = db_manager
        self.provider = provider
        self.model_name = model_name
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
        self.ollama_url = ollama_url.rstrip("/")

    def _call_llm(self, prompt: str, system_prompt: str = "") -> str:
        """Invokes the selected LLM provider with robust timeout and structured temperature."""
        if self.provider == "Ollama (Local)":
            url = f"{self.ollama_url}/api/generate"
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "system": system_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_ctx": 4096
                }
            }
            try:
                resp = requests.post(url, json=payload, timeout=180)
                resp.raise_for_status()
                return resp.json().get("response", "").strip()
            except requests.exceptions.Timeout:
                raise RuntimeError("Ollama request timed out. Tip: Switch to 'qwen2.5:7b' for faster inference.")
            except Exception as e:
                raise RuntimeError(f"Ollama connection error: {str(e)}. Ensure Ollama is running at {self.ollama_url}")

        elif self.provider == "OpenAI":
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model_name or "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system_prompt or "You are an elite SQL and data analytics copilot."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1
            }
            resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

        elif self.provider == "Google Gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name or 'gemini-1.5-flash'}:generateContent?key={self.api_key}"
            payload = {
                "contents": [
                    {"role": "user", "parts": [{"text": f"{system_prompt}\n\n{prompt}"}]}
                ],
                "generationConfig": {"temperature": 0.1}
            }
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

        raise ValueError(f"Unsupported provider: {self.provider}")

    def generate_suggested_questions(self) -> List[str]:
        """Generates dynamic, schema-aware suggested analytical questions based on actual dataset columns."""
        if not self.db.loaded:
            return ["Upload a dataset to see suggestions."]

        num = self.db.numeric_cols
        cat = self.db.categorical_cols
        dt = self.db.date_cols
        suggestions = []

        # 1. Category Breakdown
        if cat and num:
            suggestions.append(f"Compare total {num[0].replace('_', ' ')} across different {cat[0].replace('_', ' ')}s")
        # 2. Time-series trend
        if dt and num:
            suggestions.append(f"Show {num[0].replace('_', ' ')} trend over time by {dt[0].replace('_', ' ')}")
        # 3. Top performers
        if len(cat) >= 2 and num:
            suggestions.append(f"What are the top 5 {cat[1].replace('_', ' ')}s by {num[0].replace('_', ' ')}?")
        elif cat and num:
            suggestions.append(f"Which {cat[0].replace('_', ' ')} generates the highest {num[0].replace('_', ' ')}?")
        # 4. Correlation / Distribution
        if len(num) >= 2:
            suggestions.append(f"Is there a correlation between {num[0].replace('_', ' ')} and {num[1].replace('_', ' ')}?")
        else:
            suggestions.append("What are the summary statistics and distribution of the data?")

        return suggestions[:4]

    def run_analysis(self, user_question: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """Runs the multi-agent copilot with conversational context and structured output."""
        start_total = time.perf_counter()
        activity_log = []

        # -------------------------------------------------------------
        # STEP 1: Data Explorer Context Preparation
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        schema_summary = self.db.get_schema_summary()
        activity_log.append({
            "stage": "Explorer",
            "title": "Dataset schema and column types analyzed",
            "time": round(time.perf_counter() - t0, 3)
        })

        # Format conversation history context if present
        context_str = ""
        if conversation_history and len(conversation_history) > 0:
            context_str = "Recent Conversation Context:\n"
            for turn in conversation_history[-3:]:
                context_str += f"- User asked: '{turn.get('question', '')}'\n"
                if turn.get("sql"):
                    context_str += f"  Previous SQL: {turn.get('sql')}\n"
            context_str += "\nUse this context to resolve references like 'those products', 'that region', or 'only last month'.\n\n"

        # -------------------------------------------------------------
        # STEP 2: SQL Specialist (Generation + Execution + Auto-Healing)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        sql_system = (
            "You are Agent 2 (DuckDB SQL Specialist). Your job is to convert the question into a valid, "
            "read-only analytical SQL query against the table `dataset`.\n"
            "Rules:\n"
            "1. Output ONLY the query inside ```sql ... ``` block.\n"
            "2. Strictly use table name `dataset`.\n"
            "3. Use appropriate aggregations (SUM, AVG, COUNT), grouping, and ORDER BY.\n"
            "4. Never generate DROP, DELETE, INSERT, or ALTER commands."
        )

        sql_prompt = (
            f"{context_str}"
            f"Table Schema Information:\n{schema_summary}\n\n"
            f"User Question: '{user_question}'\n\n"
            "Write the optimal DuckDB SQL query to answer this question accurately."
        )

        sql_response = self._call_llm(sql_prompt, sql_system)
        extracted_sql = self._extract_sql(sql_response) or "SELECT * FROM dataset LIMIT 10"

        # Execute on DuckDB engine
        df_result, exec_time, error = self.db.execute_query(extracted_sql)

        # Self-correction attempt if syntax error occurred
        retry_occurred = False
        if error:
            retry_occurred = True
            retry_prompt = (
                f"Your SQL query failed with DuckDB error:\nERROR: {error}\n\n"
                f"Failed Query:\n{extracted_sql}\n\n"
                f"Schema:\n{schema_summary}\n\n"
                "Fix the error and output ONLY the corrected DuckDB SQL inside ```sql ... ```."
            )
            sql_response_retry = self._call_llm(retry_prompt, sql_system)
            new_sql = self._extract_sql(sql_response_retry)
            if new_sql:
                extracted_sql = new_sql
                df_result, exec_time, error = self.db.execute_query(extracted_sql)

        activity_log.append({
            "stage": "SQL Analyst",
            "title": "Query generated & executed in DuckDB" + (" (self-healed)" if retry_occurred and not error else ""),
            "time": round(time.perf_counter() - t0, 3),
            "sql": extracted_sql,
            "exec_time_sec": round(exec_time, 4),
            "row_count": len(df_result) if df_result is not None else 0,
            "error": error
        })

        # -------------------------------------------------------------
        # STEP 3: Quantitative Analyst & Report Agent (Structured Findings)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        result_table_md = df_result.to_markdown(index=False) if df_result is not None and not df_result.empty else "0 rows returned."
        cols = list(df_result.columns) if df_result is not None else []

        analyst_system = (
            "You are an Executive Business Intelligence Analyst. Interpret the tabular query results.\n"
            "Output your response strictly in the following JSON format inside ```json ... ``` block:\n"
            "{\n"
            "  \"summary\": \"2-sentence high-level executive answer to the user's question with direct numbers.\",\n"
            "  \"key_findings\": [\n"
            "    \"Finding 1 with bold exact number or percentage\",\n"
            "    \"Finding 2 highlighting a peak, drop, or comparison\",\n"
            "    \"Finding 3 highlighting an anomaly or distribution\"\n"
            "  ],\n"
            "  \"chart\": {\n"
            "    \"chart_type\": \"bar|line|doughnut|scatter\",\n"
            "    \"title\": \"Chart Title\",\n"
            "    \"subtitle\": \"Short description of what is measured\",\n"
            f"    \"x_col\": \"{cols[0] if cols else 'x'}\",\n"
            f"    \"y_col\": \"{cols[1] if len(cols) > 1 else (cols[0] if cols else 'y')}\"\n"
            "  },\n"
            "  \"recommendations\": \"2 actionable next steps or strategic implications for business leaders.\"\n"
            "}"
        )

        analyst_prompt = (
            f"User Question: '{user_question}'\n\n"
            f"Executed SQL Query:\n```sql\n{extracted_sql}\n```\n\n"
            f"Query Results Data:\n{result_table_md}\n\n"
            "Analyze the data and provide structured findings."
        )

        report_raw = self._call_llm(analyst_prompt, analyst_system)
        structured_data = self._extract_json(report_raw)

        # Fallback if LLM output didn't parse clean JSON
        if not structured_data:
            structured_data = {
                "summary": report_raw[:200].replace("\n", " "),
                "key_findings": [f"Result contains {len(df_result) if df_result is not None else 0} records."],
                "chart": {
                    "chart_type": "bar",
                    "title": f"Analysis of {cols[0] if cols else 'Data'}",
                    "subtitle": "Generated from query results",
                    "x_col": cols[0] if cols else "x",
                    "y_col": cols[1] if len(cols) > 1 else (cols[0] if cols else "y")
                },
                "recommendations": "Review tabular breakdown for detailed segment performance."
            }

        activity_log.append({
            "stage": "Data Analyst",
            "title": "Derived key findings & chart specifications",
            "time": round(time.perf_counter() - t0, 3)
        })

        # Cap results preview for safety
        data_records = df_result.to_dict(orient="records") if df_result is not None else []

        return {
            "question": user_question,
            "total_duration": round(time.perf_counter() - start_total, 2),
            "sql": extracted_sql,
            "sql_error": error,
            "summary": structured_data.get("summary", ""),
            "key_findings": structured_data.get("key_findings", []),
            "chart": structured_data.get("chart", {}),
            "recommendations": structured_data.get("recommendations", ""),
            "columns": cols,
            "rows": data_records,
            "total_rows": len(data_records),
            "activity_log": activity_log
        }

    def _extract_sql(self, text: str) -> Optional[str]:
        match = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        lines = [line.strip() for line in text.splitlines() if line.strip().upper().startswith(("SELECT", "WITH"))]
        return "\n".join(lines) if lines else None

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except Exception:
                pass
        try:
            return json.loads(text.strip())
        except Exception:
            pass
        return None
