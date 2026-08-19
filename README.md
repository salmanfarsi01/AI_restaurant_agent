# Restaurant AI Agent

Local restaurant chatbot using:

- Ollama for local language models
- Qdrant for vector search
- LangGraph for the agent workflow
- Telegram for chat
- Seaborn for model comparison charts

## Requirements

- Python 3.11+
- Ollama
- Git
- Docker Desktop (optional; only needed for Qdrant container mode)
- Telegram bot token (only needed for Telegram)

## Setup on Windows

```powershell
git clone <repository-url>
cd restaurant-ai-agent
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and add your Telegram token:

```env
TELEGRAM_BOT_TOKEN=your_token_here
OLLAMA_MODEL=qwen2.5:1.5b
```

## Install and start Ollama

Install Ollama from [ollama.com](https://ollama.com), then download the models:

```powershell
ollama pull qwen2.5:0.5b
ollama pull qwen2.5:1.5b
ollama pull qwen3:0.6b
ollama pull qwen3:1.7b
```

Ollama normally runs automatically. If it does not:

```powershell
ollama serve
```

## Qdrant

The project already contains a local Qdrant index in `data/processed/qdrant_storage`.

To use Qdrant with Docker instead:

```powershell
docker compose up -d qdrant
```

## Run the application

Run the Telegram bot:

```powershell
python -m app.api.telegram
```

Run the FastAPI server:

```powershell
uvicorn app.main:app --reload
```

Test the API:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/chat `
  -ContentType "application/json" `
  -Body '{"user_id":"1","message":"What is the price of the milk?"}'
```

## Rebuild the RAG index

Put the menu CSV in `data/raw/menu_dataset.csv`, then run:

```powershell
python -m app.rag.build_index
```

## Run the 100-question benchmark

The benchmark uses English US restaurant and menu questions from
`app/evaluation/datasets.py`.

Run all four models:

```powershell
python -m app.evaluation.benchmark
```

Run selected models:

```powershell
python -m app.evaluation.benchmark --models qwen2.5-0.5b qwen2.5-1.5b
```

Results are saved in `experiments/results/`:

- `model_comparison_summary.csv`
- `comparison_table.csv`
- `model_performance_comparison.png`
- per-model benchmark CSV files

## Project structure

```text
app/
  agent/                 LangGraph workflow
  api/telegram.py        Telegram bot
  evaluation/            Benchmark and metrics
  models/                Ollama model loading
  rag/                   CSV loading, embeddings, retrieval, Qdrant
  main.py                FastAPI application
data/raw/                Menu and policy files
data/processed/          Local Qdrant index and SQLite database
experiments/results/     Benchmark CSV files and charts
tests/                   Automated tests
```

## Run tests

```powershell
pytest
```
