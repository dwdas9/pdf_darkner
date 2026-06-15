# pdf_darkner — Developer Guide

> The definitive reference for the pdf_darkner application: architecture,
> components, data model, build, deployment, and the practices for changing it
> safely. This is a living document — when you change the code, change the
> section here that describes it, in the same commit.
>
> Maintainer: Das · Applies to: `pdf_darkner.html` (browser app) and
> `pdf_darkner.py` (CLI).

---

## 0. How to read this guide

The guide is ordered from the outside in: what the system is, how it is put
together, then each subsystem in the order data flows through it, then the
practical chapters (extending, troubleshooting, deploying).

If you are here to **fix a bug**, jump to the subsystem in Part 4 that owns the
behavior, then read "Impact of changes" at the end of that subsystem before you
touch anything.

If you are here to **add a feature**, read Part 3 (architecture) and Part 8
(extending the app) first — there are worked examples that match the most common
requests.

Every subsystem section follows the same shape on purpose:

- **Purpose** — what job it does.
- **Where it lives** — the functions and DOM it owns.
- **Dependencies** — what it needs and what needs it.
- **How it works** — the mechanism.
- **Impact of changes** — what you can break, and what to re-test.

---

## 1. What the application is

pdf_darkner solves one problem: scanned documents that arrive too faint survive
poorly through document-capture image processing (Captiva InputAccel, Kofax, and
similar), which can binarize and blank-page-detect the faint content into a blank
page. pdf_darkner darkens the faint pages **before** they enter capture, so the
content survives.

There are two deliverables that share one algorithm:

| Deliverable | File | Runtime | Audience |
|---|---|---|---|
| Browser review app | `pdf_darkner.html` | Any modern browser, offline | End users; reviewers |
| Command-line utility | `pdf_darkner.py` | Python 3.9+ | Batch/automation; engineers |

The darkening logic is intentionally duplicated in both (JavaScript and Python)
rather than shared, because the two run in completely different environments and
neither can call the other. **They must be kept behaviorally in sync by hand** —
see §6.4 and §10.

---

## 2. Technology stack and dependencies

### 2.1 Browser app

- **Plain HTML + CSS + vanilla JavaScript.** No framework, no bundler, no build
  toolchain in the traditional sense. There is exactly one runtime artifact: the
  single HTML file.
- **pdf.js** (Mozilla, Apache-2.0) — renders PDF pages to `<canvas>`. Pinned at
  `3.11.174`.
- **pdf-lib** (MIT) — assembles the exported PDF in the browser. Pinned at
  `1.17.1`.
- **Browser-native APIs only** for everything else: Canvas 2D, IntersectionObserver
  (thumbnail lazy-load), localStorage (persistence), Blob/URL (worker + export),
  `window.matchMedia` (system theme), `performance.memory` (Chrome-only readout).

Both libraries are **embedded inside the HTML file** (see §5, the build). At
runtime nothing is fetched from the network. This is a hard requirement, not a
convenience — the documents contain PII and the tool must make zero network
calls.

### 2.2 Python CLI

- **Python 3.9+**
- **PyMuPDF (fitz)** — render PDF pages and write output PDFs.
- **NumPy** — pixel math.
- **Pillow** — image construction for the rebuilt pages.

Declared in `requirements.txt`. Note PyMuPDF is AGPL — relevant if the CLI is ever
redistributed; the browser app does not use it.

---

## 3. High-level architecture

### 3.1 Browser app — mental model

The app is a single-page, single-document workstation. One PDF is open at a time.
There is no server, no router, no async backend. All state lives in one JavaScript
object (`S`, §4.1) and the UI is rendered imperatively from it.

The data flows in one direction through a chain of subsystems:

```
  File  ──► loadPDF ──► per-page analysis (analyze) ──► darkening settings
                               │
                               ▼
   thumbnails (lazy)      render cache  ◄── renderOriginal (pdf.js)
        │                      │
        ▼                      ▼
   navigator click ──►  setActivePage ──► renderViewer('orig')  ──► Original pane
                                      └──► renderViewer('proc')  ──► Processed pane
                                                   │  (processInto = darkening)
                                                   ▼
                                          diff / minimap / sync overlays
                                                   │
                                                   ▼
                                          exportPDF (pdf-lib) ──► *_darkened.pdf
```

