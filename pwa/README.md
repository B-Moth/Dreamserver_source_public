# DreamCatcher PWA (brief)

This folder contains the optional React + Vite Progressive Web App used as a UI for the `dreamserver` backend. It's included for completeness and to demonstrate a small full-stack setup.

Maintainer-friendly notes:
- The PWA is self-contained under this `pwa/` directory.
- You can run it locally for manual testing, but it is not required to evaluate the Python server.

Quick start (from `pwa/`):

```bash
npm install
npm run dev   # start dev server with HMR
npm run build # create production build in dist/
```

If you prefer to skip the frontend during review, ignore the `pwa/` folder — the server provides the same API surface the PWA uses.
