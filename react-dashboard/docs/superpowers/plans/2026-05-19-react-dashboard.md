# React Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a display-only, space-themed React dashboard with 5 widgets across a two-column layout, mocked data, and Framer Motion animations.

**Architecture:** Vite + React SPA with Tailwind CSS for styling. A shared `Widget` wrapper card provides consistent card styling. All data lives in `src/mockData.js` shaped to mirror the eventual FastAPI response format. Framer Motion handles staggered entrance animations and hover effects.

**Tech Stack:** Vite, React 18, Tailwind CSS v3, Framer Motion, PostCSS

---

## File Map

| File | Responsibility |
|---|---|
| `index.html` | Vite entry HTML |
| `vite.config.js` | Vite config |
| `tailwind.config.js` | Tailwind theme (custom colors, font) |
| `postcss.config.js` | PostCSS plugins (Tailwind, autoprefixer) |
| `src/main.jsx` | React root mount |
| `src/App.jsx` | Root component — renders Navbar + Dashboard |
| `src/index.css` | Global styles: grain texture, base dark background |
| `src/mockData.js` | All mocked data for every widget |
| `src/components/Navbar.jsx` | Sticky top bar |
| `src/components/Dashboard.jsx` | Two-column grid layout |
| `src/components/shared/Widget.jsx` | Shared card wrapper with Framer Motion entrance |
| `src/components/shared/JobCard.jsx` | Reusable job card for Inbox/Processing/Outbox |
| `src/components/widgets/Inbox.jsx` | Inbox widget |
| `src/components/widgets/Processing.jsx` | Processing widget |
| `src/components/widgets/Outbox.jsx` | Outbox widget |
| `src/components/widgets/Stats.jsx` | Stats widget |
| `src/components/widgets/Settings.jsx` | Settings widget |

---

### Task 1: Scaffold Vite + React project

**Files:**
- Create: `package.json`
- Create: `vite.config.js`
- Create: `index.html`
- Create: `src/main.jsx`
- Create: `src/App.jsx`

- [ ] **Step 1: Scaffold with Vite**

Run from `react-dashboard/`:
```bash
npm create vite@latest . -- --template react
```
When prompted "Current directory is not empty. Remove existing files and continue?" — select **Yes**.

- [ ] **Step 2: Install dependencies**

```bash
npm install
npm install framer-motion
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

- [ ] **Step 3: Verify dev server starts**

```bash
npm run dev
```
Expected: Vite server running at `http://localhost:5173`. Default React page visible in browser.

- [ ] **Step 4: Commit**

```bash
git add .
git commit -m "[chore] Scaffold Vite + React project with Tailwind and Framer Motion"
```

---

### Task 2: Configure Tailwind with custom space theme

**Files:**
- Modify: `tailwind.config.js`
- Modify: `src/index.css`

- [ ] **Step 1: Update tailwind.config.js**

Replace the entire file with:
```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        space: {
          bg: '#0a0a1a',
          card: '#0f0f2a',
          border: '#2d1b69',
          accent: '#6d28d9',
          blue: '#1d4ed8',
          muted: '#6b7280',
          text: '#e2e8f0',
          dim: '#94a3b8',
        },
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 2: Set up global styles with grain texture in src/index.css**

Replace the entire file with:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  background-color: #0a0a1a;
  color: #e2e8f0;
  min-height: 100vh;
  position: relative;
}

body::before {
  content: '';
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  opacity: 0.18;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
  background-repeat: repeat;
  background-size: 200px 200px;
}

#root {
  position: relative;
  z-index: 1;
}
```

- [ ] **Step 3: Update src/App.jsx to verify Tailwind is working**

```jsx
export default function App() {
  return (
    <div className="min-h-screen text-space-text">
      <p className="p-8 text-purple-400">Tailwind working</p>
    </div>
  )
}
```

- [ ] **Step 4: Check browser**

Run `npm run dev` if not already running. Verify: dark background, purple text, grain texture visible over it.

- [ ] **Step 5: Commit**

```bash
git add tailwind.config.js src/index.css src/App.jsx
git commit -m "[feat] Configure Tailwind space theme and grain background texture"
```

---

### Task 3: Add mock data

**Files:**
- Create: `src/mockData.js`

- [ ] **Step 1: Create src/mockData.js**

