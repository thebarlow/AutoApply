# AutoApply

<table style="border: none; border-collapse: collapse;">
<tr>
<td><img src="./assets/icon.png" width="160"></td>
<td>Capture job postings from LinkedIn, Indeed and remote job boards, score how well each one fits you, and generate a tailored résumé and cover letter for it. Review and edit the result, export clean PDFs, then apply.</td>
</tr>
</table>

**Live at [autoapply.matthewbarlow.me](https://autoapply.matthewbarlow.me).** Sign in with Google.

---

## Using the hosted app

1. **Sign in** with Google. Anyone with a verified Google account can create an account.
2. **Choose how AI is paid for.** Every AI action (scoring, generation, résumé parsing) runs on a language model.
   - **Your own API key (free).** Paste an OpenRouter, OpenAI, Anthropic or Google Gemini key in your user settings and pick any text model your key offers. AutoApply charges nothing; your provider bills you directly. Keys are stored encrypted and never shown again.
   - **Credits.** No key? Buy a prepaid credit pack through Stripe. Each action has a fixed price, shown before you run it.
3. **Build your profile.** Upload your master résumé and AutoApply parses it into editable sections, or fill them in by hand. The richer the profile, the better the tailoring.
4. **Add jobs**, in any of three ways:
   - the **browser extension** on a LinkedIn or Indeed posting (see below);
   - the **Find Jobs** tab, which searches Remotive and RemoteOK;
   - pasting a posting in by hand.
5. **Work each job** from the dashboard:
   - **Score** compares the posting to your profile and shows which required skills you have and which you're missing.
   - **Résumé** and **Cover letter** generate tailored documents. Edit any field directly, or leave notes on a section and let the model revise it. An ATS check confirms the rendered PDF still reads correctly.
   - **Apply** opens the original posting. Download the PDFs, or drag them in from the desktop tray app if you run AutoApply locally.

AutoApply is free with your own key. If it helped you, you can [buy me a coffee](https://buymeacoffee.com/mrbarlow).

### Browser extension

The extension adds a Scrape button to LinkedIn and Indeed job pages and sends postings to your account. On supported application forms (Greenhouse, Lever, Ashby) it can show and fill the fields AutoApply mapped from your profile.

It isn't in the Chrome or Firefox stores yet, so load it from this repository:

- **Chrome:** open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked**, and select the `browser-extension` folder. The file picker shows folders only, which is expected.
- **Firefox:** open `about:debugging`, choose **This Firefox**, click **Load Temporary Add-on…**, and select `browser-extension/manifest.json`.

Then click the extension icon and sign in.

---

## Running it locally

Requirements: Windows, Git, and Node 18+. `setup.bat` installs Python 3.10+ and [pandoc](https://pandoc.org/installing.html) through winget if they're missing.

```bash
git clone https://github.com/thebarlow/AutoApply.git
cd AutoApply
setup.bat          # creates .venv, installs Python deps, Playwright Chromium and pandoc,
                   # initializes the database, and builds the dashboard
```

Copy `.env.example` to `.env` and set an LLM provider:

```ini
LLM_PROVIDER_TYPE=openrouter      # openrouter | openai | anthropic | gemini
LLM_API_KEY=your-provider-key
LLM_DEFAULT_MODEL=openai/gpt-4o-mini
```

If you have [Claude Code](https://claude.com/claude-code) installed and signed in, `LLM_PROVIDER_TYPE=claude_cli` uses your local `claude` CLI instead of an API key. This works for local development only; the hosted app refuses it.

```bash
start.bat          # API server (port 8080) + desktop tray app
start.bat dev      # also runs the Vite dev server with hot reload
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080). Locally there is no login: the app runs as a single user on a SQLite database (`auto_apply.db`).

---

## How it's built

| Layer | Stack |
|---|---|
| API | FastAPI, SQLAlchemy, Alembic; SQLite locally, PostgreSQL in production |
| Frontend | React, Vite, Tailwind |
| LLM | OpenAI SDK against any OpenAI-compatible provider; responses validated against Pydantic schemas with JSON-repair retries |
| Documents | Typed JSON stored in the database is the source of truth; Markdown → pandoc → Jinja2 HTML → headless Chromium → PDF |
| Auth | Google OAuth (Authlib), signed-cookie sessions |
| Billing | Prepaid fixed-price credits, Stripe Checkout and webhooks |
| Extension | Manifest V3 (Chrome and Firefox) |
| Hosting | Railway: Docker build, managed Postgres, migrations run on startup |

Some design decisions:

- **Multi-tenant by construction.** Every tenant-owned row carries a `profile_id`. Queries go through a scoping helper, and a SQLAlchemy `before_flush` guard rejects writes that cross tenants.
- **Bring-your-own-key billing.** A user's own key is encrypted at rest (Fernet) and pinned for the length of each action. Removing the key partway through can't push the rest of that action onto the platform key unbilled.
- **Structured LLM output.** Generated documents are schema-validated JSON, not free-form Markdown, so users can edit individual fields and the model can patch individual sections.
- **Defensive rendering.** User and model content is never rendered as raw HTML, and Chromium renders PDFs offline with JavaScript disabled.
- **Fail-closed configuration.** Security checks resolve the environment through one helper. A missing `APP_ENV` on the host is treated as production, and an unrecognized value stops the app from starting.
- **Operational visibility.** Structured JSON logs, plus an admin error log that groups repeated errors by fingerprint with an atomic upsert.

The full architecture is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### Tests

```bash
.venv/Scripts/python -m pytest -q              # backend (~1,200 tests)
cd react-dashboard && npx vitest run            # frontend
cd e2e && npm test                              # Playwright smoke tests against a local stack
```

---

## Privacy

See the [Privacy Policy](https://autoapply.matthewbarlow.me/privacy) and [Terms](https://autoapply.matthewbarlow.me/terms).
