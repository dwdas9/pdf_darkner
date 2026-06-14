# pdf_darkner

In Banking and Insurance, where large scale customer documents are scanned and ingested, one of the frequent issues is low-quality or faint scans. Most of the document capture workflows like Captiva Capture (Captiva InputAccel) or Kofax Capture involve some sort of image processing at some stage, because in almost all cases the documents need to be converted to black and white or to some other format.

Essentially it means most of these capture workflows run some processing on the scanned documents, and sometimes this 'washes' the paper clean if the document was already faint. The image processing modules cannot tell whether a faint mark is a smudge to be cleaned or actual content that needs to be kept. So the faint content gets removed and the page comes out blank.

To get around this, users sometimes rescan the document, and sometimes they print the document again in a darker tone from a file and then rescan it. But these are a waste of paper and time, and not something desirable.

So this project gives users a way to fix the faint PDFs themselves before sending them into the capture workflow, without the printing and rescanning. It darkens the faint pages so the content survives the downstream image processing.

There are two tools here. One is a browser app for end users who just want to open a file and fix it. The other is a command-line utility for people who are comfortable with a terminal, or for running things in bulk and automation. Both do the same core job, they just suit different users.

---

# 1. The browser app — `pdf_darkner.html`

## What it is

`pdf_darkner.html` is a single self-contained file. You just double-click it and it opens in a browser (Edge, Chrome, Firefox). There is nothing to install, no Python, no setup, and no internet needed. The PDF libraries are built into the file itself.

It is a three-pane document review tool. On the left you get a page navigator with thumbnails, in the middle you see the original scan, and on the right you see the darkened (processed) result. The idea is that you can compare the before and after side by side, page by page, fix the faint pages, and then export a clean copy.

Everything runs locally in the browser. The PDF is never uploaded anywhere and no network call is ever made, so it is safe to use on documents that contain customer information.

## How to use it

1. Open `pdf_darkner.html` in your browser.
2. Drag a PDF onto the window, or click **Open** and choose a file.
3. Each page is analyzed automatically. Faint pages are flagged and darkened, and good pages are left as they are.
4. Compare the original (middle) against the processed result (right). Move through pages from the thumbnails on the left.
5. If you want to push a page darker or lighter, open **Adjust** and use the presets or sliders.
6. When you are happy, use **Export** to save the darkened PDF.

## What it does to the pages

For every page the tool measures the background, how much ink is on the page, and how dark that ink is. Based on that it decides what to do:

- A healthy page is left untouched, so good scans keep their full quality.
- A faint page is darkened, so the content does not get washed out by the capture workflow.
- A page with nothing detectable on it is flagged, so you know a rescan from the source may be needed.

You can darken the whole file at once with the Gentle / Standard / Strong presets, or set a single page on its own with Skip / Global / Custom. There is also a pure black and white option for the worst cases.

## The three panes

**Page navigator (left).** Thumbnails for every page with the page number on each one. Faint pages are flagged. The current page is highlighted. You can search for a page number and jump to it, change the thumbnail size, and resize or collapse the pane. Thumbnails load as you scroll so even large files stay responsive.

**Original / Before (middle)** and **Processed / After (right).** Both viewers support zoom in and out, mouse-wheel and Ctrl + mouse-wheel zoom, fit-to-width, fit-to-page, actual size, and drag to pan when zoomed in. The pages re-render as you zoom so the text stays sharp.

## Comparing the two

- **Synchronized mode** is on by default. Scrolling, zooming, paging, and panning happen in both viewers together, so you are always looking at the same spot on both.
- **Independent mode** lets each viewer keep its own zoom and position.
- **Difference detection** shows you exactly what changed between the original and the processed page. There are four modes: side by side, difference overlay, blink compare, and highlight changes only. The sensitivity is adjustable.
- **Minimap** shows up when you are zoomed in. It gives a small overview of the page with a box for the part you are looking at, and you can drag the box to move around.

## The workspace

- All panes are resizable with the splitters. Double-click a splitter to auto-fit, and you can collapse panes you don't need.
- Light, Dark, and System themes.
- Your layout, theme, thumbnail size, and darkening settings are remembered between sessions.
- A toolbar across the top and a status bar at the bottom showing the file name, current page, zoom level, sync state, and render state.

