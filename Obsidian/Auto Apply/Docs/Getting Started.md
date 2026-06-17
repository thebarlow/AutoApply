---
order: 1
---
Auto Apply generates custom résumés and cover letters tailored to specific job postings. Everything runs in your browser at **autoapply.matthewbarlow.me** — there's nothing to install on your machine except the optional browser extension described below. Every custom document needs two things: your profile and a job.

# Setting up your profile
Your account has a single profile that holds everything Auto Apply knows about you — your work history, skills, education, and projects. The fastest way to fill it in is to upload your master résumé during the first-run setup; Auto Apply parses it into structured fields you can then edit by hand.

To edit your profile at any time, click your name in the dashboard. This opens your profile directly in its edit view. The richer and more accurate your profile, the better your generated documents will be — see **Making a Good Master Resume** for tips.

> **You do not need an LLM API key.** Auto Apply runs the AI for you. Each AI action (scoring a job, generating a résumé or cover letter) draws from your **credit** balance, shown in the navbar. New accounts start with a small grant; you can buy more credits at any time from the navbar.

# Installing the browser extension
Auto Apply uses a browser extension to capture job postings directly from the LinkedIn and Indeed job boards and send them to your account. Installing it is optional — you can always add jobs by hand (see below) — but it's the easiest way to get postings in.

**[⬇ Download the extension](/extension/download)** (a `.zip`). Unzip it somewhere you'll keep it (don't delete the folder afterward — the browser loads it from that location), then follow the instructions for your browser.

## Chrome / Edge install instructions
1. Navigate to `chrome://extensions` (or `edge://extensions`) in your URL bar.
2. Enable **Developer mode** (toggle in the top right).
3. Click **Load unpacked**.
4. Select the unzipped extension folder (the one containing `manifest.json`).
5. Open the extension and sign in with the same account you use on the website.

## Firefox install instructions
1. Navigate to `about:debugging` in your URL bar.
2. Select **This Firefox** from the left sidebar.
3. Click **Load Temporary Add-on…**
4. Select the `manifest.json` file inside the unzipped extension folder.
5. Open the extension and sign in with the same account you use on the website.

Once installed and signed in, browse to a LinkedIn or Indeed job posting and use the extension to send it to your Inbox.

# Adding jobs

## With the extension
On a LinkedIn or Indeed job posting, open the extension and capture the job. It lands in your Inbox, where our servers automatically process the raw description into a structured form. You can watch this happen in real time in the Inbox widget.

## Manually uploading a job
You can also enter a job by hand — useful for postings the extension can't reach. Click the **+ Upload** button at the top of the Inbox widget and fill in the fields:

- **Title** *(required)* — the job title.
- **Description** *(required)* — paste the full job description. This is what the AI tailors your documents to, so include as much detail as you can.
- **Company**, **Location**, **Salary** — optional context that improves scoring and generation.
- **Job URL** — optional link back to the original posting; also used to detect duplicates. Uploading a URL that already exists is rejected as a duplicate.

Click **Upload** and the job lands in your Inbox, processed exactly like a captured job.

# Generating your documents
Select a job card in your Inbox to open it in the Preview tab on the right. (If you don't see it, exit your profile edit view first — it shares the same panel.)

The job preview has a row of tabs:
- **Description** — the raw posting alongside the AI-processed version that's fed into later AI calls.
- **Résumé** — generate a tailored résumé.
- **Cover Letter** — generate a tailored cover letter.
- **Score** — an assessment of how well you fit the job and how well the job fits you.

Each tab reveals an action button that generates the associated document, calculates a compatibility score, or (re)processes the description. Each action runs against a customizable prompt; reasonable defaults are set to start you off, and each action spends credits.

After generating, you can refine a document with feedback or edit its fields directly using the pencil (✎) button on the Résumé/Cover toolbar.

# Applying to a job
Once you've generated your documents for a job, download the résumé and cover-letter PDFs from the preview and submit them through the employer's application form. When you're done, mark the job as applied; it moves to **Archives**, where you can review it later.
