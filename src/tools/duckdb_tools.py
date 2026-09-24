"""CrewAI Custom Tools for DuckDB.
"""

from typing import Type, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from src.database.duckdb_manager import DuckDBManager


class SQLQueryInput(BaseModel):
    query: str = Field(..., description="The DuckDB SQL query to execute against table 'dataset'.")


class DuckDBQueryTool(BaseTool):
    name: str = "Execute DuckDB SQL Query"
    description: str = (
        "Executes a SQL query against the DuckDB database table named 'dataset'. "
        "Returns tabular output in markdown format."
    )
    args_schema: Type[BaseModel] = SQLQueryInput
    db_manager: Optional[DuckDBManager] = None

    def __init__(self, db_manager: DuckDBManager, **kwargs):
        super().__init__(**kwargs)
        self.db_manager = db_manager

    def _run(self, query: str) -> str:
        if not self.db_manager or not self.db_manager.loaded:
            return "Error: Database is not initialized or dataset is not loaded."

        df, exec_time, error = self.db_manager.execute_query(query)
        if error:
            return f"SQL Execution Error: {error}\nPlease adjust your query."

        if df is None or df.empty:
            return f"Query returned 0 rows ({exec_time:.4f}s)."

        total_rows = len(df)
        if total_rows > 25:
            preview_md = df.head(25).to_markdown(index=False)
            return (
                f"Query executed successfully ({total_rows} rows, {exec_time:.4f}s):\n\n"
                f"{preview_md}\n\n... [{total_rows - 25} rows truncated]"
            )
        return f"Query executed successfully ({total_rows} rows, {exec_time:.4f}s):\n\n{df.to_markdown(index=False)}"


class SchemaInput(BaseModel):
    table_name: str = Field(default="dataset", description="The table name to inspect.")


class DuckDBSchemaTool(BaseTool):
    name: str = "Inspect DuckDB Table Schema"
    description: str = (
        "Returns the schema (columns, data types, sample records) of the 'dataset' table in DuckDB."
    )
    args_schema: Type[BaseModel] = SchemaInput
    db_manager: Optional[DuckDBManager] = None

    def __init__(self, db_manager: DuckDBManager, **kwargs):
        super().__init__(**kwargs)
        self.db_manager = db_manager

    def _run(self, table_name: str = "dataset") -> str:
        if not self.db_manager or not self.db_manager.loaded:
            return "Error: Database is not initialized or dataset is not loaded."
        return self.db_manager.get_schema_summary()
