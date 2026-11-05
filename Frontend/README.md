# Frontend — Payout Reconciliation

Single-page frontend that:
1. Uploads two CSV files (System + Bank) to the backend.
2. Previews the reconciliation report (`.xlsx`) using the **excel-viewer** npm package.
3. Downloads the report.

## Features

- **File-name summary with tick marks** — after selecting/uploading files, each chosen file is listed with a `✓` tick.
- **Swapped-file detection** — reads the first line of each CSV and warns if the System file looks like a Bank file (and vice versa).
- **Fixed preview overflow** — the viewer sits in a scrollable wrapper so it never overlaps the download button.
- **Fully responsive** — works on mobile and desktop.

## Prerequisites

Backend (FastAPI) must be running. From the `Backend` folder:

```bash
cd ../Backend
python -m venv venv
.\venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn api:app --reload --port 8000
```

The backend enables CORS for `http://localhost:5173`, which is the port this frontend serves on.

## Install & Run

```bash
cd Frontend
npm install
npm run dev          # serves on http://localhost:5173
```

Open **http://localhost:5173**, select both CSVs, click **Reconcile & Upload**, then preview/download the report.

## Files

- `index.html` — UI + loads `excel-viewer` from the npm CDN (unpkg).
- `style.css` — all styling (separate file).
- `main.js` — upload, preview, download, and validation logic.
- `package.json` — declares `excel-viewer` as a dependency and Vite dev server.
- `vite.config.js` — serves on port 5173 to match backend CORS.

## Notes

- `excel-viewer` is loaded via its npm CDN (`unpkg.com/excel-viewer@...`) because it depends on global `xspreadsheet`/`XLSX` UMD bundles; this is the package's documented CDN usage and is the most reliable way to use it in a plain HTML page. `package.json` still declares it as an npm dependency (`npm i excel-viewer`).
- The preview fetches the backend report as a blob and creates an `object URL` so the viewer reads from a same-origin URL, avoiding CORS issues inside the viewer. A direct-URL fallback is included.