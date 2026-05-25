nav to the worktree folder .claude/worktrees/{name}
make sure to tell Claude to have use the data



- [](http://localhost:8080/#/docs/uploading-jobs)

# Uploading Jobs

There are two ways to get jobs into the pipeline:

## Browser extension (LinkedIn, Indeed)

Install the browser extension from `browser-extension/`. With it active, opening a LinkedIn or Indeed job posting will surface a "Save to Auto Apply" button. Saved jobs appear in your Inbox with `state=pending`.

## API scrapers (Remotive, RemoteOK)

The scraper runner (`scraper/`) polls remote-job-board APIs on a schedule and saves matching jobs. Configure search terms and filters in your scraper config. Run it manually with `python -m scraper.runner` or via the tray app.

## What happens next

New jobs land in **Inbox**. Score them, generate tailored documents, and apply. Jobs you've handled move to **Archive**.


- [](http://localhost:8080/#/docs/llm-providers)
- [uploading jobs](http://localhost:8080/#/docs/uploading-jobs)

# LLM Providers

The app needs an LLM provider to score jobs and tailor resumes.

## Getting an API key

- **Anthropic:** Sign up at [https://console.anthropic.com](https://console.anthropic.com) → API Keys → Create Key. Recommended models: `claude-haiku-4-5-20251001` (cheap), `claude-sonnet-4-6` (higher quality).
- **OpenAI:** Sign up at [https://platform.openai.com](https://platform.openai.com) → API Keys. Recommended models: `gpt-4o-mini` (cheap), `gpt-4o` (higher quality).

## Picking a model

Smaller/cheaper models (Haiku, gpt-4o-mini) are fine for scoring jobs. For generating tailored resumes and cover letters, larger models (Sonnet, gpt-4o) produce noticeably better output.

## Cost

Scoring a single job typically costs a fraction of a cent. Generating a tailored resume + cover letter is usually 1–5 cents depending on model and length.