Two rendering targets exist per page: the **Original** (straight from pdf.js) and
the **Processed** (the Original's pixels passed through the darkening LUT). The
Processed pane is always derived from the Original render at the same scale, which
is why both panes stay crisp at any zoom.

### 3.2 Subsystem map

The JavaScript is organized into these subsystems, in dependency order. Each has a
section in Part 4:

1. Worker bootstrap (§4.0)
2. State model (§4.1)
3. PDF loading (§4.2)
4. Analysis + darkening engine (§4.3) — the core IP
5. Render and cache (§4.4)
6. Thumbnails / navigator (§4.5)
7. Viewers: zoom, pan, fit (§4.6)
8. Synchronization (§4.7)
9. Difference detection (§4.8)
10. Minimap (§4.9)
11. Page navigation (§4.10)
12. Splitters, collapse, layout (§4.11)
13. Persistence and theme (§4.12)
14. Recent files (§4.13)
15. Export (§4.14)
16. Pop-out (§4.15)
17. Menus, toolbar, keyboard wiring (§4.16)

### 3.3 Python CLI — mental model

A straight pipeline, no state object: argparse → for each input file →
`process_pdf` → for each page render to grayscale → `analyze_gray` → if faint,
`enhance_page` → write with PyMuPDF. Covered in Part 7.

---

## 4. Browser app — subsystem reference

### 4.0 Worker bootstrap — `initWorker()`

**Purpose.** Start the pdf.js worker without a network fetch.

**Where it lives.** The IIFE `initWorker()` at the top of the script block.

**How it works.** pdf.js normally loads its worker from a URL. We cannot use a URL
(offline requirement), so the minified worker source is embedded in a
`<script id="pdfworker" type="text/plain">` tag, read at runtime, wrapped in a
`Blob`, and the resulting object URL is assigned to
`pdfjsLib.GlobalWorkerOptions.workerSrc`.

**Dependencies.** Requires the worker text to be present (injected by the build,
§5). Everything PDF-related depends on this having run.

**Impact of changes.** If you upgrade pdf.js, the worker text and the main library
must come from the **same version** or rendering will fail in subtle ways. Never
point `workerSrc` at a CDN — that reintroduces a network call and breaks the
security model.

---

### 4.1 State model — the `S` object

**Purpose.** Single source of runtime truth. There is no other state store.

**Where it lives.** `const S = {…}` near the top.

**Shape and meaning:**

| Field | Type | Meaning |
|---|---|---|
| `pdf` | PDFDocumentProxy | the loaded pdf.js document, or null |
| `fileName` | string | original file name (used for export naming) |
| `numPages` | number | page count |
| `page` | number | currently active page (1-based) |
| `pages[]` | array | per-page records (see below) |
| `sync` | bool | synchronized comparison on/off |
| `diffMode` | string | `side` \| `overlay` \| `blink` \| `changes` |
| `diffSens` | number | difference sensitivity threshold (luminance delta) |
| `minimap` | bool | minimap visible |
| `thumbSize` | string | `s` \| `m` \| `l` \| `auto` |
| `zoom` | object | `{orig:{scale,mode}, proc:{scale,mode}}` |
| `baseSize` | object | `{w,h}` unscaled page size in CSS px (from page 1) |
| `recents[]` | array | recent file names |
| `blinkTimer` | id | interval handle for blink mode |

**Per-page record (`S.pages[n-1]`):**

| Field | Meaning |
|---|---|
| `num` | page number |
| `metrics` | result of `analyze()` (null until analyzed) |
| `settings` | this page's darkening settings (`black`/`white` seeded from metrics) |
| `mode` | `skip` \| `global` \| `custom` — how this page is processed |
| `thumbRendered` | guard so a thumbnail renders once |

**The `mode` field is the heart of per-page control.** `skip` = pass through
untouched; `global` = use the drawer's global sliders; `custom` = use this page's
own `settings`. `effSettings(pg)` resolves a page's effective settings from its
mode.

**Impact of changes.** Adding a feature usually means adding a field here and a
line in `defaultSettings()` and/or the per-page record creation inside `loadPDF`.
If you persist it, also handle it in §4.12. Forgetting to seed a new per-page field
in `loadPDF` is the most common "undefined" bug.

---

### 4.2 PDF loading — `loadPDF`, `ensureAnalyzed`

**Purpose.** Turn a `File` into the open-document state and kick off analysis.

**Where it lives.** `loadPDF(file)`, `analyzeVisibleFirst()`, `ensureAnalyzed(num)`.

**How it works.**
1. `loadPDF` reads the file to an ArrayBuffer and opens it with
   `pdfjsLib.getDocument`. (`renderCache.clear()` first — a new document
   invalidates all cached renders.)
2. It builds the `S.pages[]` records, reads page 1's viewport to set
   `S.baseSize`, updates the status bar, registers the file in recents, builds the
   thumbnail shells, analyzes page 1 immediately, and shows page 1.
3. `ensureAnalyzed(num)` lazily analyzes a page the first time it is needed
   (on activation or when its thumbnail renders). It renders a small raster, runs
   `analyze()`, stores metrics, seeds `black`/`white`, and sets the initial `mode`
   (faint/blank → `global`, ok → `skip`).

**Dependencies.** Needs the worker (§4.0). Feeds everything downstream.

**Impact of changes.** `S.baseSize` is read from page 1 only — if you support
mixed page sizes per document, this must move to per-page. Analysis scale
(`thumbScale()*1.3`) trades speed for accuracy; raising it makes verdicts more
reliable but slows load on large files.

---

### 4.3 Analysis and darkening engine — the core IP

This is the most important subsystem. It is the algorithm; everything else is UI.

**Functions.** `defaultSettings()`, `analyze(data)`, `buildLUT(s)`,
`processInto(srcData,dstCanvas,s)`, `effSettings(pg)`, `globalSettings()`.

#### 4.3.1 `analyze(data)` — page measurement and verdict

Input is RGBA pixel data. Steps:

1. Build a 256-bin luminance histogram (`0.299R + 0.587G + 0.114B`).
2. `background = 90th percentile` of luminance (the paper color).
3. `p2 = 2nd percentile` (the darkest meaningful tone).
4. Two ink thresholds, both relative to background:
   - **sensitive** = `background − 10` → used to detect that *any* faint ink
     exists, so a faint page is not mislabeled blank.
   - **strict** = `background − 30` → used to measure true ink darkness without
     counting anti-aliasing halos.
5. `inkRatio` (sensitive), `medianInk` and `contrast` (strict, where
   `contrast = background − medianInk`).
6. **Verdict:**
   - `blank` if `inkRatio < 0.0008` (essentially nothing on the page),
   - else `faint` if `strict-ratio < 0.004` OR `medianInk > 135` OR
     `contrast < 95`,
   - else `ok`.
7. Seeds `black = p2 − 4` and `white = background` for the levels remap.

**Why two thresholds?** A single threshold either misses very faint ink (labels a
recoverable page "blank") or pulls in anti-aliasing and labels normal pages
"faint." The split fixed a real bug found in testing — see §9.

#### 4.3.2 `buildLUT(s)` — the darkening curve

Produces a 256-entry lookup table from a settings object. This is a **levels
remap + gamma**, not a naive brightness shift, because faint ink sits in a narrow
bright band and only a levels stretch rescues it:

```
dark   = s.dark/100            // "Darken faint ink" slider
con    = s.contrast/100        // "Contrast" slider
span   = white - black
white' = white - dark*span*0.55   // pull the white point down toward the ink
black' = black + con*span*0.35    // raise the black point
for each input value v:
    n = clamp((v - black') / (white' - black'), 0, 1)
    n = n ^ gamma                 // gamma < 1 darkens midtones
    out = n * 255
    if bitonal: out = (out < thresh) ? 0 : 255
```

The `black`/`white` come from the page's own metrics (auto levels), and the
sliders push those points. This is why darkening adapts per page instead of
applying a fixed curve.

#### 4.3.3 `processInto(srcData, dstCanvas, s)`

Applies the LUT to every pixel (via luminance), writes a grayscale result into the
destination canvas. This is the only place pixels are modified.

#### 4.3.4 `effSettings(pg)` / `globalSettings()`

`effSettings` resolves a page to its actual settings by `mode`: `skip`→null,
`global`→drawer settings merged with the page's auto `black`/`white`,
`custom`→the page's own `settings`. `globalSettings()` reads the drawer sliders.

**Impact of changes.** This subsystem defines output quality and the
blank/faint/ok verdicts that drive auto-darkening. Changing a constant
(`0.0008`, `135`, `95`, the `0.55`/`0.35` push factors) changes which pages get
touched and how hard. **Any change here must be mirrored in the Python CLI**
(§7) or the two tools will disagree. Re-test against the sample set and check the
verdict distribution before and after.

---

### 4.4 Render and cache — `renderOriginal`, the LRU

**Purpose.** Produce page rasters from pdf.js and avoid re-rendering.

**Where it lives.** `renderOriginal(num, scale)`, `cacheGet`/`cacheSet`,
`renderCache` (a `Map`), `RENDER_CACHE_MAX = 14`, `thumbScale()`, `DPR`.

**How it works.** `renderOriginal` rounds the scale, checks the cache by
`num@scale`, and on a miss renders the page to an offscreen canvas (white
background first, then pdf.js). The cache is a simple LRU: on access the entry is
re-inserted to mark it most-recently-used; on overflow the oldest key is evicted.
Processed renders are cached separately inside `renderViewer` keyed by
`proc-num@scale-settingsJSON`.

**Dependencies.** Everything visual (thumbnails, viewers, diff, minimap, export)
goes through here. `DPR` (devicePixelRatio clamped to 2) is multiplied into the
render scale for crispness.

**Impact of changes.** `RENDER_CACHE_MAX` trades memory for speed; on very large
or very high-DPI documents, lower it if memory climbs, raise it for snappier
back-and-forth paging. The settings-keyed processed cache means changing a slider
naturally produces new cache entries — they age out via the LRU.

---

### 4.5 Thumbnails / navigator — lazy rendering

**Purpose.** Page navigator that scales to 1000+ pages without freezing.

**Where it lives.** `buildThumbs()`, `renderThumb(num)`, `applyThumbLayout()`,
`thumbObserver` (IntersectionObserver).

**How it works.** `buildThumbs` creates a placeholder element per page with the
right aspect ratio (so the scrollbar is correct before anything renders) and
observes each with an IntersectionObserver rooted on the thumbs container with a
300px margin. When a placeholder scrolls near view, `renderThumb` renders it once
(guarded by `thumbRendered`) and opportunistically analyzes the page. This is the
"virtualization" — only visible thumbnails ever render.

`applyThumbLayout` computes the grid columns from the chosen size (`s`/`m`/`l`) or
uses `auto-fill` for Auto, and reflows on pane resize.

**Dependencies.** Uses `renderOriginal` at `thumbScale()`. Writes the faint-flag
dot from `metrics`.

**Impact of changes.** If you add a per-page status indicator, render it in
`renderThumb` and refresh it in `ensureAnalyzed` (the flag is set in both places
today). Changing `rootMargin` trades eager rendering (smoother scroll) for memory.

---

### 4.6 Viewers: zoom, pan, fit — the rendering core

**Purpose.** Display a page in each pane with zoom/pan/fit and crisp re-render.

**Where it lives.** `viewerEl`, `stageEl`, `computeFit(side)`,
`renderViewer(side)`, `renderBoth()`, `setZoomMode`, `zoomBy`,
`updateZoomIndicators`, `wireViewer(side)`.

**Model.** Each viewer is a scroll container holding a `.stage` div sized to
`baseSize × scale`. Inside the stage is a single canvas. Pan = native scroll;
drag-pan adjusts `scrollLeft/Top`. The displayed canvas is rendered at
`scale × DPR` device pixels and CSS-scaled down, which keeps text sharp at any
zoom.

`computeFit(side)` returns the scale for the current `mode` (`fitW`, `fitP`,
`actual`, or `custom`). `renderViewer` computes the scale, sizes the stage,
renders the Original at device resolution, and for the Processed side derives the
canvas through `processInto` (cached). It then draws diff overlays if active and
updates the minimap.

**Dependencies.** `renderOriginal`, the darkening engine (proc side), diff (§4.8),
minimap (§4.9). Drives the zoom indicators in toolbar and status bar.

**Impact of changes.** This is performance-sensitive — it runs on every page
change, zoom, and slider move. The device-scale cap (`DPR` clamped to 2, render
scale clamped to 6) bounds canvas size; raising those improves sharpness at the
cost of memory and speed. Re-test zoom at extremes and the cursor-anchored zoom in
`zoomBy`.

---

### 4.7 Synchronization — `mirrorScroll`

**Purpose.** Keep both viewers locked when `S.sync` is on.

**Where it lives.** `mirrorScroll(from)`, the scroll listener in `wireViewer`,
and the sync branches in `zoomBy`/`setZoomMode`.

**How it works.** Scroll positions are mirrored as ratios (so different scales stay
aligned), guarded by an `S._syncing` reentrancy flag cleared on the next animation
frame. Zoom sync applies the same scale/mode to both panes. Page changes always
update both panes regardless of sync.

**Impact of changes.** The reentrancy guard is essential — without it, mirroring
triggers the other viewer's scroll handler, which mirrors back, into a loop. Keep
the guard if you touch this.

---

### 4.8 Difference detection — `drawDiff`, blink

**Purpose.** Show what the darkening changed.

**Where it lives.** `getPairCanvases(scale)`, `drawDiff(dispCanvas,cssW,cssH)`,
`startBlink`/`stopBlink`, `applyDiffMode(mode)`.

**How it works.** `getPairCanvases` renders the Original and the Processed at one
scale. `drawDiff` compares them pixel-by-pixel on luminance; where the delta
exceeds `S.diffSens` the pixel is painted magenta. In `changes` mode unchanged
pixels are forced white (isolating the changes); in `overlay` mode the processed
content stays underneath for context. `blink` alternates the Processed canvas
between original and processed on a timer. `applyDiffMode` switches modes, manages
the blink timer, and ensures the Processed pane is visible for non-side modes.

**Dependencies.** Reads from the darkening engine and the render cache. Activated
from the toolbar menu and the `D` shortcut.

**Impact of changes.** Adding a diff mode means a menu item, a branch in
`drawDiff` (or a new render path), and a case in `applyDiffMode` — see the worked
example in §8.2. Sensitivity is a raw luminance delta (2–80); document any change
to its range in the UI.

---

### 4.9 Minimap — `drawMinimap`

**Purpose.** Overview + draggable viewport when zoomed in.

**Where it lives.** `minimapEl`, `drawMinimap(side,onlyRect)`,
`wireMinimapDrag(...)`.

**How it works.** Shown only when content overflows the viewer. Renders a small
page thumbnail once, then positions a rectangle from the viewer's scroll ratios
and visible fraction. Dragging the rectangle (or clicking the map) sets the
viewer's scroll, and mirrors to the other pane if sync is on.

**Impact of changes.** The `+20` offset in the rect position accounts for the
minimap header height — adjust together with the header CSS. Recompute only the
rectangle (`onlyRect=true`) on scroll; full redraw only on page/zoom change.

---

### 4.10 Page navigation — `setActivePage`

**Purpose.** The single entry point for "show page N."

**Where it lives.** `setActivePage(num, scrollThumb)`, `refreshDrawerForPage()`.

**How it works.** Clamps the page, updates the active thumbnail (optionally scrolls
it into view), updates the page inputs and status bar, ensures the page is
analyzed, refreshes the Adjust drawer's metrics for the page, renders both panes,
and restarts blink if active.

**Impact of changes.** Every navigation path (toolbar, thumbnails, keyboard, page
input, search) funnels here — fix navigation bugs in this one function, not in the
callers.

---

### 4.11 Splitters, collapse, layout — `wireSplitter`, `toggleCollapse`

**Purpose.** Resizable, collapsible three-pane workspace.

**Where it lives.** `wireSplitter(elId,leftPaneId,isNav)`, `toggleCollapse(which)`,
plus `saveLayout`/`restoreLayout`/`resetLayout` (§4.12).

**How it works.** A splitter drag adjusts the left pane's flex/width within clamps;
double-click resets to defaults. The navigator uses a fixed width; the two viewers
share flex. Collapsing hides a pane and its splitter. Layout changes persist.

**Impact of changes.** After any resize the viewers must re-render (the fit scale
changed) — `renderBoth()` is called on mouseup. If you add a fourth pane, the
splitter wiring and the flex math both need updating.

---

### 4.12 Persistence and theme — `store`, `applyTheme`

**Purpose.** Remember preferences between sessions; light/dark/system theme.

**Where it lives.** `store` (localStorage wrapper, `pdfdarkner.` prefix),
`saveLayout`/`restoreLayout`/`resetLayout`, `applyTheme(t)`.

**How it works.** `store.get/set` wrap localStorage in try/catch so the app still
runs where storage is blocked (e.g. some locked-down `file://` contexts) — it just
won't remember. Persisted keys: `theme`, `layout`, `thumbSize`, `darkening`,
`recents`. `applyTheme` resolves `system` via `matchMedia` and sets
`data-theme` on `<html>`; all colors derive from that via CSS variables.

**Impact of changes.** Add new persisted state through `store` and load it in
`wireUI`/`boot`. Never assume localStorage works — keep the try/catch. Theme is
pure CSS variables; add a theme by adding a `data-theme` block, not by touching JS
colors.

---

### 4.13 Recent files — `addRecent`, `buildRecentMenu`

**Purpose.** A recent-files list.

**How it works.** Names only, capped at 8, persisted. Browser security forbids
reopening a disk path silently, so selecting a recent entry re-opens the file
picker. Documented as a known boundary.

**Impact of changes.** True reopen needs the File System Access API (Chrome-only,
permission-gated) or the Electron path — see §11.

---

### 4.14 Export — `exportPDF`

**Purpose.** Write a darkened PDF (all pages or current page).

**Where it lives.** `exportPDF(currentOnly)`.

**How it works.** For each target page: ensure analyzed, render the Original at a
fixed export scale (2.0), resolve effective settings (respecting "only modify
faint pages"), darken via `processInto`, encode the canvas to PNG, embed with
pdf-lib, and add a page at the unscaled size. Saves a Blob and triggers a download
named `<file>_darkened.pdf` (or `_pN_` for a single page).

**Dependencies.** pdf-lib; the darkening engine; the render path.

**Impact of changes.** Output is **image-based** — the text layer is not
preserved. Preserving searchable text is the single biggest possible enhancement
and requires a different export strategy (§8.4 and §10). Export scale (2.0) trades
file size for fidelity.

---

### 4.15 Pop-out — `popOut`

**Purpose.** Best-effort multi-window: open the current page image in a new window.

**Impact of changes.** True cross-monitor docking is not achievable in a single
browser file; it is an Electron capability (§11). Do not over-invest here in the
browser build.

---

### 4.16 Menus, toolbar, keyboard — `wireUI`, `wireKeyboard`, `boot`

**Purpose.** Wire every control to its subsystem.

**How it works.** `wireUI` attaches all toolbar/drawer/menu handlers and restores
saved darkening settings. `wireKeyboard` maps the documented shortcuts (and ignores
keys while typing in inputs). `boot` applies theme, restores layout, wires the
viewers, and calls `wireUI`/`wireKeyboard`. `closeMenus`/`toggleMenu` manage the
dropdowns; a document click closes them.

**Impact of changes.** A handler that throws during `wireUI` stops the handlers
after it from attaching (this exact class of bug appeared in development — a
missing `refreshGlobalLabels` halted wiring; see §9). Keep handlers defensive and
test that the whole toolbar still responds after any change here.

---

## 5. The build: how the single file is produced

The HTML you ship is generated, not hand-edited with the libraries inside it. The
source template contains three placeholders:

```
/*__PDFJS_LIB__*/      → contents of pdfjs-dist build/pdf.min.js
/*__PDFLIB_LIB__*/     → contents of pdf-lib dist/pdf-lib.min.js
/*__PDFJS_WORKER__*/   → contents of pdfjs-dist build/pdf.worker.min.js
```

Build steps:

1. Obtain the two libraries at the pinned versions (e.g. `npm pack
   pdfjs-dist@3.11.174 pdf-lib@1.17.1` and extract).
2. Read the three build files.
3. In the worker text, escape any literal `</script>` to `<\/script>` (it lives
   inside a `<script type="text/plain">` tag).
4. Replace the three placeholders with the file contents.
5. Write the result as `pdf_darkner.html` (~1.9 MB).

**Keep the template and the built file distinct in your workflow.** Edit the
template (the version with placeholders); never hand-edit the 1.9 MB built file —
the embedded minified libraries make diffs unreadable and merges dangerous.

**Upgrading a library:** bump the version, re-pack, re-inject, and smoke-test
(load, render, zoom, diff, export). pdf.js main + worker must move together.

---

## 6. Configuration and tunable parameters

All tunables are constants near the top of their subsystem. The ones you are most
likely to touch:

| Parameter | Location | Default | Effect |
|---|---|---|---|
| Blank cutoff | `analyze` | `inkRatio < 0.0008` | Below this a page is "blank" |
| Faint rules | `analyze` | `medianInk>135 / contrast<95 / strict<0.004` | What counts as faint |
| Levels push | `buildLUT` | `0.55` (white), `0.35` (black) | How hard sliders darken |
| Render cache size | top of render | `RENDER_CACHE_MAX=14` | Memory vs paging speed |
| Device scale cap | `DPR` | `min(dpr,2)` | Sharpness vs memory |
| Export scale | `exportPDF` | `2.0` | Output fidelity vs file size |
| Thumb scales | `thumbScale` | s/m/l = 0.16/0.24/0.32 | Thumbnail resolution |
| Diff sensitivity range | `#diffSens` | 2–80 | Difference threshold |

### 6.4 Keeping JS and Python in sync

The browser `analyze`/`buildLUT` and the Python `analyze_gray`/`enhance_page`
implement the same algorithm with the same intent but separate code. When you
change a threshold or the darkening curve in one, change the other in the same
commit and note it in both files' headers. The Python equivalents:

| Browser | Python |
|---|---|
| `analyze` verdict rules | `analyze_gray` + module constants (`FAINT_MEDIAN_INK`, `LOW_CONTRAST`, `BLANK_INK_RATIO`) |
| `buildLUT` levels+gamma | `contrast_stretch` + `gamma_darken` |
| bitonal threshold | `bradley_threshold` (adaptive — note: the CLI uses adaptive thresholding, the browser uses a global threshold; this is a deliberate difference, see §7) |

---

## 7. Python CLI reference — `pdf_darkner.py`

**Structure.** `PageStats` (dataclass) → `analyze_gray(gray, page_no)` →
enhancement (`contrast_stretch`, `gamma_darken`, `bradley_threshold`,
`enhance_page`) → `render_gray(page, dpi)` → `process_pdf(...)` → `main()`
(argparse).

**Flow.** For each input PDF, `process_pdf` opens it with PyMuPDF, and for each
page renders grayscale at `--dpi`, runs `analyze_gray` to get a verdict, and for
faint pages runs `enhance_page` (contrast stretch → gamma → optional Bradley
adaptive threshold). Healthy pages are copied through with `insert_pdf` (true
pass-through, no re-raster). Output is written next to the input or to `--outdir`.

**Key difference from the browser.** The CLI's optional bitonal path uses
**Bradley/Roth adaptive thresholding** (local mean via integral image), which is
stronger than the browser's global threshold but slower. This is intentional: the
CLI is for batch quality, the browser is for interactive speed. If exact parity is
ever required, port Bradley to the browser (it is feasible but costs render time).

**Constants** (`INK_DELTA`, `BLANK_INK_RATIO`, `FAINT_MEDIAN_INK`, `LOW_CONTRAST`)
are the CLI analogue of the browser's `analyze` thresholds — keep them aligned
(§6.4).

**CLI contract.** Documented in the README options table; `--analyze-only` and
`--json` exist for dry-runs and logging/audit and should be preserved as the
machine-readable interface.

---

## 8. Extending the application — worked examples

General rule: find the owning subsystem in Part 4, add state in `S`
(§4.1), add the control in the DOM, wire it in `wireUI`, and re-render the affected
pane. Persist it through `store` if it should survive a reload.

### 8.1 Add a new darkening control (e.g. "sharpen faint edges")

1. Add a field to `defaultSettings()` and to `globalSettings()`.
2. Add a slider in the Adjust drawer and a label refresh in
   `refreshGlobalLabels()`.
3. Use the new field inside `buildLUT` (or add a post-LUT pass in `processInto`).
4. Wire the slider in `wireUI` to re-derive the Processed pane.
5. **Mirror it in Python** (§6.4) if it should affect batch output.
6. Re-test verdicts and the before/after on the sample set.

### 8.2 Add a difference mode

1. Add a `<div class="mi" data-diff="yourmode">` to `#diffMenu`.
2. Handle it in `drawDiff` (new comparison branch) or as a new render path.
3. Add a case in `applyDiffMode` (timers/visibility if needed).
4. Confirm the `D` shortcut still cycles sensibly.

### 8.3 Add a toolbar button / shortcut

1. Add the button to the toolbar markup with a title.
2. Wire `onclick` in `wireUI` to the subsystem function.
3. If it needs a key, add a `case` in `wireKeyboard` (respect the typing-in-input
   guard).

### 8.4 Preserve searchable text on export (large change)

Today export rasterizes. To keep text you must stop flattening pages. Options, in
order of effort: (a) only darken pages that need it and copy untouched pages
through as real PDF pages (pdf-lib `copyPages`) so at least healthy pages keep
their text; (b) apply darkening as a PDF image mask/transfer function rather than
a raster; (c) move processing to the Python service where Ghostscript/qpdf can
re-tone while preserving structure. This is the highest-value roadmap item — scope
it deliberately and coordinate with whatever consumes the output.

---

## 9. Troubleshooting

| Symptom | Likely cause | Where to look |
|---|---|---|
| Blank viewers, PDF won't open | worker not started / version mismatch | §4.0 `initWorker`; confirm pdf.js main+worker versions match |
| Whole toolbar unresponsive after an edit | a handler threw during `wireUI`, halting the rest | §4.16; check console for the first error |
| Normal pages flagged "faint" | ink threshold pulling in anti-aliasing | §4.3.1; the strict/sensitive split exists for this — don't merge them |
| Faint page flagged "blank" and skipped | sensitive threshold too strict | §4.3.1 `inkRatio` cutoff |
| Settings not remembered | localStorage blocked (file:// policy) | §4.12; expected on some locked-down setups; host via http(s) to fix |
| Sluggish on huge files | cache too small / device scale too high | §4.4 `RENDER_CACHE_MAX`; §4.6 `DPR`/clamp |
| Sync drifts / jitters | reentrancy guard removed or broken | §4.7 `S._syncing` |
| Export too light / too dark | levels push or gamma | §4.3.2 `buildLUT` |
| Minimap rect misaligned | header offset vs CSS | §4.9 `+20` offset |

**First move for any JS bug:** open the browser console. Because there is no build
step or source map indirection, the stack trace points straight at the function.

---

## 10. Testing

There is no unit-test harness in the repo today; testing has been done by driving
the built file in a headless browser (load a known PDF, exercise navigation, zoom,
each diff mode, export, and assert no console errors). Recommended practice when
changing the engine or a subsystem:

1. Keep a small fixture set of PDFs spanning faint / normal / very-faint / blank.
2. After an engine change, compare the verdict distribution before and after, and
   eyeball before/after on the faint fixtures.
3. After a UI change, smoke-test the full toolbar and confirm export still
   produces a valid PDF.
4. If you formalize this, a headless-browser script asserting "no console errors +
   export downloads a non-empty PDF" catches the majority of regressions cheaply.

---

## 11. Deployment

**Browser app.** It is one static file. Three viable distributions:

- **Hand out the file** — works, but each update is a re-distribution and some
  locked-down setups restrict `file://` script/localStorage.
- **Host on internal web/SharePoint (recommended for an enterprise)** — serve the
  single HTML from an intranet `https://` origin. localStorage works normally, no
  files to email, updates are a one-file replace, and it runs from a trusted
  origin. Behavior is identical; only the address changes.
- **Electron desktop app** — wrap the same HTML/JS unchanged to gain real OS
  windows (true multi-monitor docking), real file paths (working Recent Files),
  and an installer. This is the path if those boundaries (§4.13, §4.15) must
  become real features; it then follows normal software-packaging/approval.

**CLI / server-side.** `pdf_darkner.py` is the automation path — a watched folder
or scheduled job can darken incoming PDFs headlessly. Same algorithm, no UI.

**Security / compliance (applies to all).** Processing is fully local and makes no
network calls by design — keep it that way (no CDN, no telemetry). The documents
can contain PII, so deployment should be cleared with the data/compliance owner
regardless of the technical locality.

---

## 12. Known limitations and roadmap

- **Image-based export (no text layer)** — highest-value item; see §8.4.
- **Single page size assumed** from page 1 (`S.baseSize`) — generalize for mixed-
  size documents.
- **Multi-monitor docking** and **silent Recent-Files reopen** — need Electron.
- **JS/Python parity is manual** — a shared spec or a generated constants file
  would reduce drift.
- **No automated test suite** — see §10.

---

## 13. Glossary

- **Levels remap** — mapping a black point and white point across the full 0–255
  range; the mechanism that rescues faint ink.
- **Gamma** — a power curve on normalized luminance; `<1` darkens midtones.
- **Bitonal** — pure 1-bit black and white.
- **Binarization** — a capture pipeline step converting grayscale to black/white;
  the step that "washes" faint pages.
- **Verdict** — a page's classification: `ok` / `faint` / `blank`.
- **LRU** — least-recently-used cache eviction (the render cache).
- **DPR** — device pixel ratio; the display's physical-to-CSS pixel multiplier.

---

## 14. Maintenance conventions

- Edit the **template**, rebuild the single file; never hand-edit the built HTML.
- Any engine change goes into **both** the browser and the CLI in the same commit
  (§6.4), with a note in each file header.
- Update the relevant section of **this guide** in the same commit as the code
  change — that is what keeps it a source of truth.
- Keep the **no-network** rule absolute.
- Record significant changes in the file header revision history (browser app) and
  here.

*Maintainer: Das.*

---

## 15. v2.0 changes — explicit apply, multi-select, and regions

v2.0 changes the **default behavior** and adds three subsystems. Everything in
Parts 1–14 still holds; this part documents what is new. All v2.0 code is
commented in-file with the `// [Das]` footprint.

### 15.1 Behavior change — no automatic darkening

Previously, `ensureAnalyzed` set faint/blank pages to `mode='global'` on load, so
darkening appeared immediately. **v2.0 removes that.** Every page now loads in
`mode='skip'` (review-only). Analysis still runs and still sets the faint/blank
verdict (so the navigator can flag pages), but nothing is darkened until the user
explicitly applies. The Processed pane mirrors the Original until then.

Where this lives: `loadPDF` seeds each page as `mode:'skip', regions:[]`, and
`ensureAnalyzed` no longer assigns a mode. If you ever want an "auto-darken faint
on load" option, that is the single place to branch — but keep `skip` the default.

### 15.2 Per-page data model additions

Each `S.pages[n-1]` gains:

- `regions[]` — array of `{rect:{x,y,w,h} (normalized 0..1), settings}` rubber-band
  regions for that page.

New `S` fields: `selection` (Set of selected page numbers), `selAnchor` (last
plain-clicked thumbnail, for Shift-range), `regionMode` (bool), `selRegion`
(`{page, idx}` of the selected region or null).

`pageHasEdits(pg)` = `mode!=='skip' || regions.length>0`. This drives the "edited"
thumbnail dot and the status-bar **Edited n** counter (`updateEditedCount`).

### 15.3 Apply-scope subsystem

**Functions.** `applyToPages(nums, bind)`, `clearPageEdits(num)`,
`invalidatePages(nums)`, `updateEditedCount`.

The sliders only define a *candidate* treatment. `applyToPages` is the only thing
that changes a page's base treatment:

- **bind=false (stamp)** — copies the current slider values into each page's own
  `settings` and sets `mode='custom'`. Later slider moves do **not** affect stamped
  pages. Used by *This page*, *Selected*, *All pages*.
- **bind=true (live)** — sets `mode='global'`; the page follows the live sliders.
  Used by *Global (live)*.

`invalidatePages` drops the affected pages' cached processed canvases (keys
matching `proc-<n>@`) so the next render rebuilds them. Always call it after
changing a page's settings/regions.

**Impact of changes.** This is the contract the whole v2.0 UX rests on: nothing
mutates page treatment except `applyToPages`/`clearPageEdits`. Keep it that way —
don't scatter `pg.mode=` assignments elsewhere.

### 15.4 Selection subsystem

**Functions.** `parseRange`, `rangeToString`, `setSelection`, `toggleSelect`,
`rangeSelect`. **DOM.** `#navSelect` (range box), `#navSelClear`, thumbnail
`.selected` class + `.selflag` check.

`S.selection` (a Set) is the source of truth. Two inputs stay in sync: typing in
the range box (`parseRange`) and Ctrl/Shift-click on thumbnails (handled in the
thumbnail `onclick` in `buildThumbs`). `setSelection` updates the count, the box
text (unless the edit came from the box), and the thumbnail classes.

### 15.5 Region (rubber-band) subsystem

**Functions.** `regionLayerEl`, `drawRegionBoxes(side)`, `selectRegion`,
`deselectRegion`, `deleteSelectedRegion`, `clearRegionsOnPage`,
`loadSettingsIntoSliders`, `setRegionMode`, `wireRegionDraw(side)`. Compositing is
in `buildProcessed` (Part 4.3 area).

**How it works.** With region mode on, `wireRegionDraw` captures a drag on a viewer
(capture-phase listener that calls `stopPropagation`, so the pan handler — which
also early-returns when `S.regionMode` — never fires). On mouseup it converts the
pixel rectangle to **normalized** page coordinates (relative to the scaled stage's
bounding box) and pushes a region seeded with the current slider settings, then
selects it. Region boxes are rendered by `drawRegionBoxes` into a `.region-layer`
**inside the stage** (so they scroll and scale with the page), positioned in
percentages. Clicking a box selects it and loads its settings into the sliders;
slider moves then live-edit the selected region (see the `onAdjust` handler in
`wireUI`). `buildProcessed` composites regions by re-processing the original pixels
inside each rectangle over the base layer.

**Why the layer is inside the stage.** An earlier approach put the layer as a
sibling of the stage; it misaligned on scroll/zoom because its offset parent was
the viewer, not the scaled stage. `renderViewer` wipes the stage on each render, so
it re-creates the layer and calls `drawRegionBoxes` after mounting the canvas.

**Impact of changes.** Regions touch the data model, `buildProcessed`, render,
export, and the diff (all of which go through `buildProcessed`, so they get regions
for free). Coordinates are normalized — never store pixel rects, or they break at
other zooms/scales. The capture-phase draw handler plus the `S.regionMode` guard on
the pan handler are what keep drawing and panning from fighting; keep both.

### 15.6 About modal and GUI copyright

`openAbout`/`closeAbout` toggle `#aboutBackdrop`. The modal is static markup
(version, author, copyright, library licenses). A subtle `© Das` item in the status
bar (`#sbCopy`) and the toolbar info button (`#btnAbout`) both open it; Escape and a
backdrop click close it. Update the version/year in the modal markup and in the file
header together when you cut a release.

### 15.7 v2.0 keyboard additions

`R` toggles region mode, `Delete`/`Backspace` removes the selected region, and
`Escape` exits region mode → else deselects a region → else closes the About modal.
