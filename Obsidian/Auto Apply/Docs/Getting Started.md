---
order: 1
---
Auto Apply is an app for generating custom Resumes and Cover Letter for jobs on LinkedIn. Every custom document needs two things : A User and a Job. 

# Setting up your User Profile
Auto Apply offers the functionality to set up multiple user profiles. While it is not necessary to set up multiple profiles, we leave you this option open so that you can maximize the output of your generated documents.
You could have one profile for : Data Scientist, one for Software Dev, one for Quant, etc.

## Setting up your LLM Provider
Auto Apply leans heavily on Large Language Models (LLM) for the production of customized documents. To use most of the features, you must provide a working API key to a major LLM Provider. 

- [OpenRouter API Key](https://openrouter.ai/workspaces/default/keys) : Assortment of many frontier models
- [OpenAI API Key]() : ChatGPT
- [Claude API Key](https://platform.claude.com/dashboard) : Anthropic
- [Gemini API Key]() : Google

After signing up for your preferred LLM Provider, you can input your Preferred model and API key. If you're not sure which model to pick don't worry, we have a reasonable default selected for each of the configured Providers.

The user is encouraged to test different models at different stages of the generation process to maximize output to cost efficiency.
# Installing the browser extension

This service uses a custom browser extension to scrape jobs from the LinkedIn job board. 

## Firefox Install Instructions 
1. In your browser's url bar, navigate to about:debugging
2. Select "This Firefox" from the tabs on the left sidebar
3. Click "Load Temporary Add-on..."
4. Select auto_apply/browser-extension/manifest.json

### Chrome Install Instructions

1. In your browser's url bar, navigate to: chrome://extensions
2. Enable developer mode in the top right
3. Click "Load unpacked"
4.  Select auto_apply/browser-extension/manifest.json

# Generating your Documents
Once your job is scraped, our servers automatically begin processing the raw job description into something more structured. You can see this process happening in real time in the inbox widget of the dashboard. 

## Manually Uploading a Job
The browser extension is the easiest way to add jobs, but you can also enter one by hand — useful for postings that aren't on LinkedIn or that the extension can't reach.

Click the **+ Upload** button at the top of the Inbox widget to open the upload form. Fill in the fields:

- **Title** *(required)* — the job title.
- **Description** *(required)* — paste the full job description. This is what the LLM tailors your documents to, so include as much detail as you can.
- **Company**, **Location**, **Salary** — optional context that improves scoring and generation.
- **Job URL** — optional link back to the original posting; also used to detect duplicates. Uploading a URL that already exists is rejected as a duplicate.

Click **Upload** and the job lands in your Inbox, where it's processed exactly like a scraped job.

Select a Job Card in your Inbox to interact with it. It will appear on the right of your screen in the Preview tab. If you do not see it, you probably need to exit out of your User Profile settings. They use the same widget.

The Job Card Preview view has a row of tabs for 
- Description : Where you can view the raw scraped description of the job along with the AI Processed version. The processed version is what it fed into subsequent LLM calls
- Resume : Custom Document Generation
- Cover Letter : Custom document Generation
- Score : An assessment of how well you fit the job, and how well the job fits you

Navigating to one of these tabs reveals a unique action button on the right, allowing you to generate the associated document, calculate a compatibility score, or (re)process the description. 
Each of these actions is associated with a specific prompt under the active user profile, which are all customizable. Reasonable defaults are set to start you off. 

# Applying to a Job
Once you have generated at least a cover letter for a specific job, clicking on it will reveal an Apply button in the Preview window. Clicking this apply button will navigate you back to the initial posting, and open our system tray app.
The tray app lets you drag your generated files into LinkedIn, or the ATS's file upload bars. 
Pressing the checkmark next to the associated Resume and Cover Letter in the tray app will remove them and mark the job as applied. You can later view it in the dashboard under "Archives". Pressing the x will remove the files from the tray app, and mark the job as "deleted". Deleted jobs move to Archives and are recoverable until the user closes the server. They are cleaned up and removed from the database on server start.
# Customizing your User Profile
