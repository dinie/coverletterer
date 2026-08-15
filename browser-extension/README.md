# CoverLetterer Capture (browser extension)

A Manifest V3 Chrome extension: click the toolbar icon on a job-ad page to
create a CoverLetterer `JobApplication` for it (scraped description + your
default resume attached), without opening the app. Personal use only — not
published to the Chrome Web Store.

## Install (unpacked)

1. `chrome://extensions` → enable **Developer mode** (top right) → **Load
   unpacked** → select this `browser-extension/` folder.
2. In CoverLetterer, go to **Profile → Extension access → Generate token**
   and copy the token (shown once).
3. Right-click the new toolbar icon → **Options** → paste the token, set the
   **Backend URL** (`http://localhost:8000` for local dev, or your deployed
   `https://<prefix>-backend.fly.dev`) → **Save & Test**.

## Use

Open a job ad (SEEK, Indeed, LinkedIn, or any site CoverLetterer can parse),
click the toolbar icon. The badge shows the result:

- **✓ green** — added (or already tracked)
- **! amber** — added, but the description needs a manual paste in the app,
  or the token isn't set up yet
- **✗ red** — request failed (check the backend URL/token in Options)

Hover the icon for the full message. No popup, no OS notifications — just
the badge, so no icon assets are needed.

## Notes

- The extension never touches your CoverLetterer browser session/cookies —
  it authenticates purely via the personal access token, so it works
  whether or not you have CoverLetterer open in another tab.
- It prefers a page's `<link rel="canonical">` URL over the visible tab URL,
  since some job boards' URLs carry tracking query params.
- `manifest.json`'s `host_permissions` lists both `localhost:8000` and the
  `*.fly.dev` backend; edit it if you deploy under a different domain.
