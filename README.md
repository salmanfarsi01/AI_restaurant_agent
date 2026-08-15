# Bilingual Restaurant Ordering AI Agent (Telegram + LangGraph + Local Models)

A locally-run, bilingual (English/Bangla) restaurant ordering agent built with
LangGraph, served over Telegram, backed by a RAG pipeline (local HuggingFace
embeddings + Qdrant) over dummy menu/policy/about data, and powered by local
LLMs via Ollama. Designed so you can swap the LLM / embedding model / vector DB
per run and produce comparison tables for a conference paper.

## 0. Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) installed natively, **or** run it via Docker (see `docker-compose.yml`)
- Docker (only needed if you run Qdrant/Ollama in containers — optional, see below)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

## 1. Setup (local PC, step by step)

```bash
# 1. clone/copy this project, then:
cd restaurant-ai-agent
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. install dependencies
pip install -r requirements.txt

# 3. configure environment
cp .env.example .env
# edit .env: paste your TELEGRAM_BOT_TOKEN, pick OLLAMA_MODEL / EMBEDDING_MODEL

# 4. start Qdrant (pick ONE)
#    a) Docker (recommended):
docker compose up -d qdrant
#    b) No Docker — embedded mode: set QDRANT_URL= (empty) in .env, skip this step

# 5. start Ollama and pull a model
ollama serve                     # if not already running as a service
ollama pull llama3.1:8b
ollama pull bge-m3               # only if you want to try it as an Ollama-served embedder

# 6. drop your real menu export in place, then build the vector index
cp /path/to/your/5000-row-export.csv data/raw/menu_dataset.csv
python -m app.rag.build_index
# (if you skip this, it falls back to data/raw/menu_dataset_sample.csv for a quick local test)

# 7a. run the Telegram bot
python -m app.api.telegram

# 7b. OR test via HTTP instead of Telegram
uvicorn app.main:app --reload
curl -X POST localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"user_id":"1","message":"কাচ্চি বিরিয়ানির দাম কত?"}'
```

That's it — message your bot on Telegram in English or Bangla.

## 2. Project structure

```
restaurant-ai-agent/
├── app/
│   ├── main.py              # FastAPI test harness
│   ├── config.py            # env-driven settings (swap models/DB here)
│   ├── api/telegram.py      # Telegram polling bot
│   ├── agent/               # LangGraph: state, prompts, nodes, graph
│   ├── rag/                 # loader, splitter, embeddings, Qdrant store, retriever
│   ├── models/llm_loader.py # Ollama LLM loader
│   ├── database/            # SQLAlchemy Order/OrderItem models
│   └── evaluation/          # benchmark harness -> experiments/results/*.csv
├── data/raw/
│   ├── menu_dataset.csv        # <- put your real 5000-row export here (gitignored)
│   ├── menu_dataset_sample.csv # small fixture with the same schema, for local testing
│   └── policy_en.txt / policy_bn.txt  # synthetic bilingual terms & policy (not in the CSV)
├── experiments/results/     # CSV outputs per model run (for your paper's tables)
├── tests/
└── docker-compose.yml       # Qdrant (+ optional Ollama) containers
```

## 3. About the real dataset (CSV ingestion logic)

Your export (`createdOn, changeOperation, market, city, menuItemName, ...`) is a
**change-log**, not a menu snapshot: the same dish can appear in multiple rows
over time (`Create`, `Update`, `Delete`). `app/rag/loader.py` handles this:

1. Reads the CSV with pandas, parses `createdOn` as a timestamp (falls back to
   row order if a timestamp fails to parse).
2. Groups rows by `(restaurantName, menuItemName)` and keeps only the
   **latest** row per item — that's the item's current state.
3. Drops any item whose latest event is `Delete` (no longer on the live menu).
4. Builds one `menu` document per surviving item (name, price, category,
   rating, restaurant, description) and one `restaurant_info` document per
   unique restaurant (address, cuisine description, price range).
