---
order: 2
tiers: friends_family, beta
---
The Auto Apply browser extension captures job postings straight from the **LinkedIn** and **Indeed** job boards and sends them to your Inbox — no copy-pasting. It's an optional companion to the website; you can always [add jobs by hand](#adding-jobs-by-hand) instead.

> This is an early-access feature available to Friends & Family and Beta users. It installs as an unpacked developer extension (not from the Chrome or Firefox stores yet), so expect the occasional rough edge — LinkedIn and Indeed change their pages often.

# Installing the extension
**[⬇ Download the extension](/extension/download)** — this gives you a `.zip` of the current version. Unzip it somewhere permanent (your browser loads it from that folder, so don't delete or move it afterward), then follow the steps for your browser.

## Chrome / Edge
1. Go to `chrome://extensions` (or `edge://extensions`).
2. Turn on **Developer mode** (toggle, top-right).
3. Click **Load unpacked** and select the unzipped folder (the one containing `manifest.json`).
4. The "Job Scraper" extension appears in your toolbar. Pin it for easy access.

## Firefox
1. Go to `about:debugging` → **This Firefox**.
2. Click **Load Temporary Add-on…**
3. Select the `manifest.json` file inside the unzipped folder.
4. The extension loads until you restart Firefox; re-add it the same way after a restart.

# Signing in
The extension posts jobs to **your** account, so it needs to be signed in.

1. Click the extension icon to open its popup.
2. Click **Sign in with Google** or **Sign in with GitHub** — use the same provider you use on autoapply.matthewbarlow.me.
3. A provider window opens; approve it, and the popup shows your signed-in email.

You must already have an Auto Apply account. If the extension reports **"No Auto Apply account,"** sign up on the website first, then sign in again. Use **Sign out** in the popup to disconnect the extension from your account.

# Capturing jobs
1. Browse to a job posting or a job-search results page on LinkedIn or Indeed.
2. The extension injects a **Scrape** button onto each job card (and a fixed button on single-job view pages).
3. Click **Scrape**. The button reports the result:
   - **✓ Scraped** — the job was sent to your Inbox.
   - **✓ Already staged** — you've already captured this one (deduped automatically).
   - **✗ Sign in required** — open the popup and sign in.
   - **✗ Timeout / Server error / Parse error** — try again, or reload the page and retry.

Captured jobs land in your Inbox, where the server processes the raw posting into a structured form — watch it happen live in the Inbox widget.

The extension remembers what you've already scraped to avoid duplicates. To reset that memory (e.g. to re-capture a job you deleted), open the popup and click **Clear scrape history**.

# Adding jobs by hand
For postings the extension can't reach, click **+ Upload** at the top of the Inbox widget and fill in the fields — **Title** and **Description** are required; Company, Location, Salary, and Job URL are optional. Click **Upload** and the job is processed exactly like a captured one.

# Troubleshooting
- **No Scrape buttons appear.** Reload the LinkedIn/Indeed page — the extension injects its buttons on page load, and reloading the *extension* alone doesn't re-inject into already-open tabs.
- **Sign-in fails with no provider window.** Reload the extension and try again; if it persists, contact support — your install's redirect URL may need allowlisting.
- **Wrong company/location on captured jobs.** LinkedIn and Indeed rearrange their pages frequently. Report it and we'll update the extension.
