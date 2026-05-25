# Uploading Jobs

There are two ways to get jobs into the pipeline:

## Browser extension (LinkedIn, Indeed)

Install the browser extension from `browser-extension/`. With it active, opening a LinkedIn or Indeed job posting will surface a "Save to Auto Apply" button. Saved jobs appear in your Inbox with `state=pending`.

## API scrapers (Remotive, RemoteOK)

The scraper runner (`scraper/`) polls remote-job-board APIs on a schedule and saves matching jobs. Configure search terms and filters in your scraper config. Run it manually with `python -m scraper.runner` or via the tray app.

## What happens next

New jobs land in **Inbox**. Score them, generate tailored documents, and apply. Jobs you've handled move to **Archive**.