## Keyboard shortcuts

| Key | Action | Key | Action |
|---|---|---|---|
| Page Up / Page Down | Previous / Next page | Ctrl + + / − | Zoom in / out |
| Home / End | First / Last page | Ctrl + 0 | Fit page |
| Space | Toggle sync | Ctrl + 1 | Actual size |
| D | Toggle difference mode | Ctrl + O | Open file |
| M | Toggle minimap | Arrow keys (+ Shift) | Pan (faster) |

## A few things to know

- Because the export rebuilds each page from the darkened image, the output is image-based. If you need the output to stay searchable, keep that in mind.
- The multi-monitor pop-out opens the current page in a new window. Full docking across monitors would need a desktop version.
- The memory readout in the status bar only shows on Chrome and Edge.
- These documents can contain sensitive data. Even though everything runs locally, use the tool in an approved environment and follow your organization's data-handling policy.

---

# 2. The command-line utility — `pdf_darkner.py`

## What it is

`pdf_darkner.py` is a small command-line tool that does the same darkening, but from a terminal instead of a browser. It is meant for the cases the browser app is not the best fit for, like running a whole folder of PDFs in one go, or wiring the darkening into a script or a server-side step so it runs without anyone clicking anything.

It looks at a PDF, finds the faint pages, and darkens only those. The healthy pages are passed through untouched, so the good documents are not changed at all and only the problem pages are fixed.

## What you need

It runs on Python 3.9 or newer and uses three libraries:

```bash
pip install pymupdf numpy pillow
```

## How to use it

The simplest case is just pointing it at a PDF. It finds the faint pages, darkens them, and writes a new file next to the original:

```bash
python pdf_darkner.py input.pdf
# writes input_enhanced.pdf
```

You can choose the output name, or run a whole folder at once:

```bash
# choose the output name
python pdf_darkner.py input.pdf -o fixed.pdf

# do a whole folder
python pdf_darkner.py *.pdf --outdir enhanced/
```

Before fixing anything in bulk, it is a good idea to just look at what the tool thinks is faint. The analyze-only mode prints a report for each page and writes nothing, so you can confirm it is flagging the right pages first:

```bash
python pdf_darkner.py input.pdf --analyze-only
```

If the result still comes out too light, you can push it harder, or go to pure black and white for the worst scans:

```bash
# darken more (lower gamma = darker)
python pdf_darkner.py input.pdf --gamma 0.4

# pure black and white, survives any binarizer
python pdf_darkner.py input.pdf --bitonal

# darken every page, not just the ones it picked as faint
python pdf_darkner.py input.pdf --force
```

## What it does to the pages

It works the same way as the browser app. For every page it measures the background, the amount of ink, and how dark that ink is, and then it decides:

- **pass** — a healthy page, copied through untouched.
- **enhance** — a faint page, gets darkened.
- **warn-blank** — nothing detectable on the page, so it is flagged for a possible rescan from the source.

Because only the faint pages are touched, the normal documents are not degraded.

## The options

| Option | What it does |
|---|---|
| `-o, --output` | Output file (for a single input) |
| `--outdir` | Output folder (for batch mode) |
| `--dpi` | Render DPI (default 300) |
| `--gamma` | Darkening amount; lower is darker (default 0.55) |
| `--bitonal` | Make the faint pages pure 1-bit black and white |
| `--force` | Darken every page, not just the faint ones |
| `--analyze-only` | Print the report, write no file |
| `--json` | Print the report as JSON, useful for logging |

## Example output

```
=== Certification (Signed)1.pdf ===
  p  1  [DARKENED] ink= 2.65%  median_ink=215.0  contrast= 34.0
  p  2  [ok      ] ink= 5.11%  median_ink= 73.0  contrast=180.0
  -> 1 enhanced, 1 untouched  ->  Certification (Signed)1_enhanced.pdf
```

## A note

The thresholds that decide what counts as faint are near the top of the file and can be tuned for your own documents if needed. And as with the browser app, these documents can carry sensitive data, so run it in an approved environment and follow your organization's data-handling policy.