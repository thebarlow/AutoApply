# Landing / About Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a public "About" marketing page that pitches AutoApply (scrape → tailor → apply), shown to logged-out visitors and reachable at `/about` for everyone.

**Architecture:** Pure frontend. A new `landing/` component tree (page shell + 4 presentational sections) renders on the existing dark/purple theme with subtle Framer Motion. `App.jsx` redirects logged-out visitors to `/about` and adds an `/about` route for logged-in users; `Navbar` gets an "About" link. No backend/API changes.

**Tech Stack:** React 18, react-router-dom v7, Framer Motion v11, Tailwind (custom `space.*` tokens), Vitest + @testing-library/react + jsdom.

## Global Constraints

- No backend changes, no new API endpoints, no data fetching on the landing page.
- No pricing / credit-pack section.
- Reuse existing Tailwind tokens only: `space-bg` `#0a0a1a`, `space-card` `#0f0f2a`, `space-border` `#2d1b69`, `space-accent` `#6d28d9`, `space-text` `#e2e8f0`, `space-dim` `#94a3b8`, plus existing `purple-*` classes. No new theme entries.
- OAuth links are full-page backend navigations: `/auth/login/google`, `/auth/login/github`. Never wrap them in a React `<Link>`; use plain `<a href>`.
- Router-dependent components must be rendered inside a router in tests (`MemoryRouter`).
- Follow existing FE test conventions: `import { describe, it, expect } from 'vitest'`, `render`/`screen` from `@testing-library/react`. jest-dom matchers are globally set up (see `vitest.config.js`).
- All new component files live under `react-dashboard/src/components/landing/`; tests co-locate as `*.test.jsx` next to the component (matches repo convention).
- Run FE tests from the `react-dashboard/` directory: `npm run test`.
- Commit format: `[type] Imperative subject` (types: feat, fix, refactor, docs, test, chore).

---

### Task 1: `SignInCard` — OAuth / dashboard CTA (absorbs LoginScreen)

**Files:**
- Create: `react-dashboard/src/components/landing/SignInCard.jsx`
- Test: `react-dashboard/src/components/landing/SignInCard.test.jsx`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `export default function SignInCard({ isAuthed, betaClosed })`. Renders, when
  `isAuthed` is falsy: an `<a href="/auth/login/google">` and `<a href="/auth/login/github">`,
  each wrapping a button; if `betaClosed` is truthy, also a closed-beta message containing the
  text "closed beta". When `isAuthed` is truthy: a single `<a href="/">` button labeled
  "Go to dashboard" and NO OAuth links. The card root has `id="signin"` (hero CTA scroll target).

- [ ] **Step 1: Write the failing test**

```jsx
// react-dashboard/src/components/landing/SignInCard.test.jsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import SignInCard from './SignInCard'

describe('SignInCard', () => {
  it('logged out: shows Google + GitHub OAuth links', () => {
    render(<SignInCard isAuthed={false} />)
    expect(screen.getByRole('link', { name: /google/i }).getAttribute('href')).toBe('/auth/login/google')
    expect(screen.getByRole('link', { name: /github/i }).getAttribute('href')).toBe('/auth/login/github')
  })

  it('logged out + betaClosed: shows the closed-beta message', () => {
    render(<SignInCard isAuthed={false} betaClosed />)
    expect(screen.getByText(/closed beta/i)).toBeTruthy()
  })

  it('logged out without betaClosed: no closed-beta message', () => {
    render(<SignInCard isAuthed={false} />)
    expect(screen.queryByText(/closed beta/i)).toBeNull()
  })

  it('logged in: shows Go to dashboard and no OAuth links', () => {
    render(<SignInCard isAuthed />)
    const cta = screen.getByRole('link', { name: /go to dashboard/i })
    expect(cta.getAttribute('href')).toBe('/')
    expect(screen.queryByRole('link', { name: /google/i })).toBeNull()
    expect(screen.queryByRole('link', { name: /github/i })).toBeNull()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `react-dashboard/`): `npm run test -- SignInCard`
Expected: FAIL — cannot resolve `./SignInCard`.

- [ ] **Step 3: Write minimal implementation**

```jsx
// react-dashboard/src/components/landing/SignInCard.jsx
const oauthBtn =
  'w-full py-2.5 rounded-lg border border-space-border bg-[#1a1a2e] hover:bg-[#23233a] text-space-text font-medium transition-colors'

