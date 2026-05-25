  - Transforms JSX/TypeScript on the fly as the browser requests each file
  - Watches your source files and pushes updates to the browser without a full reload (HMR)
  - Proxies API calls to uvicorn so you don't hit CORS issues during development
  
  In production, the dev server goes away — you run vite build once to produce the static files, then serve those. The transformation work is already done.