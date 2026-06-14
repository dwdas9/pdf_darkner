# pdf_darkner

A small command-line utility that **analyzes scanned PDFs and darkens only the
faint pages** before they are submitted to a document-capture pipeline (e.g.
OpenText Captiva / InputAccel Image Processor & Image Converter).

## The problem it solves

Some scanned PDFs arrive very light / low-contrast. When a capture pipeline
binarizes these pages (converts them to black & white) and runs blank-page
detection, the faint content can fall below the threshold and the page comes
out **washed white** — effectively blank — or gets discarded.

The usual manual workaround is to print the document, darken it, and rescan it.
`pdf_darkner` does that digitally: it boosts contrast and darkens the faint
strokes so the content survives downstream processing — no printing, no
rescanning.

## What it does

For every page in a PDF, the tool:

1. **Measures** the page — background level, how much "ink" is present, and how
   dark/contrasty that ink is (all relative to the page background, so it works
   for sparse text pages and dense pages alike).
2. **Decides** an action per page:
   - **pass** — healthy page, copied through **untouched** (no quality loss, no bloat)
   - **enhance** — faint page, gets darkened
   - **warn-blank** — no detectable content even before processing (flagged so a
     source rescan can be requested)
3. **Enhances** only the faint pages: auto contrast-stretch → gamma darkening →
   (optional) adaptive thresholding for crisp black & white output.

Because healthy pages are passed through unchanged, normal documents are not
degraded — only the problem pages are modified.

## Requirements

- Python 3.9+
- `pymupdf`, `numpy`, `pillow`

```bash
pip install pymupdf numpy pillow
```

## Quick start

```bash
# 1. Auto mode — detect faint pages and fix only those
python pdf_darkner.py input.pdf

#    -> writes input_enhanced.pdf next to the original

# 2. Choose the output name
python pdf_darkner.py input.pdf -o fixed.pdf

# 3. Just report faintness, write nothing (good first check)
python pdf_darkner.py input.pdf --analyze-only

# 4. Batch a whole folder
python pdf_darkner.py *.pdf --outdir enhanced/
```

## If output is still too light

```bash
# Darken harder (lower gamma = darker). Default is 0.55
python pdf_darkner.py input.pdf --gamma 0.4

# Produce crisp 1-bit black & white (survives any binarizer)
python pdf_darkner.py input.pdf --bitonal

# Enhance every page, not just the ones auto-detected as faint
python pdf_darkner.py input.pdf --force
```

## All options

| Option | Description |
|---|---|
| `-o, --output` | Output file (single input only) |
| `--outdir` | Output directory (batch mode) |
| `--dpi` | Raster DPI (default 300) |
| `--gamma` | Darkening gamma; `<1` darkens (default 0.55) |
| `--bitonal` | Adaptive-threshold faint pages to 1-bit B/W |
| `--force` | Enhance every page, not just faint ones |
| `--analyze-only` | Print the faintness report, write no PDF |
| `--json` | Emit the report as JSON (useful for logging/audit) |

## Example output

```
=== Certification (Signed)1.pdf ===
  p  1  [DARKENED] ink= 2.65%  median_ink=215.0  contrast= 34.0
  p  2  [ok      ] ink= 5.11%  median_ink= 73.0  contrast=180.0
  -> 1 enhanced, 1 untouched  ->  Certification (Signed)1_enhanced.pdf
```

## Notes

- The detector thresholds (`FAINT_MEDIAN_INK`, `LOW_CONTRAST`, etc.) are near the
  top of `pdf_darkner.py` and can be tuned for your documents.
- Run `--analyze-only` against a sample of real documents first to confirm the
  right pages are being flagged before enhancing in bulk.
- These documents may contain sensitive data — run the tool in an approved
  environment and follow your organization's data-handling policy.

---

## Interactive app (no install, no command line)

`pdf_darkner_app.html` is a self-contained version for end users who don't want
to touch a terminal. **Just double-click the file** — it opens in any modern
browser (Edge, Chrome, Firefox).

- Upload (or drag in) a PDF
- Every page is analyzed and faint pages are auto-flagged and darkened
- Adjust the **whole file** with Gentle / Standard / Strong presets and sliders,
  or set any **single page** to Skip / Global / Custom and fine-tune it
- Live before/after preview for every page
- Export a `*_darkened.pdf` copy

**Privacy:** the app runs entirely in the browser. The PDF is never uploaded —
nothing leaves the computer, and it works with no internet connection (the PDF
libraries are embedded in the file). This makes it safe for documents containing
sensitive data.

---

## Review workstation (`pdf_darkner_review.html`)

A professional three-pane document-review build for inspecting and validating
results, comparable to enterprise document-review software. Double-click to open
in a browser — same self-contained, offline, local-only model (libraries embedded,
nothing uploaded).

**Layout**
- **Page navigator** (left): lazy-rendered thumbnails with page numbers, faint-page
  flags, current-page highlight, page search/jump, S/M/L/Auto thumbnail sizes,
  resizable + collapsible.
- **Original (Before)** and **Processed (After)** viewers: zoom in/out, mouse-wheel
  and Ctrl-wheel zoom, fit-width, fit-page, actual size, drag-to-pan, high-quality
  re-render at every zoom level.

**Comparison**
- **Synchronized mode** (default): scroll, zoom, page, and pan stay locked together.
- **Independent mode**: each viewer keeps its own zoom/scroll/pan.
- **Difference detection**: side-by-side, difference overlay, blink compare, and
  highlight-changes-only, with adjustable sensitivity.
- **Minimap**: appears when zoomed in; drag the viewport rectangle to navigate.

**Workspace**
- Resizable splitters (double-click to auto-fit), collapse/expand panes, reset layout.
- Light / Dark / System themes.
- Layout, theme, thumbnail size, and darkening settings persist between sessions.
- Toolbar (open, recent, navigation, zoom, sync, diff, minimap, export, theme) and a
  status bar (file, page, zoom, sync state, render state, and memory on Chrome).

**Keyboard**

| Key | Action | Key | Action |
|---|---|---|---|
| Page Up / Down | Prev / Next page | Ctrl + +/− | Zoom in / out |
| Home / End | First / Last page | Ctrl + 0 | Fit page |
| Space | Toggle sync | Ctrl + 1 | Actual size |
| D | Toggle difference mode | Ctrl + O | Open file |
| M | Toggle minimap | Arrows (+Shift) | Pan (faster) |

**Known boundaries (single-file browser app):**
- *Multi-monitor undocking* — the pop-out button opens the current page in a new
  window; true cross-monitor docking needs a packaged desktop app (Electron).
- *Memory readout* is Chrome-only.
- *Recent Files* remembers names; browser security requires re-selecting the file
  via the picker (a disk path can't be reopened silently).