5. Both doc types are kept **atomic** in `splitter.py` — they're already a
   single fact each, so chunking them would separate a dish's name from its
   price and hurt retrieval.

**Language note:** the CSV is English-only. Rather than machine-translating
5,000 rows into Bangla (which would just inject MT errors into your RAG
context), `retrieve()` in `app/rag/retriever.py` only applies a language
filter for policy docs, which genuinely exist in both languages. For
menu/restaurant queries, a Bangla question is embedded and matched directly
against the English menu chunks — multilingual embedding models (BGE-M3,
multilingual-e5) map same-meaning text across languages into the same vector
space, so this cross-lingual retrieval works without needing a Bangla menu
corpus. The LLM then generates the final answer in Bangla using that English
context. This is worth stating explicitly as a design decision/limitation in
your paper, and is itself a reasonable thing to *measure*: does retrieval
quality or answer quality drop for Bangla queries against English-only
context, compared to English queries? That's a clean ablation for the paper.

Once you know which restaurant a user is ordering from, set
`state["restaurant_name"]` (e.g. after an initial restaurant-selection step)
so `rag_retrieve` / `handle_order` narrow results to that restaurant instead
of searching across all restaurants in the CSV.

## 4. Running the model-comparison experiments

The whole point of the `evaluation/` module is to let you swap one variable at
a time and get a CSV per run:

```bash
# edit .env -> OLLAMA_MODEL=llama3.1:8b
python -m app.evaluation.benchmark

# edit .env -> OLLAMA_MODEL=mistral:7b
python -m app.evaluation.benchmark

# edit .env -> OLLAMA_MODEL=qwen2.5:7b
python -m app.evaluation.benchmark
# ...repeat for each LLM, then repeat the whole sweep for each EMBEDDING_MODEL
```

Each run appends timing + a naive keyword-match accuracy to
`experiments/results/`. For the paper, extend `metrics.py` with: retrieval
precision/recall@k, a proper LLM-judged answer-accuracy score, hallucination
rate (does the answer state facts not in the retrieved context?), and
order-completion success rate (did the extracted cart JSON match ground truth?).

## 5. Model recommendations (with Bangla in mind)

### LLMs (via Ollama)
| Model | Notes |
|---|---|
| **Qwen2.5 / Qwen3 (7B–8B)** | Best all-round Bangla performance among openly runnable local models right now — 100+ languages, strong instruction following, good JSON/structured-output reliability (important for your order-extraction node). Good default baseline. |
| **Meta Llama 3.1 8B Instruct** | Solid general multilingual baseline, widely benchmarked, easy to compare against published numbers. |
| **Gemma 2/3 (9B / 12B)** | Competitive multilingual quality, runs comfortably on a single consumer GPU or CPU-only at smaller sizes. |
| **BanglaLLM/BanglaLLama-3-8B** (HF: `BanglaLLM/BanglaLLama-3-8b-...`) | Llama-3 fine-tuned specifically on Bangla (CulturaX Bangla subset) — worth including as your "Bangla-specialist" comparison point against the general multilingual models above, since a paper reviewer will likely ask why you didn't. |
| **Phi-4-mini** | Weakest Bangla support of this list but useful as a "cheap/small model" baseline for your latency-vs-quality tradeoff chart. |

Practical note: general-purpose multilingual models (Qwen, Llama, Gemma) currently
tend to *outperform* older Bangla-specific fine-tunes on real conversational
quality, because they were pretrained on far more Bangla data at much larger
scale — that's actually a good empirical finding to report, not a reason to skip
the Bangla-specific model from your comparison.

