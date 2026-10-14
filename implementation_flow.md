# AI Restaurant Agent: Implementation Flow & Progress Tracker

> **Architecture Reference**: [SYSTEM_REQUIREMENTS_AND_ARCHITECTURE.md](file:///c:/dev/AI_restaurant_agent/SYSTEM_REQUIREMENTS_AND_ARCHITECTURE.md)  
> **Backend Status**: ✅ ALL SPRINTS COMPLETED & VERIFIED (6/6 Integration Tests Passing)  
> **Scope Delivered**: Complete Backend Architecture & Agent Brain Logic (UI/Frontend deferred to subsequent phase)

---

## 📊 Agile Sprints Execution Summary

| Sprint | Subsystem / Module | Status | Core Technologies & Libraries |
| :--- | :--- | :--- | :--- |
| **Sprint 1** | **Environment, Dependencies & Configuration** | ✅ Completed | `groq`, `langchain-groq`, `pydantic-settings`, `python-dotenv`, `requirements.txt` |
| **Sprint 2** | **Relational Models & Transactional Order Service** | ✅ Completed | `SQLAlchemy 2.0`, `SQLite`, `pydantic`, Decimal-safe pricing, Persistent Session Cart |
| **Sprint 3** | **Groq LLM Brain & Conversational LangGraph** | ✅ Completed | `LangGraph 0.2`, `Groq Cloud API` (`llama-3.3-70b-versatile`), Progressive Category Greeting, Slot Extraction |
| **Sprint 4** | **Two-Phase Anti-Scanner Email Verification** | ✅ Completed | `aiosmtplib`, `Jinja2`, `FastAPI` (GET landing page $\to$ explicit POST confirmation) |
| **Sprint 5** | **Decoupled Outbox Workers & POS Kitchen Printing** | ✅ Completed | `python-escpos`, `pywin32` (`win32print`), Fallback Mock File POS, Outbox Worker Queue |
| **Sprint 6** | **Day-by-Day Google Sheets Sync & Marketing Broadcast** | ✅ Completed | `gspread`, `google-auth`, Throttled Marketing Broadcast, Unsubscribe Compliance |
| **Sprint 7** | **End-to-End Automated Testing & Quality Verification** | ✅ Completed | `pytest`, `fastapi.testclient`, 100% Passing Integration Test Suite |

---

## 📝 Comprehensive Sprint Implementation Details

### [Sprint 1] Environment, Dependencies & Configuration
* **Completed Work**:
  * Upgraded `requirements.txt` to include `groq`, `langchain-groq`, `gspread`, `google-auth`, `aiosmtplib`, `jinja2`, `python-escpos`, `pywin32`, and `python-multipart`.
  * Installed dependencies into the virtual environment at `.\venv`.
  * Updated `app/config.py` with centralized settings for Groq LLM, token expiration, email SMTP (with safe local mock fallback), thermal POS printer modes (`mock`, `network`, `windows`), and Google Sheets credentials.
  * Created complete `.env.example` and default `.env`.
* **How It Works**:
  * Centralizes all credentials with fail-safe mock modes. Developers can immediately run and test the complete system locally without crashing even if physical POS hardware or external API keys are not yet configured.

---

### [Sprint 2] Relational Models & Transactional Order Service (Ground Truth)
* **Completed Work**:
  * Implemented SQLAlchemy 2.0 ORM models in `app/database/models.py`:
    * `MenuItem`: Menu catalog with decimal-safe prices (`Numeric(10, 2)`) and stock availability.
    * `Order`: Full state machine (`DRAFT`, `PENDING_EMAIL_CONFIRMATION`, `CONFIRMED`, `ACCEPTED_BY_KITCHEN`, `PREPARING`, `READY`, `OUT_FOR_DELIVERY`, `DELIVERED`, `EXPIRED`, `CANCELLED`).
    * `OrderItem`: Line items with frozen unit price snapshots.
    * `CustomerLead`: CRM directory with order counts, lifetime spend, and subscription status.
    * `FulfillmentJob`: Durable outbox queue for decoupled background execution.
    * `AgentSession`: Persistent cart and slot state across chat turns.
  * Implemented `app/database/seed_menu.py` with 14 authentic Dhaka Spice House dishes.
  * Implemented `app/services/order_service.py`:
    * Dish fuzzy matching and item price resolution from database.
    * Persistent cart management (add, edit quantities, remove, clear).
    * Multi-turn customer slot validation (permissive international/Bangla name regex, email format, phone validation).
    * Decimal-safe pricing calculations (subtotal, delivery fee, grand total).
    * Idempotent order confirmation by cryptographic token.
    * Outbox job enqueuing for background workers.
* **How It Works**:
  * The database is the authoritative owner of financial totals and order states. The LLM assists with natural language but never performs arithmetic or mutates database state unvalidated.

---

### [Sprint 3] Groq LLM Brain & Conversational LangGraph
* **Completed Work**:
  * Implemented `app/models/llm_loader.py` supporting `ChatGroq` with `llama-3.3-70b-versatile` and `llama-3.1-8b-instant`, with graceful mock fallback for offline testing.
  * Refactored `app/agent/prompts.py`:
    * **No Menu Dumping**: Provides warm greetings highlighting popular categories (`[Biryani & Mains]`, `[Kebabs]`, `[Wings]`, `[Drinks]`, `[Desserts]`) rather than dumping 5,000 items.
    * Multi-turn slot extraction for `customer_name`, `customer_email`, `customer_phone`, and `delivery_address`.
    * Cart modification prompt extracting `{action, item_name, quantity}` as strict JSON.
  * Implemented LangGraph nodes (`app/agent/nodes.py`) and workflow graph (`app/agent/graph.py`):
    * `detect_language`: Fast bilingual routing (Bangla / English).
    * `classify_intent`: Dispatches to `greeting`, `menu_inquiry`, `order_update`, `provide_info`, `checkout_review`, or `general`.
    * `handle_checkout_review`: Displays explicit order recap before creating a draft order and sending verification email.
* **How It Works**:
  * Maintains conversational state via checkpointer while syncing persistent cart state directly to `AgentSession` in SQLite. When all 6 required fields are provided, it transitions the order to `PENDING_EMAIL_CONFIRMATION` and dispatches the verification email.

---

### [Sprint 4] Two-Phase Anti-Scanner Email Verification Endpoints
* **Completed Work**:
  * Implemented `app/services/email_service.py`:
    * Generates branded, responsive Jinja2 HTML verification email with itemized summary and a prominent `[Review & Confirm Order]` action.
    * Supports async SMTP delivery (`aiosmtplib`) and local file output in `data/emails/`.
  * Implemented FastAPI router in `app/api/orders.py`:
    * `GET /orders/verify?token=...`: Anti-scanner landing page. Displays order recap and an explicit confirmation button. **Zero state mutations occur on GET.**
    * `POST /api/orders/confirm`: Customer explicit action. Atomically changes order status to `CONFIRMED` and `VERIFIED`.
    * Enforces strict idempotency: repeated clicks return the existing confirmed order without duplicate kitchen prints or duplicate sheet rows.
* **How It Works**:
  * Protects against email security bots (Proofpoint, Outlook Safe Links, Gmail crawlers) that pre-fetch GET links. Orders are only sent to the kitchen when an intentional POST is submitted.

---

### [Sprint 5] Decoupled Outbox Workers & POS Kitchen Printing
* **Completed Work**:
  * Implemented `app/services/printer_service.py`:
    * **Network ESC/POS Adapter**: Connects via TCP socket (`IP:9100`) sending raw ESC/POS byte streams with auto paper cut.
    * **Windows Spooler Adapter**: Dispatches raw tickets via Windows driver (`win32print`).
    * **Mock File Adapter**: Writes formatted 80mm receipts to `data/receipts/receipt_{order_code}.txt`.
  * Implemented `app/services/notification_service.py`:
    * Pushes real-time confirmation notices to Telegram / Web Chat.
  * Implemented `app/services/worker_dispatcher.py`:
    * Polls `fulfillment_jobs` table and independently executes `KITCHEN_PRINT`, `GSHEETS_SYNC`, and `CUSTOMER_NOTIFY`.
    * Implements error logging and retry counts with backoff.
* **How It Works**:
  * Hardware outages (out of paper, printer offline) are completely decoupled from customer order confirmation. The order is confirmed in the database, and the printer worker retries or alerts staff without blocking customer notifications or spreadsheet logging.

---

### [Sprint 6] Day-by-Day Google Sheets Sync & Marketing Broadcast
* **Completed Work**:
  * Implemented `app/services/sheets_service.py`:
    * Authenticates with Google Sheets API v4 using Service Account (`credentials.json`).
    * Automatically creates daily tabs: `Orders_YYYY-MM-DD` with formatted column headers.
    * Implements **idempotent upsert**: checks Column B (`Order ID`); updates row if order already exists, otherwise appends a new row.
    * Upserts into `Leads_Master` sheet (Email, Name, Phone, Lifetime Spend, Total Orders, Subscribed).
    * Includes local CSV replica backup in `data/sheets_backup/` to guarantee zero data loss.
  * Implemented `app/services/marketing_service.py` & `app/api/marketing.py`:
    * Canonical endpoint: `POST /api/marketing/broadcast` (and alias `POST /api/marketing/campaigns/send`).
    * Preview endpoint: `POST /api/marketing/broadcast/preview`.
    * Unsubscribe endpoint: `GET /api/marketing/unsubscribe?email=...` (sets `is_subscribed = False` in DB and Sheets).
    * Staff Kitchen Reprint Control: `POST /api/orders/{order_code}/reprint` (prints ticket marked `*** DUPLICATE / REPRINT ***`).
* **How It Works**:
  * Enables restaurant management to broadcast promotional discounts to all verified leads with delivery throttling and unsubscribe compliance.

---

### [Sprint 7] Quality Verification & Integration Tests
* **Test Suite**: `tests/test_flow.py`
* **Test Results**: **6 / 6 PASSED** in 1.40s
  1. `test_menu_seeded` (✅ PASSED): Verified menu catalog and prices.
  2. `test_chat_greeting` (✅ PASSED): Verified progressive category greeting without menu dumping.
  3. `test_cart_operations` (✅ PASSED): Verified adding, modifying, and calculating line item totals.
  4. `test_end_to_end_order_and_anti_scanner_verification` (✅ PASSED):
     - Verified slot collection for all 6 mandatory fields.
     - Verified draft creation (`PENDING_EMAIL_CONFIRMATION`).
     - Verified GET landing page performed zero state mutation.
     - Verified POST confirmation transitioned status to `CONFIRMED`.
     - Verified idempotency on repeated POST confirmation.
  5. `test_decoupled_worker_execution` (✅ PASSED): Verified outbox worker execution.
  6. `test_marketing_broadcast_endpoint` (✅ PASSED): Verified authorization protection and broadcast execution.

---

## 🚀 How to Run & Test the Backend

### 1. Run the FastAPI Server
```powershell
.\venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```

### 2. Run the Full Test Suite
```powershell
.\venv\Scripts\pytest.exe tests/test_flow.py
```

### 3. Test Chat via REST API
```powershell
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"user_id": "cust1", "message": "hi"}'
```

### 4. Run the Telegram Bot (Polling Mode)
```powershell
.\venv\Scripts\python.exe -m app.api.telegram
```
