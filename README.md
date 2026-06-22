# Telegram Content Factory

AI-powered content repurposing bot. Users send raw ideas, voice notes, or links via Telegram →
AI transforms them into polished LinkedIn posts, Twitter threads, or Notion pages.

## Architecture

```
Telegram Message
      │
      ▼
┌─────────────────┐
│  Workflow Router │  ← Hybrid (rules → AI fallback)
│ Intent Classifier│
└────────┬────────┘
         │
    ┌────┴────┬─────────┐
    ▼         ▼          ▼
LinkedIn   Twitter    Notion
  Post     Thread      Page
    │         │          │
    └────┬────┴────┬─────┘
         ▼         ▼
   Shared Services (OpenAI, Telegram, Notion)
```

## Project Structure

```
src/
├── main.py                  # Entry point (polling loop)
├── router/                  # Decision layer
│   ├── workflow_router.py   # Rule-based + AI hybrid
│   └── intent_classifier.py # LLM intent classification
├── workflows/               # Content transformation pipelines
│   ├── linkedin_post/       # Idea → LinkedIn carousel/text
│   ├── twitter_thread/      # Idea → Twitter thread
│   └── notion_page/         # Idea → Notion doc
├── services/                # External API wrappers
│   ├── telegram_service.py  # Bot API (send/receive/poll)
│   ├── openai_service.py    # LLM (GPT-4.1)
│   └── notion_service.py    # Notion API (create pages)
├── models/                  # Data structures
│   ├── message.py           # Incoming Telegram message
│   └── content.py           # Generated content types
├── prompts/                 # AI prompt templates
│   ├── linkedin_prompt.txt
│   ├── twitter_prompt.txt
│   └── notion_prompt.txt
├── config/settings.py       # Config + env vars
└── utils/
    ├── logger.py            # Structured logging
    └── retry.py             # Retry + backoff decorator
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in your keys
python src/main.py
```

## Environment Variables

| Key | Purpose |
|-----|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token |
| `OPENAI_API_KEY` | OpenAI API key |
| `NOTION_API_KEY` | Notion integration token |
| `NOTION_PARENT_PAGE_ID` | Notion page to create content under |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |
