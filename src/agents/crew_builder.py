"""CrewAI Agent and Task Orchestrator for DataCrew.
"""

from __future__ import annotations
import os
from typing import Optional
from crewai import Agent, Crew, Process, Task, LLM
from src.database.duckdb_manager import DuckDBManager
from src.tools.duckdb_tools import DuckDBQueryTool, DuckDBSchemaTool


def build_llm(
    provider: str = "Ollama (Local)",
    model_name: str = "qwen2.5-coder:14b",
    api_key: Optional[str] = None
) -> LLM:
    """Builds a CrewAI LLM instance based on provider and API key."""
    if provider == "Ollama (Local)":
        return LLM(model=f"ollama/{model_name}", base_url="http://localhost:11434")

    if api_key:
        if provider == "OpenAI":
            os.environ["OPENAI_API_KEY"] = api_key
            return LLM(model=f"openai/{model_name}", api_key=api_key)
        elif provider == "Google Gemini":
            os.environ["GEMINI_API_KEY"] = api_key
            os.environ["GOOGLE_API_KEY"] = api_key
            m = model_name if model_name.startswith("gemini/") else f"gemini/{model_name}"
            return LLM(model=m, api_key=api_key)
        elif provider == "Groq":
            os.environ["GROQ_API_KEY"] = api_key
            return LLM(model=f"groq/{model_name}", api_key=api_key)
        elif provider == "Anthropic":
            os.environ["ANTHROPIC_API_KEY"] = api_key
            return LLM(model=f"anthropic/{model_name}", api_key=api_key)

    # Fallback to local Ollama or default OpenAI
    return LLM(model="ollama/qwen2.5-coder:14b", base_url="http://localhost:11434")


def create_datacrew(
    db_manager: DuckDBManager,
    user_query: str,
    llm: LLM
) -> Crew:
    """Constructs the 4-agent CrewAI pipeline."""

    schema_tool = DuckDBSchemaTool(db_manager=db_manager)
    query_tool = DuckDBQueryTool(db_manager=db_manager)

    # 1. Data Explorer
    explorer_agent = Agent(
        role="Senior Data Explorer & Profiler",
        goal="Inspect 'dataset' schema, column types, and sample values to eliminate hallucinations.",
        backstory="Expert data engineer who verifies exact column names and types before queries are generated.",
        tools=[schema_tool, query_tool],
        llm=llm,
        verbose=True
    )

    # 2. SQL Analyst
    sql_agent = Agent(
        role="Lead DuckDB SQL Specialist",
        goal="Write optimal DuckDB SQL, execute it against table 'dataset', and return verified results.",
        backstory="SQL master who writes high-performance aggregations, window functions, and filters.",
        tools=[query_tool, schema_tool],
        llm=llm,
        verbose=True
    )

    # 3. Data Analyst
    analyst_agent = Agent(
        role="Principal Quantitative Data Analyst",
        goal="Interpret SQL query results, extract trends, outliers, growth rates, and statistical insights.",
        backstory="Senior quantitative strategist who discovers the business drivers behind raw numbers.",
        tools=[query_tool],
        llm=llm,
        verbose=True
    )

    # 4. Report & Visualization Agent
    report_agent = Agent(
        role="Executive BI & Visualization Designer",
        goal="Synthesize findings into an executive report with recommendations and a ```chart_spec``` JSON block.",
        backstory="Presentation wizard skilled in crafting executive takeaways and defining Plotly chart specs.",
        llm=llm,
        verbose=True
    )

    # Tasks
    task_explore = Task(
        description=f"Inspect 'dataset' schema for question: '{user_query}'. Identify all relevant columns and data types.",
        expected_output="Schema overview with relevant columns, data types, and filtering recommendations.",
        agent=explorer_agent
    )

    task_sql = Task(
        description=f"Write clean DuckDB SQL for: '{user_query}'. Execute it using your tool on table 'dataset'. Fix any errors.",
        expected_output="Final executed SQL enclosed in ```sql ... ``` and markdown table of query results.",
        agent=sql_agent
    )

    task_analyze = Task(
        description=f"Analyze SQL results for: '{user_query}'. Calculate metrics, trends, percentages, and outliers.",
        expected_output="Statistical and business analysis detailing findings and anomalies.",
        agent=analyst_agent
    )

    task_report = Task(
        description=(
            f"Create executive report for '{user_query}'. Output MUST include:\n"
            "1. **Executive Summary**\n"
            "2. **Executed SQL Query** in ```sql ... ```\n"
            "3. **Key Analytical Insights** (metrics, percentages)\n"
            "4. **Strategic Recommendations**\n"
            "5. **Chart Specification** inside ```chart_spec\n"
            "{\n  \"chart_type\": \"bar|line|scatter|pie\",\n  \"title\": \"Title\",\n  \"x_col\": \"column_name\",\n  \"y_col\": \"column_name\"\n}\n```"
        ),
        expected_output="Structured markdown report containing SQL, insights, recommendations, and ```chart_spec``` block.",
        agent=report_agent
    )

    return Crew(
        agents=[explorer_agent, sql_agent, analyst_agent, report_agent],
        tasks=[task_explore, task_sql, task_analyze, task_report],
        process=Process.sequential,
        verbose=True
    )
