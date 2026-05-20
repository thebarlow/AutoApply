# React Dashboard Design

**Date:** 2026-05-19  
**Status:** Approved

## Overview

A display-only React dashboard for the Auto Apply job application pipeline. Space-themed dark UI with purples and blues. Mocked data only for now — backend integration deferred.

## Stack

- **Scaffolding:** Vite + React
- **Styling:** Tailwind CSS
- **Animations:** Framer Motion
- **Data:** Static mocked data (`src/mockData.js`), no API calls

## Component Tree

```
App
├── Navbar
└── Dashboard
    ├── LeftColumn
    │   ├── Inbox
    │   ├── Processing
    │   └── Outbox
    └── RightColumn
        ├── Stats
        └── Settings
```

## Visual Design

### Background
- Base color: `#0a0a1a` (deep dark navy)
- Full-page grainy SVG noise texture layered via a `::before` pseudo-element on `body`
- Accent palette: indigo/violet purples and cobalt blues

### Navbar
- Sticky, full viewport width
- Dark semi-transparent background with `backdrop-blur`
- Left: "Auto Apply" — bold, white
- Right: "Credits: $0.00" — muted purple/blue
- Sits above all content (high z-index)

### Widget Cards (shared style)
- Background: `bg-white/5` (dark semi-transparent)
- Border: `border-purple-900/40` (subtle purple)
- Rounded corners
- Soft inner glow (box-shadow, purple tint)

## Layout

Two-column grid below the navbar:

| Left Column (60%) | Right Column (40%) |
|---|---|
| Inbox (~40% height) | Stats (top half) |
| Processing (~30% height) | Settings (bottom half) |
| Outbox (~30% height) | |

## Widget Specs

### Inbox
- Displays pending job listings as cards
- Each card: job title, company name, date added
- Tallest widget — most data lives here

### Processing
- Jobs currently being scored or having resume/cover letter generated
- Each card: job title, company, current stage (e.g. "Scoring", "Generating")

### Outbox
- Completed or applied jobs
- Each card: job title, company, outcome (e.g. "Applied", "Skipped")

### Stats
- 2x2 grid of metric tiles
- Metrics: Total Jobs, Applied, Success Rate, Credits Used
- Each tile: large number + small label

### Settings
- Static display fields
- Fields: Resume Path, Target Roles, Location Preference, Model In Use

## Animations

- **Widget entrance:** Framer Motion fade + slide-up on page load, staggered per widget
- **Card hover:** subtle scale or glow lift via Framer Motion `whileHover`

## Data

All data mocked in `src/mockData.js`. Shape mirrors what the FastAPI backend will eventually return, so wiring up real data later requires only replacing the import with a fetch call.

## Out of Scope

- Backend integration
- Interactivity (clicks, state changes, filtering)
- Authentication
- Routing
