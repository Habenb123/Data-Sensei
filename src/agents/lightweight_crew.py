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
        self.provider = provider or "Ollama (Local)"
        self.model_name = (model_name or "").strip()
        
        # Resolve API Key from explicit argument or environment variables
        env_key = ""
        p_lower = self.provider.lower()
        if "gemini" in p_lower:
            env_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
            if not self.model_name:
                self.model_name = "gemini-1.5-flash"
        elif "openai" in p_lower:
            env_key = os.getenv("OPENAI_API_KEY") or ""
            if not self.model_name:
                self.model_name = "gpt-4o-mini"
        elif "groq" in p_lower:
            env_key = os.getenv("GROQ_API_KEY") or ""
            if not self.model_name:
                self.model_name = "llama-3.3-70b-versatile"
        elif "ollama" in p_lower:
            if not self.model_name:
                self.model_name = "qwen2.5-coder:14b"
            
        self.api_key = (api_key or "").strip() or env_key.strip()
        self.ollama_url = ollama_url.rstrip("/")

    def _call_llm(self, prompt: str, system_prompt: str = "") -> str:
        """Invokes the selected LLM provider with robust error handling and clear diagnostics."""
        p_lower = self.provider.lower()

        # 1. Ollama (Local)
        if "ollama" in p_lower:
            url = f"{self.ollama_url}/api/generate"
            payload = {
                "model": self.model_name or "qwen2.5-coder:14b",
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
                if not resp.ok:
                    err_msg = resp.text
                    try:
                        err_json = resp.json()
                        err_msg = err_json.get("error", resp.text)
                    except Exception:
                        pass
                    raise RuntimeError(f"Ollama Error ({resp.status_code}): {err_msg}. Make sure model '{self.model_name}' is pulled (`ollama pull {self.model_name}`).")
                return resp.json().get("response", "").strip()
            except requests.exceptions.Timeout:
                raise RuntimeError("Ollama request timed out after 180s. Tip: Switch to 'qwen2.5:7b' for faster inference.")
            except (requests.exceptions.ConnectionError, requests.exceptions.RequestException) as e:
                raise RuntimeError(
                    f"Cannot connect to local Ollama at {self.ollama_url}. "
                    "Make sure Ollama is running (`ollama serve`), or switch Provider to 'Google Gemini' or 'OpenAI' and enter an API key."
                )

        # 2. Google Gemini
        elif "gemini" in p_lower:
            if not self.api_key:
                raise RuntimeError("Google Gemini API key is missing. Please enter your Gemini API Key in Settings or the Copilot model bar.")

            req_model = (self.model_name or "gemini-1.5-flash").strip()
            if req_model.startswith("models/"):
                req_model = req_model[7:]

            full_prompt = f"{system_prompt}\n\n{prompt}".strip() if system_prompt else prompt.strip()
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": full_prompt}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 2048
                }
            }
            headers = {"Content-Type": "application/json"}

            # Build candidate list with user-specified model first
            candidate_models = [req_model]
            
            # Dynamically query Gemini ListModels to find exactly which models are enabled for this API key
            for version in ["v1beta", "v1"]:
                try:
                    list_url = f"https://generativelanguage.googleapis.com/{version}/models?key={self.api_key}"
                    list_resp = requests.get(list_url, timeout=6)
                    if list_resp.ok:
                        m_list = list_resp.json().get("models", [])
                        for item in m_list:
                            name = item.get("name", "").replace("models/", "")
                            methods = item.get("supportedGenerationMethods", [])
                            if "generateContent" in methods and name not in candidate_models:
                                # Prioritize flash and pro models
                                if "flash" in name or "pro" in name or "gemini" in name:
                                    candidate_models.append(name)
                        if len(candidate_models) > 1:
                            break
                except Exception:
                    pass

            # Fallback static list if ListModels was blocked
            for fallback in ["gemini-1.5-flash-latest", "gemini-1.5-flash", "gemini-1.5-flash-001", "gemini-1.5-flash-002", "gemini-1.5-pro", "gemini-pro", "gemini-2.0-flash-exp", "gemini-2.5-flash"]:
                if fallback not in candidate_models:
                    candidate_models.append(fallback)

            last_error = None
            for api_version in ["v1beta", "v1"]:
                for try_model in candidate_models:
                    url = f"https://generativelanguage.googleapis.com/{api_version}/models/{try_model}:generateContent?key={self.api_key}"
                    try:
                        resp = requests.post(url, headers=headers, json=payload, timeout=40)
                    except Exception as e:
                        last_error = str(e)
                        continue

                    if resp.status_code == 404:
                        continue

                    if not resp.ok:
                        err_msg = resp.text
                        try:
                            err_json = resp.json()
                            err_msg = err_json.get("error", {}).get("message", resp.text)
                        except Exception:
                            pass
                        last_error = f"Gemini ({resp.status_code}): {err_msg}"
                        # If unauthorized/invalid key, don't keep looping
                        if resp.status_code in [400, 401, 403] and "API_KEY" in err_msg.upper():
                            raise RuntimeError(f"Gemini API Key Error: {err_msg}. Please verify your API key.")
                        continue

                    res_json = resp.json()
                    candidates = res_json.get("candidates", [])
                    if not candidates:
                        continue
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if not parts:
                        continue
                    return parts[0].get("text", "").strip()

            raise RuntimeError(f"Gemini API Error: {last_error or 'Could not connect to Gemini API with your key.'}")

        # 3. OpenAI
        elif "openai" in p_lower:
            if not self.api_key:
                raise RuntimeError("OpenAI API key is missing. Please enter your OpenAI API Key in Settings or the Copilot model bar.")
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
            try:
                resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
            except Exception as e:
                raise RuntimeError(f"Network error connecting to OpenAI API: {str(e)}")

            if not resp.ok:
                err_msg = resp.text
                try:
                    err_json = resp.json()
                    err_msg = err_json.get("error", {}).get("message", resp.text)
                except Exception:
                    pass
                raise RuntimeError(f"OpenAI API Error ({resp.status_code}): {err_msg}")
            return resp.json()["choices"][0]["message"]["content"].strip()

        # 4. Groq
        elif "groq" in p_lower:
            if not self.api_key:
                raise RuntimeError("Groq API key is missing. Please enter your Groq API Key in Settings or the Copilot model bar.")
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model_name or "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system_prompt or "You are an elite SQL and data analytics copilot."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1
            }
            try:
                resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=60)
            except Exception as e:
                raise RuntimeError(f"Network error connecting to Groq API: {str(e)}")

            if not resp.ok:
                err_msg = resp.text
                try:
                    err_json = resp.json()
                    err_msg = err_json.get("error", {}).get("message", resp.text)
                except Exception:
                    pass
                raise RuntimeError(f"Groq API Error ({resp.status_code}): {err_msg}")
            return resp.json()["choices"][0]["message"]["content"].strip()

        raise ValueError(f"Unsupported LLM provider: {self.provider}")

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
        # STEP 2: SQL Specialist (Pure LLM Generation + Auto-Healing)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        sql_system = (
            "You are Data Sensei, an expert DuckDB SQL Data Analyst.\n"
            "Your sole mission is to analyze the user's uploaded dataset (table `dataset`).\n"
            "Rules:\n"
            "1. If the question asks to analyze, query, aggregate, or filter data from the dataset, write the optimal read-only DuckDB SQL inside ```sql ... ``` block using table `dataset`.\n"
            "2. If the user's input is NOT a data analysis question (e.g. random math like '2+2', general chit-chat, unrelated trivia), output strictly: `OUT_OF_DOMAIN`.\n"
            "3. Strictly use table name `dataset`.\n"
            "4. Never generate DROP, DELETE, INSERT, or ALTER commands."
        )

        sql_prompt = (
            f"{context_str}"
            f"Table Schema Information:\n{schema_summary}\n\n"
            f"User Question: '{user_question}'\n\n"
            "Analyze whether this is a dataset question. If so, write the DuckDB SQL query. If completely unrelated to the dataset, output OUT_OF_DOMAIN."
        )

        # Call selected LLM directly (errors bubble up directly to UI)
        sql_response = self._call_llm(sql_prompt, sql_system)

        # Handle Out of Domain politely
        if "OUT_OF_DOMAIN" in (sql_response or "").upper():
            return {
                "question": user_question,
                "total_duration": round(time.perf_counter() - start_total, 2),
                "sql": "-- Out of Scope: Question is unrelated to active dataset",
                "sql_error": None,
                "summary": f"🥋 Data Sensei is strictly dedicated to dataset intelligence. Please ask a question related to your active dataset '{self.db.source_filename or 'dataset'}' (e.g., trends, category comparisons, highest performers).",
                "key_findings": [
                    f"Active Dataset: **{self.db.source_filename or 'Loaded Data'}** ({self.db.row_count:,} rows, {self.db.column_count} columns).",
                    f"Quantitative Columns: {', '.join(self.db.numeric_cols[:4]) if self.db.numeric_cols else 'None'}",
                    f"Categorical Dimensions: {', '.join(self.db.categorical_cols[:4]) if self.db.categorical_cols else 'None'}"
                ],
                "chart": None,
                "recommendations": f"Try asking: 'Compare total {self.db.numeric_cols[0] if self.db.numeric_cols else 'metrics'} across {self.db.categorical_cols[0] if self.db.categorical_cols else 'categories'}'",
                "columns": [],
                "rows": [],
                "total_rows": 0,
                "activity_log": [{
                    "stage": "Guardrail",
                    "title": "Out-of-scope query guided back to dataset analysis",
                    "time": round(time.perf_counter() - t0, 3)
                }]
            }

        extracted_sql = self._extract_sql(sql_response)
        if not extracted_sql:
            raise RuntimeError(f"AI model did not return a valid SQL query block. Raw AI output:\n{sql_response[:300]}")

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

        if error:
            raise RuntimeError(f"DuckDB SQL Execution Error: {error}\nExecuted Query:\n{extracted_sql}")

        activity_log.append({
            "stage": "SQL Analyst",
            "title": f"Query generated by {self.provider} & executed in DuckDB" + (" (self-healed)" if retry_occurred and not error else ""),
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
            "    \"chart_type\": \"bar|line|doughnut\",\n"
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
            "Analyze the data and provide structured findings in JSON."
        )

        report_raw = self._call_llm(analyst_prompt, analyst_system)
        structured_data = self._extract_json(report_raw)

        if not structured_data:
            structured_data = {
                "summary": report_raw[:300].replace("\n", " "),
                "key_findings": [f"Query returned {len(df_result) if df_result is not None else 0} rows."],
                "chart": {
                    "chart_type": "bar",
                    "title": f"Analytics for {cols[0] if cols else 'Result'}",
                    "subtitle": "Generated by AI Analyst",
                    "x_col": cols[0] if cols else "x",
                    "y_col": cols[1] if len(cols) > 1 else (cols[0] if cols else "y")
                },
                "recommendations": "Review tabular records for granular segment details."
            }

        activity_log.append({
            "stage": "Data Analyst",
            "title": f"Derived key findings & chart specs via {self.provider}",
            "time": round(time.perf_counter() - t0, 3)
        })

        # Cap results preview for safety
        if df_result is not None and not df_result.empty:
            try:
                data_records = json.loads(df_result.to_json(orient="records", date_format="iso"))
            except Exception:
                data_records = df_result.fillna("").to_dict(orient="records")
        else:
            data_records = []

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
