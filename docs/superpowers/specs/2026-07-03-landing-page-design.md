# Landing / Marketing Page — Design

**Date:** 2026-07-03
**Status:** Approved (design), pending spec review
**Type:** Frontend feature (React dashboard), no backend changes

## Problem

The hosted app (`https://autoapply.matthewbarlow.me`) has no public marketing
surface. Logged-out visitors hit a bare `LoginScreen` (App.jsx:202) with two OAuth
buttons and one line of copy — no explanation of what the product is, who it's for,
or what it does. There is nothing to sell the product to a first-time visitor.

## Goal

A public marketing page ("About") that pitches AutoApply — **scrape jobs → tailor a
résumé & cover letter → apply** — with a clear call to action. Viewable whether or not
the visitor is signed in. The dashboard stays behind auth; the landing page renders in
front of it for logged-out visitors and remains reachable for logged-in users.

## Non-goals

- No pricing/credit-pack section (explicitly cut to avoid coupling to live packs data).
- No backend changes, no new API endpoints, no data fetching.
- No CMS / editable copy — copy is authored in-component.

## Behavior & Routing

Route name: **`/about`**.

- **Logged-out visitors** (`me === null`): **all routes redirect to `/about`** (URL
  normalizes to `/about`) and render the landing page. The landing page's sign-in card
  carries the Google/GitHub OAuth CTAs. The existing `?beta=closed` messaging (currently
  in `LoginScreen`) moves into the sign-in card so nothing regresses.
- **Logged-in visitors:** navigate the app normally. `/about` is reachable via a new
  **navbar "About" link** and by direct URL. On the landing page, the primary CTA reads
  **"Go to dashboard"** (→ `/`) instead of sign-in.

`LoginScreen.jsx` becomes orphaned once the landing page absorbs its OAuth buttons +
beta-closed state. It will be flagged for removal but **not deleted** without explicit
approval (per project guardrails); the orphan note goes in `react-dashboard/CONTEXT.md`.

### App.jsx wiring

- When `me === undefined` (loading): unchanged (`return null`).
- When `me === null` (logged out): render the landing page for every path. Simplest
  correct approach: render `<LandingPage me={null} betaClosed={betaClosed} />` directly
  (as the current code renders `<LoginScreen>`), so any URL shows it. If the address bar
  should read `/about`, add a `<Navigate to="/about" replace>` guard so the URL
  normalizes; the page content is identical regardless. **Decision:** normalize the URL to
  `/about` via redirect for logged-out visitors (matches "all routes forward to /about").
- When `me` is set (logged in): add `<Route path="/about" element={<LandingPage me={me} />} />`
  alongside the existing `/docs` and `/admin` routes.

## Content Sections

Authored copy (draftable/revisable later). Order top→bottom:

1. **Hero** — product name/logo, headline, one-line value prop, primary CTA
   (sign-in card scroll-to for logged-out / "Go to dashboard" for logged-in), gradient
   backdrop.
2. **How it works (3 steps)** — Scrape jobs → Tailor résumé & cover letter → Apply.
   Numbered/iconed 3-step flow.
3. **Feature highlights** — 3–4 benefit cards: AI tailoring, ATS-safe formatting,
   job scoring / skill matching, live PDF preview.
4. **Sign-in card / CTA footer** — OAuth buttons (Google/GitHub) + beta-closed state for
   logged-out; "Go to dashboard" for logged-in.

Pricing section intentionally omitted.

## Component Structure

New directory `react-dashboard/src/components/landing/`:

- `LandingPage.jsx` — page shell; props `{ me, betaClosed }`. Composes the sections and
  owns a ref/anchor so the hero CTA can scroll to `SignInCard`. Derives `isAuthed = !!me`.
- `Hero.jsx` — headline, value prop, primary CTA, gradient. Props: `{ isAuthed, onCtaClick }`.
- `HowItWorks.jsx` — static 3-step flow.
- `Features.jsx` — static benefit cards (array of `{ title, blurb, icon }`).
- `SignInCard.jsx` — OAuth buttons + `betaClosed` messaging (logged-out) OR
  "Go to dashboard" link (logged-in). Absorbs current `LoginScreen` behavior.

Each unit is presentational, independently renderable, and has no external dependencies
beyond `react-router-dom` `Link`/`Navigate` and existing Tailwind tokens. Rationale for
splitting: the "elevated" look means each section carries non-trivial markup/animation;
isolating them keeps each file focused and testable.

## Aesthetic

Existing dark palette + purple accents, elevated to marketing grade:

- Larger hero gradient, generous whitespace, clear vertical rhythm.
- Subtle Framer Motion entrance/scroll animations reusing the app's existing motion
  vocabulary (`initial/animate/whileHover`, easing already used in `Pipeline.jsx`).
- Reuses existing `space-bg` / `space-border` / `space-text` / `space-dim` Tailwind
  tokens and purple accent classes. No new design system.

## Testing

Vitest render tests (matching existing FE test conventions):

- `LandingPage` renders all four sections (hero, how-it-works, features, sign-in card).
- Logged-out: sign-in card shows OAuth links pointing to `/auth/login/google` and
  `/auth/login/github`; beta-closed prop renders the closed-beta message.
- Logged-in: primary CTA / card renders "Go to dashboard" linking to `/`, and OAuth
  buttons are absent.
- App-level: logged-out state redirects an arbitrary route to `/about` (or renders the
  landing page), and the navbar renders an "About" link when logged in.

## Files Touched

- **New:** `react-dashboard/src/components/landing/{LandingPage,Hero,HowItWorks,Features,SignInCard}.jsx`
- **New:** landing render test(s) under the existing FE test location.
- **Edit:** `react-dashboard/src/App.jsx` — logged-out → landing (redirect to `/about`);
  add `/about` route for logged-in users.
- **Edit:** `react-dashboard/src/components/Navbar.jsx` — add "About" link.
- **Edit:** `react-dashboard/CONTEXT.md` — note `LoginScreen.jsx` orphaned, landing page
  routing.
- **Orphaned (not deleted):** `react-dashboard/src/components/LoginScreen.jsx`.

## Risks / Notes

- The redirect-to-`/about` for logged-out users must not break the OAuth round-trip:
  `/auth/login/*` are full-page navigations to the backend (not React routes), so the
  SPA redirect never intercepts them. Confirm the OAuth callback lands the user back at
  `/` authenticated (existing behavior, unchanged).
- Keep the page lightweight — no heavy assets — so first paint for a cold visitor is fast.