```js
export const inboxJobs = [
  { id: 1, title: 'Frontend Engineer', company: 'Stripe', dateAdded: '2026-05-18' },
  { id: 2, title: 'React Developer', company: 'Vercel', dateAdded: '2026-05-17' },
  { id: 3, title: 'UI Engineer', company: 'Linear', dateAdded: '2026-05-17' },
  { id: 4, title: 'Software Engineer', company: 'Notion', dateAdded: '2026-05-16' },
  { id: 5, title: 'Product Engineer', company: 'Loom', dateAdded: '2026-05-15' },
]

export const processingJobs = [
  { id: 6, title: 'Full Stack Developer', company: 'Retool', stage: 'Scoring' },
  { id: 7, title: 'TypeScript Engineer', company: 'Prisma', stage: 'Generating' },
  { id: 8, title: 'Staff Engineer', company: 'PlanetScale', stage: 'Scoring' },
]

export const outboxJobs = [
  { id: 9, title: 'Backend Engineer', company: 'Supabase', outcome: 'Applied' },
  { id: 10, title: 'DevOps Engineer', company: 'Railway', outcome: 'Skipped' },
  { id: 11, title: 'Python Developer', company: 'Prefect', outcome: 'Applied' },
]

export const stats = {
  totalJobs: 47,
  applied: 11,
  successRate: '23%',
  creditsUsed: '$2.84',
}

export const settings = {
  resumePath: '~/auto_apply/resumes/matthew_barlow.pdf',
  targetRoles: 'Frontend Engineer, React Developer, UI Engineer',
  locationPreference: 'Remote',
  modelInUse: 'claude-sonnet-4-6',
}
```

- [ ] **Step 2: Commit**

```bash
git add src/mockData.js
git commit -m "[feat] Add mock data for all dashboard widgets"
```

---

### Task 4: Build shared Widget card wrapper

**Files:**
- Create: `src/components/shared/Widget.jsx`

- [ ] **Step 1: Create src/components/shared/Widget.jsx**

```jsx
import { motion } from 'framer-motion'

export default function Widget({ title, children, className = '' }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      whileHover={{ boxShadow: '0 0 24px 2px rgba(109,40,217,0.15)' }}
      className={`
        bg-white/5 border border-space-border rounded-xl p-4 flex flex-col gap-3
        ${className}
      `}
    >
      <h2 className="text-xs font-semibold uppercase tracking-widest text-space-dim">
        {title}
      </h2>
      <div className="flex-1">{children}</div>
    </motion.div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add src/components/shared/Widget.jsx
git commit -m "[feat] Add shared Widget card wrapper with Framer Motion"
```

---

### Task 5: Build shared JobCard component

**Files:**
- Create: `src/components/shared/JobCard.jsx`

- [ ] **Step 1: Create src/components/shared/JobCard.jsx**

```jsx
import { motion } from 'framer-motion'

export default function JobCard({ title, company, meta, metaColor = 'text-space-dim' }) {
  return (
    <motion.div
      whileHover={{ scale: 1.01, backgroundColor: 'rgba(255,255,255,0.06)' }}
      transition={{ duration: 0.15 }}
      className="flex items-center justify-between rounded-lg px-3 py-2 bg-white/[0.03] border border-white/5"
    >
      <div>
        <p className="text-sm font-medium text-space-text">{title}</p>
        <p className="text-xs text-space-dim">{company}</p>
      </div>
      <span className={`text-xs font-medium ${metaColor}`}>{meta}</span>
    </motion.div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add src/components/shared/JobCard.jsx
git commit -m "[feat] Add shared JobCard component"
```

---

### Task 6: Build Navbar

**Files:**
- Create: `src/components/Navbar.jsx`

- [ ] **Step 1: Create src/components/Navbar.jsx**

```jsx
export default function Navbar() {
  return (
    <nav className="sticky top-0 z-50 w-full backdrop-blur-md bg-space-bg/80 border-b border-space-border px-6 py-3 flex items-center justify-between">
      <span className="text-lg font-bold tracking-tight text-white">
        Auto Apply
      </span>
      <span className="text-sm font-medium text-purple-400">
        Credits: $0.00
      </span>
    </nav>
  )
}
```

- [ ] **Step 2: Wire Navbar into App.jsx**

```jsx
import Navbar from './components/Navbar'

export default function App() {
  return (
    <div className="min-h-screen text-space-text">
      <Navbar />
    </div>
  )
}
```

- [ ] **Step 3: Check browser**

Verify: navbar is visible at top, sticky when scrolling, "Auto Apply" on left, "Credits: $0.00" in purple on right.

- [ ] **Step 4: Commit**

```bash
git add src/components/Navbar.jsx src/App.jsx
git commit -m "[feat] Add sticky Navbar"
```

---

### Task 7: Build Dashboard layout

**Files:**
- Create: `src/components/Dashboard.jsx`
- Modify: `src/App.jsx`

- [ ] **Step 1: Create src/components/Dashboard.jsx**

```jsx
import { motion } from 'framer-motion'

const containerVariants = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.1,
    },
  },
}

export default function Dashboard({ children }) {
  return (
    <motion.main
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="grid grid-cols-5 gap-4 p-6 h-[calc(100vh-53px)]"
    >
      {children}
    </motion.main>
  )
}
```