### Embedding models (for retrieval quality)
| Model | Notes |
|---|---|
| **BAAI/bge-m3** | Consistently the strongest multilingual/cross-lingual retriever across published benchmarks (MIRACL, IndicRAGSuite, BEIR-style Indic evaluations) — leads in most Indic languages tested, including Bangla-adjacent languages. **Recommended default** for your main pipeline. |
| **intfloat/multilingual-e5-large** | Very close second, sometimes ahead on short-passage/single-language retrieval, noticeably lower latency than bge-m3. Good "efficient" comparison point. |
| **jinaai/jina-embeddings-v3** | Competitive multilingual model with flexible task-specific LoRA adapters (retrieval/classification/etc.) — good third point of comparison. |
| **sentence-transformers/LaBSE** | Weaker retrieval performance than the above in most benchmarks, but useful as a lower-bound baseline in your table since it's a very commonly cited multilingual embedding model. |

Given your paper angle, a clean experimental design is: **3 LLMs × 2–3
embedding models × Qdrant** (fixed), reporting the metrics in §3 — that's a
manageable ~6–9 run matrix without needing to also swap vector DBs.

### Vector DB
Using **Qdrant** here (this project already wired up). If you want a vector-DB
comparison axis too, keeping everything else fixed and swapping just
`app/rag/vectorstore.py` for a Chroma/Milvus/Weaviate-local implementation is
a small, isolated change — but for a first paper, fixing the vector DB and
varying LLM + embedding model is the more tractable scope.

## 6. Agile plan (2-week sprints)

**Sprint 0 — Setup (2–3 days)**
- Repo scaffold (this project), Ollama + Qdrant running locally, `.env` configured
- Dummy bilingual data finalized (menu/policy/about, EN + BN)
- Definition of Done: `python -m app.rag.build_index` runs clean, `/chat` endpoint answers a basic EN and BN question

**Sprint 1 — Core RAG pipeline**
- Loader/splitter/embeddings/retriever solid, tune chunk size, add metadata filters
- Manual QA pass: 10 EN + 10 BN questions, check retrieval relevance
- DoD: retrieval hit-rate ≥ ~80% on your manual test set

**Sprint 2 — Agent graph (LangGraph)**
- Language detection, intent classification, RAG-answer node, general-chat node
- Per-user memory via checkpointer working across turns
- DoD: bot correctly routes menu/policy/general queries in both languages

**Sprint 3 — Ordering flow**
- Cart add/remove/clear extraction, checkout confirmation, SQLite persistence
- Edge cases: ambiguous item names, quantity parsing, mixed-language input
- DoD: a user can complete a full order end-to-end via Telegram

**Sprint 4 — Telegram polish + evaluation harness**
- Telegram UX (start command, error handling, typing indicator, retries)
- `evaluation/` module finished: latency, keyword-accuracy, retrieval metrics
- DoD: `python -m app.evaluation.benchmark` produces a clean CSV per model

**Sprint 5 — Experiments for the paper**
- Run the full LLM × embedding-model matrix, log every CSV in `experiments/results/`
- Add hallucination-rate and order-completion-success scoring (manual or LLM-judged)
- DoD: results table + charts ready to drop into the paper

**Sprint 6 — Writeup**
- Draft paper using `docs/paper_notes.md`, `docs/architecture.md`, `docs/experiment_plan.md`
- Related-work pass, ablations if time allows (chunk size, k, temperature)
- DoD: submission-ready draft

Use `docs/` as your running notes (architecture, experiment plan, and paper
draft) — track sprint backlogs there or in a GitHub Projects board / Jira, one
epic per sprint above, tasks broken down per bullet.

## 7. How to finish it

1. Get Sprints 0–2 working with just 1 LLM + 1 embedding model — don't optimize early.
2. Once the bot reliably completes orders and answers RAG questions in both languages, freeze the pipeline code.
3. Only then start swapping models for Sprint 5 — changing code and comparing models at the same time will contaminate your results.
4. Keep every `experiments/results/*.csv` — you'll want raw data for statistical tests (e.g. paired comparisons across models) in the paper, not just averages.
5. Write the paper around whichever axis produced the most interesting result (e.g. "Bangla-specific fine-tune vs. general multilingual model" or "embedding model matters more than LLM choice for factual accuracy") rather than trying to cover everything equally.
