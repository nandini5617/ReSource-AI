# ReSource AI: project handover

## Status

Working Streamlit app with a cloud-AI agent, photo analysis, organisation matching,
human-controlled exchanges and estimated impact. Documentation written after the work below.

## File inventory

| File | Purpose |
|---|---|
| `app.py` | Navigation shell; sidebar; calls `views/*.render()` |
| `views/_common.py` | Session state, flash messages, navigation helpers, table/chart helpers |
| `views/dashboard.py`, `chat.py`, `add_resource.py`, `explorer.py`, `exchanges.py`, `impact.py` | Pages |
| `ui_theme.py` | Green theme CSS, badges, metric cards |
| `tools.py` | Agent tools + USER-ONLY exchange functions (safety-critical) |
| `agent.py` | Agent wrapper, system prompt, offline pipeline |
| `ai_router.py` | Provider fallback, tool loop, loop-guard, cooldown |
| `gemini_client.py` | Only module importing Google's SDK |
| `vision.py` | Image validation, preparation, vision routing |
| `analysis.py` | Text classification and reuse ideas (router + keyword fallback) |
| `matching.py`, `impact.py`, `knowledge.py`, `memory.py` | Matching, estimates, constants, session memory |
| `database.py` | SQLite schema and writes |
| `stats.py` | Read-only queries for pages |
| `config.py` | Settings, keys from environment, `is_mock_mode()`, vision settings, `redact()` |
| `main.py` | Command-line interface |
| Tests | `test_offline`, `test_exchange_safeguards`, `test_vision`, `test_stats`, `test_explorer`, `test_exchanges`, `test_impact`, `test_router_guard`, `test_app`, `run_all_tests`, `audit_project`, `test_vision_providers` (live), `test_gemini` (legacy, live) |
| Legacy/unused | `groq_client.py`, `openrouter_client.py` (not imported by anything) |

Dependencies flow: pages → `tools`/`stats`/`database`; `tools` → `analysis`/`matching`/`impact`/`database`; `agent` → `ai_router`/`tools`/`memory`.

## Database (SQLite, `data/resource_ai.db`)

- `resources(id, name, category, material, condition, quantity, unit, location, disposition, notes, status, created_at)`; status: available, requested, transferred.
- `organizations(id, name, org_type, role, city, area, accepts, conditions, min_kg, max_kg, description)`; seeded with fictional `[Demo]` entries.
- `exchanges(id, resource_id, org_id, status, message, created_at, updated_at, completed_at)`; status: pending, approved, rejected, completed, cancelled.
- `impact_log(id, exchange_id, resource_id, category, action, kg_diverted, co2e_avoided_kg, is_estimate, created_at)`.
- Existing records include test data (e.g. test exchanges 1 and 2 and later resources). Not verified real-world exchanges.

## Exchange safety

`dispatch()` is the only path the AI can reach: it may create a pending request and cancel. Approval, rejection and completion exist only as `confirm_exchange_approval`, `reject_exchange`, `confirm_exchange_completion` (they require the real boolean `True`). Both the UI (checkbox then button) and tests rely on this. Do not weaken it, and do not add these functions to `_HANDLERS` or `TOOL_DECLARATIONS`.

## Test results (as reported by the project owner)

| Suite | Result |
|---|---|
| test_offline | 37 checks passed |
| test_exchange_safeguards | 31 |
| test_vision | 32 |
| test_stats | 23 |
| test_explorer | 18 |
| test_exchanges | 25 |
| test_impact | 12 |
| test_router_guard | 15 |
| test_app | 34 |
| audit_project | 0 problems |
| Environment | Python 3.13.15, Streamlit 1.67.0 |

Live results: Groq text analysis worked; Groq vision passed one probe on a synthetic image;
Gemini returned 404 (old model) then 429 (quota); OpenRouter Nemotron rejected images.
A cloud chat answer once looped on "Rohoni?"; after the router guard, one retry gave a normal answer (one retry only).
Browser walkthrough of the redesigned app: reported as "everything is fine" with no per-step detail.
Not reported: real-photo results, bad-file messages, download checks, restart persistence, Gemini/OpenRouter text fallback in a live run.

## Known issues

1. Gemini quota (429) and unverified model names; verify IDs in provider dashboards.
2. Cloud chat can save duplicate resources on retries; the model once may have changed a quantity (15 to 16, unconfirmed).
3. Offline mode uses the full sentence as the item name.
4. Placeholder emission factors; sample organisations.
5. "Organisation declined" is enabled by the "organisation has accepted" checkbox (wording only).
6. Approval time not stored.
7. Legacy files and `test_gemini.py` still present.

## Next tasks

Duplicate-save guard, sourced emission factors, real organisation data, `approved_at` migration,
clearer decline wording, live tests for Gemini/OpenRouter fallback, deployment and Nonilion integration (reuse `tools.py`).

## Commands

```
cd C:\Users\NANDINI\Desktop\ReSource-AI
python run_all_tests.py
streamlit run app.py
python test_vision_providers.py     (live, uses quota)
```

## Notes for the next developer or AI assistant

Never ask for or print `.env`. Use cloud APIs only. Keep tests offline except the explicit probe.
Provide complete files, not snippets. Preserve exchange safeguards and the `RESOURCE_AI_MOCK` semantics
(`1/true/always` = offline). Check `config.get_vision_providers()` before sending any image.