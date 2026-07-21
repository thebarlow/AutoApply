import { request, type FullConfig } from '@playwright/test';

/**
 * Establish a logged-in session once, before any spec runs, via the gated
 * dev-login endpoint (POST /api/dev/login — non-production only). The resulting
 * session cookie is saved to storageState.json, which every spec loads, so the
 * authenticated dashboard renders without driving Google OAuth.
 */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL as string;
  const ctx = await request.newContext({ baseURL });
  const res = await ctx.post('/api/dev/login');
  if (!res.ok()) {
    throw new Error(
      `dev-login failed: ${res.status()} ${await res.text()}. ` +
        `Is the backend running with APP_ENV != production and an account in the DB?`,
    );
  }
  await ctx.storageState({ path: 'storageState.json' });
  await ctx.dispose();
}
