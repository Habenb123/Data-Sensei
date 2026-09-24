# 🥋 Data Sensei — Your AI Data Analysis Master

> *"Your Data. Your Questions. AI-Powered Insights."*  
> *"With big data comes big responsibilities." 🕷️*

**Data Sensei** is an autonomous AI data analytics workspace powered by **DuckDB**, **FastAPI**, **Chart.js**, and local LLMs via **Ollama** (`qwen2.5-coder:14b`) with support for **OpenAI**, **Gemini**, and **Groq**.

---

## ⚡ Key Capabilities

- **📊 Dynamic Dashboard**: Auto-generates top KPIs, distribution charts, and summary statistics on upload.
- **📋 Dataset Overview & Quality**: In-depth column profiling, data types, null percentages, distinct counts, and concrete quality alerts.
- **🤖 Sense AI (Copilot)**: Ask questions in natural language. Returns structured cards with **Executive Summary**, **3 Key Findings**, **Interactive Visualizations**, **Query Results**, and **Verified SQL**.
- **📈 Visualizations Studio**: Interactive custom chart builder (select dimensions, metrics, aggregations, and chart types) + automated multidimensional chart gallery.
- **⚡ Automated EDA**: Numerical statistics (mean, std, quartiles, skewness), categorical frequency rankings, and Pearson correlation matrices.
- **🦆 In-Memory DuckDB Engine**: Sub-second execution for multi-million row datasets with deterministic mathematical calculations.
- **📑 Saved Insights & Executive Reports**: Save interesting findings as you explore and export a complete, printable HTML/PDF executive briefing with 1 click.
- **🔒 Security & Safety**: Read-only SQL query validation blocking dangerous operational and filesystem commands.

---

## 🚀 Quick Start (Local Setup)

### 1. Clone the Repository
```bash
git clone https://github.com/Habenb123/Data-Sensei.git
cd Data-Sensei
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. (Optional) Run with Local Ollama
Make sure [Ollama](https://ollama.com) is running locally:
```bash
ollama run qwen2.5-coder:14b
# or for ultra-fast inference:
ollama run qwen2.5:7b
```

### 4. Launch Data Sensei
```bash
python main.py
```
Open your browser at **`http://localhost:8000`** 🥋

---

## ☁️ Cloud Deployment (Render / Railway)

1. Connect your GitHub repository to [Render.com](https://render.com) or [Railway.app](https://railway.app).
2. Set the **Build Command**: `pip install -r requirements.txt`
3. Set the **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. In the deployed web app, open the **Engine Settings** tab to enter your free **Groq API Key**, **Gemini Key**, or **OpenAI Key**.

---

## 📁 Project Architecture

```
Data-Sensei/
├── main.py                     # FastAPI web server & REST endpoints
├── requirements.txt            # Project dependencies
├── .gitignore                  # Git exclusions
├── sample_data/
│   └── ecommerce_sales.csv     # Sample dataset for instant exploration
├── src/
│   ├── database/
│   │   ├── __init__.py
│   │   └── duckdb_manager.py   # DuckDB in-memory OLAP engine & schema profiler
│   ├── agents/
│   │   ├── __init__.py
│   │   └── lightweight_crew.py # Multi-Agent orchestrator with conversational memory
│   └── utils/
│       ├── __init__.py
│       ├── chart_builder.py    # Dynamic visualizer utilities
│       └── data_profiler.py    # Dataset diagnostics & health checks
└── static/
    ├── index.html              # Modern workspace frontend
    ├── style.css               # Clean styling & JetBrains Mono typography
    ├── app.js                  # Frontend state management & Chart.js renderer
    └── sensei-logo.svg         # Iconic Sensei samurai vector logo
```

---

## 📜 License
MIT License. Created by [Habenb123](https://github.com/Habenb123).
