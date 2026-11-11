# ReSource AI

An AI agent that gives unused, surplus and discarded resources a second life.
**SecondLife** (reuse and redistribution) + **WasteWise** (smart waste decisions).

Describe an item or upload a photo. The agent classifies it, recommends reuse,
repair, recycling or disposal, ranks organisations that could take it, and tracks
the exchange with approvals that only a human can give.

## Problem and objectives

Usable items such as furniture, books, clothes and electronics are often thrown
away because the owner does not know who needs them. ReSource AI aims to:

1. Identify and classify a resource, and recommend the best action (reuse > repair > recycle > dispose).
2. Rank organisations that could take it, with explanations.
3. Track exchange requests with human-controlled approval and completion.
4. Show an estimate of the waste diverted and the CO2e avoided.

## Features

- **AI chat agent**: Gemini/Groq/OpenRouter models call tools (analyse, save, match, ideas, impact, request, list).
- **Photo analysis**: JPG/JPEG/PNG/WEBP upload, preview, in-memory analysis by a vision model. You confirm quantity, unit, city and condition before saving.
- **Resource Explorer**: search, filters, cards, details, match scores with reasons.
- **Exchanges**: status badges, timeline, separate confirmations for acceptance and hand-over.
- **Impact**: estimated totals, by-category charts, trend, CSV and Markdown report downloads.
- **Dashboard**: counts, charts, recent activity.
- **Offline demo mode**: keyword rules, no API key needed.

## Exchange safety rules

- The AI can create a **pending** request and cancel one. It **cannot** approve, reject or complete.
- Approval requires you to tick "the organisation has accepted", then press Approve.
- Completion requires a **separate** tick "the hand-over really happened", then Mark completed.
- Impact is recorded once, only when completion is confirmed. A completed exchange cannot be completed again.
- These rules are enforced in `tools.py`, not just in the UI.

## Technology

Python 3.13, Streamlit, SQLite, Pillow, cloud AI via the Groq, Google Gen AI (Gemini) and OpenAI-compatible (OpenRouter) SDKs. No local models.

## Architecture

```
Streamlit pages (views/) ──> tools.py ──> database.py / matching.py / impact.py / analysis.py
        │                        ▲
        │                        └── agent.py ──> ai_router.py ──> Groq → Gemini → OpenRouter
        └──> stats.py (read-only)         vision.py ──> vision providers (separate list)
```

- `ai_router.py`: tool-calling loop with automatic fallback, 60 s cooldown for a failing provider, and a guard that discards looping (repetitive) answers.
- `vision.py`: image validation (real contents, size, format), re-encoding to JPEG without metadata, vision-only routing. Images are never sent to text-only models and never saved to disk.
- `tools.py`: the only code that changes exchange status. User-only functions are not visible to the AI.

## Folder structure

```
ReSource-AI/
├── app.py                 navigation shell
├── config.py  knowledge.py  impact.py  database.py  stats.py  matching.py  memory.py
├── analysis.py  tools.py  agent.py  ai_router.py  gemini_client.py  vision.py  ui_theme.py  main.py
├── views/                 _common, dashboard, chat, add_resource, explorer, exchanges, impact
├── test_*.py  run_all_tests.py  audit_project.py
├── requirements.txt  .env.example  .gitignore
├── data/ (SQLite database, created automatically)
└── groq_client.py  openrouter_client.py  test_gemini.py   (legacy, not used by the app)
```

## Installation (Windows, VS Code)

```
cd C:\Users\NANDINI\Desktop\ReSource-AI
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
```

Open `.env`, add the keys you have, and never share this file.

## Provider configuration and fallback

Text providers are tried in the order Groq, Gemini, OpenRouter (change with `RESOURCE_AI_PRIMARY_PROVIDER`).
If one fails, times out, hits quota or returns a looping answer, the next is used.
Photo analysis uses a separate list (`RESOURCE_AI_VISION_ORDER`) and only providers with a `*_VISION_MODEL` set.

| Provider | Text | Photo analysis |
|---|---|---|
| Groq `qwen/qwen3.8-27b` | Tested live | Passed one live probe on a synthetic image; your own use of real photos was reported as fine, without details |
| Gemini `gemini-3.8-flash` | Not live-verified (quota 429 seen) | Quota error 429 at last probe |
| OpenRouter (Nemotron) | Configured, not live-tested through the router | Not supported (text-only: "no endpoints support image input") |

Model names change. The old default `gemini-2.5-flash` was reported unavailable to new keys. Check each provider's current model list.

## Running

```
streamlit run app.py          web app
python main.py                command line (/approve and /complete ask you to type yes)
python main.py --mock "3 old chairs"   offline
```

## Using the app

1. **AI Chat** or **Add Resource**: describe an item or upload a photo, review, and save.
2. **Explorer**: open a resource, read the match reasons, press Request exchange.
3. **Exchanges**: after the organisation replies, tick the box and Approve; after the hand-over, tick the second box and Mark completed.
4. **Impact**: view estimates and download the report.

## Testing

```
python run_all_tests.py          all offline suites + audit, no network
python test_vision_providers.py  LIVE probe, uses a little API quota
```

Offline suites: offline (37 checks), exchange safeguards (31), vision (32), stats (23),
explorer (18), exchanges (25), impact (12), router guard (15), app (34), project audit.
The numbers are the results you reported; re-run to confirm on your machine.

## Installation and Setup

### 1. Clone the repository

```bash
git clone https://github.com/nandini5617/ReSource-AI.git
cd ReSource-AI
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API keys

Copy `.env.example` and rename the copy to `.env`.

Add your own API keys for Groq, Gemini and OpenRouter.

API keys can be obtained from their respective developer consoles. Never commit your `.env` file to GitHub.

### 4. Run the application

```bash
streamlit run app.py
```

### Important

ReSource AI uses external AI APIs for live AI-powered responses. Users must configure their own API keys and are subject to the providers' usage limits and pricing.

Without API keys, only the application's available offline or rule-based functionality will work.

## Limitations

- The organisation directory is **sample data**, not real NGOs. Availability must be confirmed.
- Impact factors in `impact.py` are **placeholders**; all impact numbers are estimates, not measurements.
- A photo cannot show weight, quantity, material or hidden defects; vision results are suggestions.
- Offline mode names an item with the whole input sentence.
- In cloud chat, retrying a request can save a duplicate resource record.
- The approval time of an exchange is not stored (timeline shows "time not recorded").
- Free-tier APIs have rate limits and can fail; fallback reduces but does not remove this.
- Model quality: an LLM may misreport a detail such as a quantity; check the saved record.

## Future scope

Real organisation onboarding and contact, sourced emission factors, duplicate detection,
an `approved_at` column, user accounts, deployment (for example Streamlit Community Cloud,
secrets via the host's secret manager) and integration with Nonilion.com through the same `tools.py` functions.