- [ ] **Step 2: Update src/App.jsx to include Dashboard with column placeholders**

```jsx
import Navbar from './components/Navbar'
import Dashboard from './components/Dashboard'

export default function App() {
  return (
    <div className="min-h-screen text-space-text">
      <Navbar />
      <Dashboard>
        {/* Left column: 3/5 = 60% */}
        <div className="col-span-3 flex flex-col gap-4">
          <div className="bg-purple-900/20 rounded-xl flex-1 flex items-center justify-center text-space-dim">Inbox</div>
          <div className="bg-purple-900/20 rounded-xl flex-1 flex items-center justify-center text-space-dim">Processing</div>
          <div className="bg-purple-900/20 rounded-xl flex-1 flex items-center justify-center text-space-dim">Outbox</div>
        </div>
        {/* Right column: 2/5 = 40% */}
        <div className="col-span-2 flex flex-col gap-4">
          <div className="bg-blue-900/20 rounded-xl flex-1 flex items-center justify-center text-space-dim">Stats</div>
          <div className="bg-blue-900/20 rounded-xl flex-1 flex items-center justify-center text-space-dim">Settings</div>
        </div>
      </Dashboard>
    </div>
  )
}
```

- [ ] **Step 3: Check browser**

Verify: two-column layout visible, left column has 3 placeholders, right has 2. Layout fills the viewport below the navbar.

- [ ] **Step 4: Commit**

```bash
git add src/components/Dashboard.jsx src/App.jsx
git commit -m "[feat] Add two-column Dashboard layout"
```

---

### Task 8: Build Inbox widget

**Files:**
- Create: `src/components/widgets/Inbox.jsx`

- [ ] **Step 1: Create src/components/widgets/Inbox.jsx**

```jsx
import Widget from '../shared/Widget'
import JobCard from '../shared/JobCard'
import { inboxJobs } from '../../mockData'

export default function Inbox() {
  return (
    <Widget title="Inbox" className="flex-[2]">
      <div className="flex flex-col gap-2">
        {inboxJobs.map((job) => (
          <JobCard
            key={job.id}
            title={job.title}
            company={job.company}
            meta={job.dateAdded}
            metaColor="text-space-dim"
          />
        ))}
      </div>
    </Widget>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add src/components/widgets/Inbox.jsx
git commit -m "[feat] Add Inbox widget"
```

---

### Task 9: Build Processing widget

**Files:**
- Create: `src/components/widgets/Processing.jsx`

- [ ] **Step 1: Create src/components/widgets/Processing.jsx**

```jsx
import Widget from '../shared/Widget'
import JobCard from '../shared/JobCard'
import { processingJobs } from '../../mockData'

const stageColor = (stage) =>
  stage === 'Scoring' ? 'text-yellow-400' : 'text-blue-400'

export default function Processing() {
  return (
    <Widget title="Processing" className="flex-[1.5]">
      <div className="flex flex-col gap-2">
        {processingJobs.map((job) => (
          <JobCard
            key={job.id}
            title={job.title}
            company={job.company}
            meta={job.stage}
            metaColor={stageColor(job.stage)}
          />
        ))}
      </div>
    </Widget>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add src/components/widgets/Processing.jsx
git commit -m "[feat] Add Processing widget"
```

---

### Task 10: Build Outbox widget

**Files:**
- Create: `src/components/widgets/Outbox.jsx`

- [ ] **Step 1: Create src/components/widgets/Outbox.jsx**

```jsx
import Widget from '../shared/Widget'
import JobCard from '../shared/JobCard'
import { outboxJobs } from '../../mockData'

const outcomeColor = (outcome) =>
  outcome === 'Applied' ? 'text-green-400' : 'text-space-muted'

export default function Outbox() {
  return (
    <Widget title="Outbox" className="flex-[1.5]">
      <div className="flex flex-col gap-2">
        {outboxJobs.map((job) => (
          <JobCard
            key={job.id}
            title={job.title}
            company={job.company}
            meta={job.outcome}
            metaColor={outcomeColor(job.outcome)}
          />
        ))}
      </div>
    </Widget>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add src/components/widgets/Outbox.jsx
git commit -m "[feat] Add Outbox widget"
```

---

### Task 11: Build Stats widget

**Files:**
- Create: `src/components/widgets/Stats.jsx`

- [ ] **Step 1: Create src/components/widgets/Stats.jsx**

