# Telegram Content Factory

AI-powered Telegram bot that turns raw ideas into polished LinkedIn posts, Twitter threads, and Notion pages. Review, then `/accept`, `/rewrite`, or `/quit`.

```
You: "I spent 18 months doing everything myself..."
  ↓
Bot:  📝 LinkedIn Post (1358 tokens)
      [your polished post here]
      ━━━━━━━━━━━━━━
      Reply: /accept /rewrite /quit
  ↓
You: /accept
Bot:  ✅ Saved to Notion: https://notion.so/...
```

---

## Quick Start

```bash
cd telegram-content-factory

# 1. Fill in your API keys
cp .env.example .env
# Edit .env — add DEEPSEEK_API_KEY, TELEGRAM_BOT_TOKEN, NOTION_API_KEY, NOTION_DATABASE_ID

# 2. Install dependencies
python3 -m pip install -r requirements.txt

# 3. Run
python3 src/main.py
```

### Environment Variables

| Variable | Where to get it |
|---|---|
| `DEEPSEEK_API_KEY` | [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys) |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/botfather) — send `/newbot` |
| `NOTION_API_KEY` | [notion.so/my-integrations](https://www.notion.so/my-integrations) |
| `NOTION_DATABASE_ID` | Create a database, copy the ID from its URL |

---

## How to Read This Codebase

If you're new to Python, start here. The code is annotated with comments that explain *why*, not just *what*.

### Reading Order (beginner-friendly)

| # | File | What you'll learn |
|---|---|---|
| 1 | `src/config/settings.py` | Environment variables, `os.getenv()`, module-level constants |
| 2 | `src/utils/logger.py` | Python's `logging` module, `__name__` |
| 3 | `src/utils/retry.py` | **Decorators** (`@retry`), `*args`/`**kwargs`, `functools.wraps` |
| 4 | `src/models/content.py` | **Dataclasses**, **Enums**, type hints (`str \| None`) |
| 5 | `src/services/openai_service.py` | **Module-level singletons**, tuple returns, OpenAI SDK |
| 6 | `src/services/telegram_service.py` | **Classes**, `self`, **async/await**, REST APIs with httpx |
| 7 | `src/services/notion_service.py` | **Type hints** with dicts, f-strings, UTC datetime |
| 8 | `src/router/intent_classifier.py` | **Hybrid pattern**, pathlib, early return |
| 9 | `src/router/workflow_router.py` | **match/case** (Python 3.10+), lazy imports |
| 10 | `src/workflows/linkedin_post/__init__.py` | Two-pass pipeline pattern |
| 11 | `src/main.py` | **State machines**, command routing, async polling loop |

### Python Concepts Used

**Decorator** (`@something` above a function):
```python
@retry(max_attempts=3)      # ← This wraps the function. If it throws,
def call_api(url):           #   it'll retry up to 3 times with backoff.
    ...
```
Think of decorators as "wrappers" — they add behavior before/after your function without changing the function's own code.

**Dataclass** (`@dataclass`):
```python
@dataclass
class IncomingMessage:
    message_id: str          # Auto-generates __init__, __repr__, __eq__
    chat_id: str
    text: str
```
A dataclass is a class that mainly holds data. Instead of writing `__init__` yourself, you just declare the fields and Python generates it.

**Enum** (enumeration):
```python
class State(Enum):
    AWAITING_IDEA = "awaiting_idea"
    AWAITING_DECISION = "awaiting_decision"
```
Enums prevent typos. You write `State.AWAITING_IDEA`, not `"awaiting_idea"` (which could be misspelled).

**Async / Await** (concurrency without threads):
```python
async def poll(self):                    # `async def` = this function can pause
    messages = await self.get_updates()   # `await` = pause here until done
```
`await` means "pause this function until the slow thing finishes, and let other things run in the meantime." In this bot, `await` is used for HTTP requests and sleeping.

**Type Hints** (what type is this?):
```python
def generate(prompt: str, max_tokens: int = 2000) -> tuple[str, int]:
    ...                                    # ↑ argument types         ↑ return type
```
Type hints don't change runtime behavior — they're documentation that your IDE (VS Code) uses for autocompletion and error detection.

**Match / Case** (Python's switch statement):
```python
match msg.content_type:
    case ContentType.LINKEDIN_POST:   # If content_type is LINKEDIN_POST...
        from workflows.linkedin_post import generate
    case ContentType.TWITTER_THREAD:  # If content_type is TWITTER_THREAD...
        from workflows.twitter_thread import generate
    case _:                           # Default (matches anything)
        return None
```

### Project Structure

```
src/
├── main.py                  ← Entry point.  The polling loop + state machine.
├── config/settings.py       ← All configuration from .env
├── models/content.py        ← Data structures (IncomingMessage, GeneratedContent)
├── router/
│   ├── intent_classifier.py ← Decides WHAT to generate (rules → AI)
│   └── workflow_router.py   ← Decides WHO generates it (dispatches to workflow)
├── services/
│   ├── openai_service.py    ← LLM calls (DeepSeek primary, OpenAI fallback)
│   ├── telegram_service.py  ← Telegram Bot API (poll, send, keyboards)
│   └── notion_service.py    ← Notion API (database logging)
├── workflows/
│   ├── linkedin_post/       ← Idea → LinkedIn post pipeline
│   ├── twitter_thread/      ← Idea → Twitter thread pipeline
│   └── notion_page/         ← Idea → Notion page pipeline
├── prompts/                 ← AI system prompts (.txt files)
│   ├── linkedin_prompt.txt
│   ├── twitter_prompt.txt
│   ├── notion_prompt.txt
│   ├── intent_classifier_prompt.txt
│   └── humanizer_pass.txt
└── utils/
    ├── logger.py            ← Structured logging
    └── retry.py             ← @retry decorator with exponential backoff
```

---

## Architecture

### Flow

```
Telegram Message
      │
      ▼
┌─────────────────┐
│  Command Router  │  /accept, /rewrite, /quit, /start ALWAYS work
└────────┬────────┘
         │ (not a command)
         ▼
┌─────────────────┐
│ State Machine    │  AWAITING_IDEA → AWAITING_DECISION → AWAITING_FEEDBACK
│  (per chat)     │
└────────┬────────┘
         │
    ┌────┴────┬─────────┐
    ▼         ▼          ▼
LinkedIn   Twitter    Notion
  Post     Thread      Page     ← Each is a two-pass pipeline
    │         │          │         (draft → humanizer)
    └────┬────┴────┬─────┘
         ▼         ▼
     Notion DB   Telegram
     (on /accept) (always)
```

### State Machine

```
AWAITING_IDEA ──→ AWAITING_DECISION ──→ AWAITING_FEEDBACK
     ↑                   │                     │
     │    /quit          │  /accept            │ feedback sent
     └───────────────────┘  (saves to Notion)  │
     ↑                                         │
     └─────────────────────────────────────────┘
```

Commands (`/accept`, `/rewrite`, `/quit`, `/start`) work in **any** state.

### Two-Pass Generation

Every content type goes through two LLM calls:

1. **Draft pass** — The content-specific prompt (LinkedIn/Twitter/Notion) generates the first version
2. **Humanizer pass** — A dedicated de-AI filter strips corporate buzzwords, AI vocabulary, em-dashes, and inflated language

This roughly doubles token usage but produces output that reads like a person wrote it.

---

## Commands

| Command | Aliases | What it does |
|---|---|---|
| `/start` | — | Reset and show welcome message |
| `/accept` | `/acc`, `/ac` | Save current result to Notion database |
| `/rewrite` | `/re`, `/rw` | Ask for feedback, then regenerate |
| `/quit` | `/q`, `/cancel`, `/reset` | Discard result, ready for a new idea |

Prefix matching means `/q`, `/qu`, `/qui`, `/quit`, `/quite` all resolve to `quit`.

---

## Notion Database

The bot logs accepted content to a Notion database with these columns:

| Column | Type | Content |
|---|---|---|
| Title | Title | First line of generated content |
| Type | Select | LinkedIn Post / Twitter Thread / Notion Page |
| Source Idea | Text | The raw idea you sent |
| Content | Text | Full generated output |
| Tokens | Number | Total token usage (draft + humanizer) |
| Created | Date | When you accepted |

**Important:** Share the database's parent page with your integration (Notion → page → `...` → Connections → add your integration).

---

## CI/CD

Every push to `main` runs:

```
ruff lint → mypy typecheck → pytest → deploy (placeholder)
```

Local equivalents:
```bash
make lint       # ruff check src/
make typecheck  # mypy src/
make test       # pytest
make ci         # all three
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `openai` | Talks to DeepSeek (and OpenAI as fallback) |
| `httpx` | Async HTTP client for Telegram + Notion APIs |
| `python-dotenv` | Loads `.env` file into environment |
| `pydantic` | (Installed for future use — structured output validation) |
| `supabase` | (Installed for future use — analytics/logging) |
