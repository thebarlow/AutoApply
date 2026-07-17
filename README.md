# Auto Apply


<table style="border: none; border-collapse: collapse;">
<tr>
<td><img src="./assets/icon.png" width="200"></td>
<td>Semi-automated job scraping, tailored resume + cover letter generation, and application management. Scrape a LinkedIn posting with the browser extension, let an LLM tailor your documents to it, then drag-and-drop them into the application via the system tray app.</td>
</tr>
</table>

---

## 1. Download & Setup

### Requirements

- **Python 3.10+** must be installed ([python.org/downloads](https://www.python.org/downloads/)). The server, tray app, and scrapers all run on Python.

### New to Git?

`git` is the tool used to download (clone) this project. If you don't have it yet:

1. Download the official installer from **[git-scm.com/downloads](https://git-scm.com/downloads)** and pick your operating system.
2. Run the installer and accept the defaults — no special options are needed.
3. Close and reopen your terminal (or Command Prompt) so it picks up the new `git` command.
4. Confirm it works by running `git --version`; you should see a version number.

Once that prints a version, continue with the clone command below.

```bash
git clone https://github.com/thebarlow/AutoApply.git
cd auto_apply
setup.bat
```

`setup.bat` installs Python if needed, creates the `.venv` virtual environment, and deletes itself on success. You can skip it and run `start.bat` directly — it detects a missing setup and runs `setup.bat` automatically on first launch.

---

## 2. Start the App

```bash
start.bat
```

This launches the FastAPI server (port 8080) in its own console window and the PyQt6 system tray app in the foreground.

Then open the dashboard at **[http://127.0.0.1:8080/](http://127.0.0.1:8080/)**.

On first launch you'll land in the onboarding flow.

---

## 3. Onboarding

### Create a User Profile

Every generated document needs two things: a **User** and a **Job**. You must create at least one User Profile, which can seed itself from your existing master resume. You can create multiple profiles to target different roles (e.g. Data Scientist, Software Dev, Quant) and maximize document quality.

> Tip: A detailed master resume produces better output. The richer your profile, the more material the LLM has to tailor from. Read the job **Score** breakdowns to see what your profile is missing relative to a posting.

### Add an LLM Provider key

Auto Apply relies on a Large Language Model for all document generation. Your profile must include a working API key from a major provider — this key determines which models are used for every generation task. Pick a provider and create a key:

- **[OpenRouter](https://openrouter.ai/workspaces/default/keys)** — access to many frontier models
- **[OpenAI](https://platform.openai.com/api-keys)** — ChatGPT models
- **[Anthropic / Claude](https://platform.claude.com/dashboard)**
- **[Google Gemini](https://aistudio.google.com/apikey)**

Each provider has a reasonable default model preselected. You're encouraged to experiment with different models at different generation stages to balance quality against cost.

### Install the browser extension

Jobs are scraped from the LinkedIn job board via a custom browser extension.

**Firefox**
1. Navigate to `about:debugging`
2. Select **This Firefox** in the left sidebar
3. Click **Load Temporary Add-on…**
4. Select `auto_apply/browser-extension/manifest.json`

**Chrome**
1. Navigate to `chrome://extensions`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked**
4. Select the `auto_apply/browser-extension/` folder

---

## 4. Generate & Apply

1. **Scrape** — use the extension on a LinkedIn posting. The job appears in your dashboard **Inbox**, and the server automatically processes the raw description into a structured form (visible in real time).
2. **Open the job** — click a Job Card in the Inbox; it opens in the **Preview** panel on the right. (If you don't see it, exit your User Profile settings — they share the same panel.)
3. **Work the tabs** — the Preview panel has tabs, each with an action button on the right:
   - **Description** — raw scraped text plus the AI-processed version fed into later LLM calls; can be re-processed.
   - **Resume** — generate a tailored résumé.
   - **Cover Letter** — generate a tailored cover letter.
   - **Score** — assess how well you fit the job and how well the job fits you.

   Each action uses a customizable prompt under the active profile, with sensible defaults to start.
4. **Apply** — once at least a cover letter exists, the job's Preview shows an **Apply** button. It reopens the original posting and launches the system tray app. Drag the generated files from the tray into LinkedIn or an ATS upload field.
5. **Mark applied** — in the tray app, the checkmark next to a document marks the job **applied** (moves it to **Archives**). The **x** marks it **deleted** (also moves to Archives, recoverable until the server restarts; cleaned from the DB on next start).

---

## Further Help

- Technical architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- In-app help docs: **[http://127.0.0.1:8080/docs](http://127.0.0.1:8080/docs)** (server must be running).
- FastAPI endpoints reference: **[http://127.0.0.1:8080/endpoints](http://127.0.0.1:8080/endpoints)**.

### Dev server (UI development)

For live-reloading React changes, run the Vite dev server from `react-dashboard/`:

```bash
npm run dev
```

It serves the dashboard on **[http://localhost:5173](http://localhost:5173)** against the same backend. Frontend errors surface in the browser console (F12 → Console); backend errors appear in the server console window opened by `start.bat`.
</content>
</invoke>
