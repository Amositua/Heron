# Heron

The Splunk app that builds and maintains itself.

## What it does

Heron is an autonomous agent that turns a plain-English monitoring request into a working Splunk app. It plans, generates, and deploys the app's inputs, parsing rules, dashboards, and alerts, then validates that it's actually working in Splunk. After deployment, Heron keeps watching the app in production and proposes (or auto-applies) tuning changes as real data comes in.

## Tech stack

- **Backend**: Python 3.11+, FastAPI, async throughout
- **LLM provider**: Google Gemini (`gemini-2.5-flash`) via the official `google-genai` SDK
- **Splunk integration**: Splunk Python SDK for reads, Splunk MCP Server for all writes
- **Frontend**: Next.js (App Router), TypeScript, Tailwind CSS
- **Database**: SQLite (`aiosqlite`)
- **Streaming**: Server-Sent Events for the live build view
- **Templates**: Jinja2 for Splunk conf-file generation

## Quick start

> Placeholder — full setup instructions land as the backend and frontend take shape.

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e .
uvicorn heron.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## License

MIT — see [LICENSE](LICENSE).
