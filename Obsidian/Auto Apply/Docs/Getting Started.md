---
order: 1
---
Auto Apply generates custom résumés and cover letters tailored to specific job postings. Everything runs in your browser at **autoapply.matthewbarlow.me** — there's nothing to install. Every custom document needs two things: your profile and a job.

# Setting up your profile
Your account has a single profile that holds everything Auto Apply knows about you — your work history, skills, education, and projects. The fastest way to fill it in is to upload your master résumé during the first-run setup; Auto Apply parses it into structured fields you can then edit by hand.

To edit your profile at any time, click your name in the dashboard. This opens your profile directly in its edit view. The richer and more accurate your profile, the better your generated documents will be — see **Making a Good Master Resume** for tips.

> **You do not need an LLM API key.** Auto Apply runs the AI for you. Each AI action (scoring a job, generating a résumé or cover letter) draws from your **credit** balance, shown in the navbar. New accounts start with a small grant; you can buy more credits at any time from the navbar.

# Adding jobs
Click the **+ Upload** button at the top of the Inbox widget and fill in the fields:

- **Title** *(required)* — the job title.
- **Description** *(required)* — paste the full job description. This is what the AI tailors your documents to, so include as much detail as you can.
- **Company**, **Location**, **Salary** — optional context that improves scoring and generation.
- **Job URL** — optional link back to the original posting; also used to detect duplicates. Uploading a URL that already exists is rejected as a duplicate.

Click **Upload** and the job lands in your Inbox, where the server processes the raw description into a structured form. You can watch this happen in real time in the Inbox widget.

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