export default function SignInCard({ isAuthed, betaClosed }) {
  return (
    <section id="signin" className="w-full max-w-sm mx-auto text-center">
      {isAuthed ? (
        <a href="/">
          <button className="w-full py-2.5 rounded-lg bg-space-accent hover:bg-purple-500 text-white font-semibold transition-colors">
            Go to dashboard
          </button>
        </a>
      ) : (
        <>
          {betaClosed ? (
            <p className="text-red-400 text-sm mb-6">
              This is a closed beta. Your account isn't on the invite list yet —
              request access and check back soon.
            </p>
          ) : (
            <p className="text-space-dim text-sm mb-6">Sign in to get started.</p>
          )}
          <div className="flex flex-col gap-3">
            <a href="/auth/login/google">
              <button className={oauthBtn}>Sign in with Google</button>
            </a>
            <a href="/auth/login/github">
              <button className={oauthBtn}>Sign in with GitHub</button>
            </a>
          </div>
        </>
      )}
    </section>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `react-dashboard/`): `npm run test -- SignInCard`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/landing/SignInCard.jsx react-dashboard/src/components/landing/SignInCard.test.jsx
git commit -m "[feat] Add landing SignInCard (OAuth / dashboard CTA)"
```

---

### Task 2: `Hero`, `HowItWorks`, `Features` — static marketing sections

**Files:**
- Create: `react-dashboard/src/components/landing/Hero.jsx`
- Create: `react-dashboard/src/components/landing/HowItWorks.jsx`
- Create: `react-dashboard/src/components/landing/Features.jsx`
- Test: `react-dashboard/src/components/landing/sections.test.jsx`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `export default function Hero({ isAuthed, onCtaClick })` — renders an `<h1>` with the
    product headline, a value-prop paragraph, and a primary CTA `<button>` whose label is
    "Get started" when `!isAuthed` and "Go to dashboard" when `isAuthed`; clicking it calls
    `onCtaClick`.
  - `export default function HowItWorks()` — renders a heading containing "How it works" and
    exactly three steps whose visible text includes "Scrape", "Tailor", and "Apply".
  - `export default function Features()` — renders four feature cards. Card titles: "AI-tailored
    documents", "ATS-safe formatting", "Job scoring & skill matching", "Live PDF preview".

- [ ] **Step 1: Write the failing test**

```jsx
// react-dashboard/src/components/landing/sections.test.jsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import Hero from './Hero'
import HowItWorks from './HowItWorks'
import Features from './Features'

describe('Hero', () => {
  it('logged out: CTA reads Get started and fires onCtaClick', () => {
    const onCtaClick = vi.fn()
    render(<Hero isAuthed={false} onCtaClick={onCtaClick} />)
    const btn = screen.getByRole('button', { name: /get started/i })
    btn.click()
    expect(onCtaClick).toHaveBeenCalledTimes(1)
  })

  it('logged in: CTA reads Go to dashboard', () => {
    render(<Hero isAuthed onCtaClick={() => {}} />)
    expect(screen.getByRole('button', { name: /go to dashboard/i })).toBeTruthy()
  })
})

describe('HowItWorks', () => {
  it('renders the three pipeline steps', () => {
    render(<HowItWorks />)
    expect(screen.getByText(/how it works/i)).toBeTruthy()
    expect(screen.getByText(/scrape/i)).toBeTruthy()
    expect(screen.getByText(/tailor/i)).toBeTruthy()
    expect(screen.getByText(/apply/i)).toBeTruthy()
  })
})

describe('Features', () => {
  it('renders four feature cards', () => {
    render(<Features />)
    expect(screen.getByText(/AI-tailored documents/i)).toBeTruthy()
    expect(screen.getByText(/ATS-safe formatting/i)).toBeTruthy()
    expect(screen.getByText(/Job scoring & skill matching/i)).toBeTruthy()
    expect(screen.getByText(/Live PDF preview/i)).toBeTruthy()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `react-dashboard/`): `npm run test -- sections`
Expected: FAIL — cannot resolve `./Hero`.

- [ ] **Step 3: Write minimal implementation**

```jsx
// react-dashboard/src/components/landing/Hero.jsx
import { motion } from 'framer-motion'

export default function Hero({ isAuthed, onCtaClick }) {
  return (
    <section className="relative overflow-hidden px-6 pt-28 pb-24 text-center">
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top,rgba(109,40,217,0.35),transparent_60%)]" />
      <motion.h1
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        className="mx-auto max-w-3xl text-4xl sm:text-5xl font-bold tracking-tight text-white"
      >
        Land more interviews. Apply in a fraction of the time.
      </motion.h1>
      <motion.p
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1, ease: 'easeOut' }}
        className="mx-auto mt-6 max-w-xl text-lg text-space-dim"
      >
        AutoApply scrapes jobs, tailors your résumé and cover letter to each one, and
        gets you ready to apply — all from one dashboard.
      </motion.p>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.2, ease: 'easeOut' }}
        className="mt-10"
      >
        <button
          onClick={onCtaClick}
          className="px-8 py-3 rounded-lg bg-space-accent hover:bg-purple-500 text-white text-base font-semibold transition-colors shadow-lg shadow-purple-900/40"
        >
          {isAuthed ? 'Go to dashboard' : 'Get started'}
        </button>
      </motion.div>
    </section>
  )
}
```

```jsx
// react-dashboard/src/components/landing/HowItWorks.jsx
import { motion } from 'framer-motion'

const STEPS = [
  { n: '1', title: 'Scrape', body: 'Pull job postings from the boards you care about into one inbox.' },
  { n: '2', title: 'Tailor', body: 'Generate a résumé and cover letter tuned to each posting.' },
  { n: '3', title: 'Apply', body: 'Review, refine, and submit — ATS-safe and ready to send.' },
]

export default function HowItWorks() {
  return (
    <section className="px-6 py-20 max-w-5xl mx-auto">
      <h2 className="text-center text-3xl font-bold text-white mb-14">How it works</h2>
      <div className="grid gap-8 sm:grid-cols-3">
        {STEPS.map((s, i) => (
          <motion.div
            key={s.n}
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.4 }}
            transition={{ duration: 0.5, delay: i * 0.1, ease: 'easeOut' }}
            className="text-center"
          >
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-space-accent/20 text-space-accent text-xl font-bold">
              {s.n}
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">{s.title}</h3>
            <p className="text-sm text-space-dim">{s.body}</p>
          </motion.div>
        ))}
      </div>
    </section>
  )
}
```

```jsx
// react-dashboard/src/components/landing/Features.jsx
import { motion } from 'framer-motion'

const FEATURES = [
  { title: 'AI-tailored documents', body: 'Every résumé and cover letter is rewritten to match the specific role.' },
  { title: 'ATS-safe formatting', body: 'Clean, parseable output that applicant-tracking systems can read.' },
  { title: 'Job scoring & skill matching', body: 'See how well each posting fits before you spend time on it.' },
  { title: 'Live PDF preview', body: 'Edit and watch the real PDF update side-by-side, instantly.' },
]

export default function Features() {
  return (
    <section className="px-6 py-20 max-w-5xl mx-auto">
      <div className="grid gap-6 sm:grid-cols-2">
        {FEATURES.map((f, i) => (
          <motion.div
            key={f.title}
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.5, delay: i * 0.08, ease: 'easeOut' }}
            className="rounded-xl border border-space-border bg-space-card/60 p-6"
          >
            <h3 className="text-lg font-semibold text-white mb-2">{f.title}</h3>
            <p className="text-sm text-space-dim">{f.body}</p>
          </motion.div>
        ))}
      </div>
    </section>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `react-dashboard/`): `npm run test -- sections`
Expected: PASS (4 tests). Note: `whileInView` triggers immediately in jsdom (no viewport), so content renders.

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/landing/Hero.jsx react-dashboard/src/components/landing/HowItWorks.jsx react-dashboard/src/components/landing/Features.jsx react-dashboard/src/components/landing/sections.test.jsx
git commit -m "[feat] Add landing hero, how-it-works, and features sections"
```

---

### Task 3: `LandingPage` — page shell composing the sections

**Files:**
- Create: `react-dashboard/src/components/landing/LandingPage.jsx`
- Test: `react-dashboard/src/components/landing/LandingPage.test.jsx`

**Interfaces:**
- Consumes: `SignInCard` (Task 1), `Hero`, `HowItWorks`, `Features` (Task 2).
- Produces: `export default function LandingPage({ me, betaClosed })`. Derives
  `isAuthed = !!me`. Renders Hero → HowItWorks → Features → SignInCard in a scrollable
  page. The hero CTA, when `!isAuthed`, scrolls to `#signin`
  (`document.getElementById('signin')?.scrollIntoView`); when `isAuthed`, navigates to `/`.

- [ ] **Step 1: Write the failing test**

```jsx
// react-dashboard/src/components/landing/LandingPage.test.jsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import LandingPage from './LandingPage'

describe('LandingPage', () => {
  it('logged out: renders all sections and OAuth sign-in', () => {
    render(<LandingPage me={null} />)
    expect(screen.getByRole('heading', { name: /how it works/i })).toBeTruthy()
    expect(screen.getByText(/AI-tailored documents/i)).toBeTruthy()
    expect(screen.getByRole('link', { name: /google/i })).toBeTruthy()
  })

  it('logged out: hero CTA scrolls to the sign-in card', () => {
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView
    render(<LandingPage me={null} />)
    screen.getByRole('button', { name: /get started/i }).click()
    expect(scrollIntoView).toHaveBeenCalled()
  })

  it('logged in: shows Go to dashboard, no OAuth links', () => {
    render(<LandingPage me={{ email: 'a@b.c' }} />)
    // both hero CTA and sign-in card link say "go to dashboard"
    expect(screen.getAllByRole('link', { name: /go to dashboard/i }).length).toBeGreaterThan(0)
    expect(screen.queryByRole('link', { name: /google/i })).toBeNull()
  })

  it('passes betaClosed through to the sign-in card', () => {
    render(<LandingPage me={null} betaClosed />)
    expect(screen.getByText(/closed beta/i)).toBeTruthy()
  })
})
```

Note: the logged-in hero CTA is a `<button>` that navigates via `window.location`, but the
sign-in card renders a `go to dashboard` `<a>`; the test uses `getAllByRole('link', …)` for the
card link. Ensure the hero CTA in logged-in mode navigates to `/` (see implementation).

- [ ] **Step 2: Run test to verify it fails**

Run (from `react-dashboard/`): `npm run test -- LandingPage`
Expected: FAIL — cannot resolve `./LandingPage`.

- [ ] **Step 3: Write minimal implementation**

```jsx
// react-dashboard/src/components/landing/LandingPage.jsx
import Hero from './Hero'
import HowItWorks from './HowItWorks'
import Features from './Features'
import SignInCard from './SignInCard'

export default function LandingPage({ me, betaClosed }) {
  const isAuthed = !!me

  const handleCta = () => {
    if (isAuthed) {
      window.location.href = '/'
    } else {
      document.getElementById('signin')?.scrollIntoView({ behavior: 'smooth' })
    }
  }

  return (
    <div className="min-h-screen bg-space-bg text-space-text">
      <Hero isAuthed={isAuthed} onCtaClick={handleCta} />
      <HowItWorks />
      <Features />
      <div className="px-6 pb-28 pt-8">
        <SignInCard isAuthed={isAuthed} betaClosed={betaClosed} />
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `react-dashboard/`): `npm run test -- LandingPage`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add react-dashboard/src/components/landing/LandingPage.jsx react-dashboard/src/components/landing/LandingPage.test.jsx
git commit -m "[feat] Add LandingPage shell composing marketing sections"
```

---

### Task 4: Wire routing in `App.jsx` + navbar link + docs

**Files:**
- Modify: `react-dashboard/src/App.jsx` (imports; logged-out branch ~L200-205; authed `<Routes>` ~L208-211)
- Modify: `react-dashboard/src/components/Navbar.jsx` (nav links block ~L59-77)
- Modify: `react-dashboard/CONTEXT.md` (note landing routing + orphaned LoginScreen)
- Test: `react-dashboard/src/App.landing.test.jsx`

**Interfaces:**
- Consumes: `LandingPage` (Task 3).
- Produces: no exported symbols. Behavior: logged-out (`me === null`) renders `LandingPage`
  and the browser URL is normalized to `/about`; logged-in adds a `/about` route rendering
  `LandingPage`; the navbar shows an "About" `<Link to="/about">`.

- [ ] **Step 1: Write the failing test**

```jsx
// react-dashboard/src/App.landing.test.jsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'

describe('Navbar About link', () => {
  it('renders an About link to /about', () => {
    render(
      <MemoryRouter>
        <Navbar me={{ email: 'a@b.c' }} />
      </MemoryRouter>
    )
    const link = screen.getByRole('link', { name: /^about$/i })
    expect(link.getAttribute('href')).toBe('/about')
  })
})
```

(App.jsx itself pulls in SSE/`getMe` side effects that are heavy to mount in jsdom; this task
verifies the navbar link directly. Logged-out redirect behavior is covered by manual QA in
Step 6 — the routing change is small and the redirect is a single `<Navigate>`.)

- [ ] **Step 2: Run test to verify it fails**

Run (from `react-dashboard/`): `npm run test -- App.landing`
Expected: FAIL — no link named "About".

- [ ] **Step 3: Add the navbar About link**

In `react-dashboard/src/components/Navbar.jsx`, inside the right-side `<div className="flex items-center gap-4">` (before the Help link), add:

```jsx
        {/* About / marketing page */}
        <Link
          to="/about"
          className="text-sm text-space-dim hover:text-purple-400 transition-colors"
        >
          About
        </Link>
```

(`Link` is already imported at the top of Navbar.jsx.)

- [ ] **Step 4: Run test to verify it passes**

Run (from `react-dashboard/`): `npm run test -- App.landing`
Expected: PASS (1 test).

- [ ] **Step 5: Wire App.jsx routing**

In `react-dashboard/src/App.jsx`:

5a. Update the router import (currently `import { Routes, Route } from 'react-router-dom'`):

```jsx
import { Routes, Route, Navigate } from 'react-router-dom'
```

5b. Add the landing import near the other component imports (e.g. after the `LoginScreen` import line):

```jsx
import LandingPage from './components/landing/LandingPage'
```

5c. Replace the logged-out branch. Current:

```jsx
  if (me === null) {
    const betaClosed = new URLSearchParams(window.location.search).get('beta') === 'closed'
    return <LoginScreen betaClosed={betaClosed} />
  }
```

with (render the landing page for every route, normalizing the URL to `/about`):

```jsx
  if (me === null) {
    const betaClosed = new URLSearchParams(window.location.search).get('beta') === 'closed'
    return (
      <Routes>
        <Route path="/about" element={<LandingPage me={null} betaClosed={betaClosed} />} />
        <Route path="*" element={<Navigate to="/about" replace />} />
      </Routes>
    )
  }
```

5d. Add an `/about` route in the authed `<Routes>` block, alongside `/docs` and `/admin`:

```jsx
      <Route path="/about" element={<LandingPage me={me} />} />
```

- [ ] **Step 6: Manual verification (routing)**

Build to confirm no import/JSX errors:

Run (from `react-dashboard/`): `npm run build`
Expected: build succeeds.

Then (optional but recommended) run the dev server (`npm run dev` from `react-dashboard/`, backend via `start.bat dev`) and confirm:
- Logged out, visiting any path (e.g. `/foo`) redirects the address bar to `/about` and shows the hero.
- The "Get started" button scrolls down to the Google/GitHub buttons.
- `?beta=closed` on `/about` shows the closed-beta message.
- Logged in, the navbar "About" link opens `/about` with a "Go to dashboard" CTA and no OAuth buttons.

- [ ] **Step 7: Update CONTEXT.md**

In `react-dashboard/CONTEXT.md`, add a short note under the routing/components section:

```markdown
- **Landing / About page** (`src/components/landing/`): public marketing page shown to
  logged-out visitors (all routes redirect to `/about`) and reachable at `/about` for
  logged-in users via the navbar "About" link. Pure frontend, no API calls.
  `src/components/LoginScreen.jsx` is now **orphaned** — its OAuth buttons + beta-closed
  message were absorbed into `landing/SignInCard.jsx`. Safe to delete once confirmed.
```

- [ ] **Step 8: Run the full FE test suite + commit**

Run (from `react-dashboard/`): `npm run test`
Expected: all tests pass (existing + the new landing tests).

```bash
git add react-dashboard/src/App.jsx react-dashboard/src/components/Navbar.jsx react-dashboard/src/App.landing.test.jsx react-dashboard/CONTEXT.md
git commit -m "[feat] Route logged-out visitors to /about landing page + navbar link"
```

---

## Post-implementation

- `LoginScreen.jsx` is now orphaned. Do **not** delete without explicit user approval
  (project guardrail). Leave the CONTEXT.md note; deletion is a follow-up.
- Update `TODO.md`: mark "Make landing page" done; also mark the stale "hosted
  job-ingestion gap" and "auto-score jobs after upload" items as already-implemented
  (verified during this work) — but confirm with the user first.

## Self-Review Notes

- **Spec coverage:** routing/redirect (Task 4), `/about` name (Tasks 3/4), navbar link
  (Task 4), Hero+CTA / HowItWorks / Features (Task 2), sign-in card + beta-closed (Task 1),
  logged-in "Go to dashboard" (Tasks 1–3), elevated dark/purple aesthetic (Tasks 2–3),
  no backend/pricing (constraints), tests (each task) — all covered.
- **Placeholders:** none; every code step is complete.
- **Type consistency:** `LandingPage({ me, betaClosed })`, `SignInCard({ isAuthed, betaClosed })`,
  `Hero({ isAuthed, onCtaClick })` used consistently across tasks; `#signin` scroll target
  defined in Task 1 and consumed in Task 3.
