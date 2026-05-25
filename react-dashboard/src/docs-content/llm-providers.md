# LLM Providers

The app needs an LLM provider to score jobs and tailor resumes.

## Getting an API key

- **Anthropic:** Sign up at <https://console.anthropic.com> → API Keys → Create Key. Recommended models: `claude-haiku-4-5-20251001` (cheap), `claude-sonnet-4-6` (higher quality).
- **OpenAI:** Sign up at <https://platform.openai.com> → API Keys. Recommended models: `gpt-4o-mini` (cheap), `gpt-4o` (higher quality).

## Picking a model

Smaller/cheaper models (Haiku, gpt-4o-mini) are fine for scoring jobs. For generating tailored resumes and cover letters, larger models (Sonnet, gpt-4o) produce noticeably better output.

## Cost

Scoring a single job typically costs a fraction of a cent. Generating a tailored resume + cover letter is usually 1–5 cents depending on model and length.