```jsx
import Widget from '../shared/Widget'
import { stats } from '../../mockData'

const tiles = [
  { label: 'Total Jobs', value: stats.totalJobs },
  { label: 'Applied', value: stats.applied },
  { label: 'Success Rate', value: stats.successRate },
  { label: 'Credits Used', value: stats.creditsUsed },
]

export default function Stats() {
  return (
    <Widget title="Stats">
      <div className="grid grid-cols-2 gap-3">
        {tiles.map(({ label, value }) => (
          <div
            key={label}
            className="bg-white/5 rounded-lg p-3 flex flex-col gap-1 border border-white/5"
          >
            <span className="text-2xl font-bold text-white">{value}</span>
            <span className="text-xs text-space-dim">{label}</span>
          </div>
        ))}
      </div>
    </Widget>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add src/components/widgets/Stats.jsx
git commit -m "[feat] Add Stats widget"
```

---

### Task 12: Build Settings widget

**Files:**
- Create: `src/components/widgets/Settings.jsx`

- [ ] **Step 1: Create src/components/widgets/Settings.jsx**

```jsx
import Widget from '../shared/Widget'
import { settings } from '../../mockData'

const fields = [
  { label: 'Resume Path', value: settings.resumePath },
  { label: 'Target Roles', value: settings.targetRoles },
  { label: 'Location', value: settings.locationPreference },
  { label: 'Model', value: settings.modelInUse },
]

export default function Settings() {
  return (
    <Widget title="Settings / Details">
      <div className="flex flex-col gap-3">
        {fields.map(({ label, value }) => (
          <div key={label} className="flex flex-col gap-0.5">
            <span className="text-xs text-space-dim">{label}</span>
            <span className="text-sm text-space-text truncate">{value}</span>
          </div>
        ))}
      </div>
    </Widget>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add src/components/widgets/Settings.jsx
git commit -m "[feat] Add Settings widget"
```

---

### Task 13: Wire all widgets into App

**Files:**
- Modify: `src/App.jsx`

- [ ] **Step 1: Replace placeholder columns in src/App.jsx with real widgets**

```jsx
import Navbar from './components/Navbar'
import Dashboard from './components/Dashboard'
import Inbox from './components/widgets/Inbox'
import Processing from './components/widgets/Processing'
import Outbox from './components/widgets/Outbox'
import Stats from './components/widgets/Stats'
import Settings from './components/widgets/Settings'

export default function App() {
  return (
    <div className="min-h-screen text-space-text">
      <Navbar />
      <Dashboard>
        <div className="col-span-3 flex flex-col gap-4 overflow-hidden">
          <Inbox />
          <Processing />
          <Outbox />
        </div>
        <div className="col-span-2 flex flex-col gap-4 overflow-hidden">
          <Stats />
          <Settings />
        </div>
      </Dashboard>
    </div>
  )
}
```

- [ ] **Step 2: Check browser — full dashboard**

Verify all 5 widgets render with correct data. Check:
- Navbar sticky at top
- Grain texture visible on background
- Left column: Inbox (tallest), Processing, Outbox
- Right column: Stats (2x2 grid), Settings (field list)
- Widgets animate in staggered on page load
- Cards have hover lift effect

- [ ] **Step 3: Commit**

```bash
git add src/App.jsx
git commit -m "[feat] Wire all widgets into dashboard layout"
```

---

### Task 14: Final polish — flex sizing for left column height distribution

**Files:**
- Modify: `src/components/widgets/Inbox.jsx`
- Modify: `src/components/widgets/Processing.jsx`
- Modify: `src/components/widgets/Outbox.jsx`

The left column widgets should fill vertical space in a 40/30/30 ratio. The `className` prop on `Widget` handles this via Tailwind flex sizing.

- [ ] **Step 1: Verify Inbox uses flex-[2], Processing and Outbox use flex-[1.5]**

These are already set in Tasks 8–10 via the `className` prop passed to `Widget`. Confirm the values match:

- `Inbox.jsx`: `className="flex-[2]"`
- `Processing.jsx`: `className="flex-[1.5]"`
- `Outbox.jsx`: `className="flex-[1.5]"`

If any differ, update them now.

- [ ] **Step 2: Verify the left column div has `overflow-hidden` and `flex flex-col gap-4`**

In `App.jsx`, the left column wrapper should be:
```jsx
<div className="col-span-3 flex flex-col gap-4 overflow-hidden">
```

Confirm this matches what was written in Task 13. No changes needed if it does.

- [ ] **Step 3: Check browser**

Verify Inbox is noticeably taller than Processing and Outbox, and all three fill the column without overflow.

- [ ] **Step 4: Commit (only if changes were made)**

```bash
git add src/components/widgets/Inbox.jsx src/components/widgets/Processing.jsx src/components/widgets/Outbox.jsx
git commit -m "[fix] Correct flex sizing for left column widget height distribution"
```
