#!/usr/bin/env python3
"""
pdf_darkner.py — Pre-Captiva PDF enhancement utility
======================================================
Analyzes each page of a scanned PDF and darkens faint pages so that
downstream image processing (e.g. Captiva Image Processor / Image
Converter binarization + blank-page detection) does not wash them out
or discard them as blank.

Pages that already look healthy are passed through UNTOUCHED (the
original page object is copied, no re-rasterization), so normal
documents are not degraded or bloated.

Pipeline applied to faint pages:
    1. Rasterize at --dpi (default 300) in grayscale
    2. Auto contrast stretch (percentile-based levels)
    3. Gamma darkening (gamma < 1 pulls midtones toward black)
    4. Optional Bradley adaptive thresholding (--bitonal) to produce
       a crisp black & white page that survives any binarizer

Usage:
    python pdf_darkner.py input.pdf                      # auto mode
    python pdf_darkner.py input.pdf -o fixed.pdf
    python pdf_darkner.py input.pdf --force              # enhance all pages
    python pdf_darkner.py input.pdf --bitonal            # B/W output for faint pages
    python pdf_darkner.py input.pdf --analyze-only       # report, no output file
    python pdf_darkner.py *.pdf --outdir enhanced/       # batch mode

Dependencies: pymupdf, numpy, pillow   (pip install pymupdf numpy pillow)
"""

import argparse
import glob
import json
import os
import sys
from dataclasses import dataclass, asdict

import fitz  # PyMuPDF
import numpy as np
from PIL import Image


# ----------------------------------------------------------------------------
# Page analysis
# ----------------------------------------------------------------------------

@dataclass
class PageStats:
    page: int
    background: float       # page background gray level (0=black, 255=white)
    ink_ratio: float        # fraction of pixels meaningfully darker than background
    median_ink: float       # median gray value of those ink pixels
    contrast: float         # background - median_ink (stroke darkness)
    is_blankish: bool       # almost no ink at all
    is_faint: bool          # has content, but content is too light
    action: str = "pass"    # pass | enhance | warn-blank


INK_DELTA = 25             # pixel counts as ink if darker than background-INK_DELTA
BLANK_INK_RATIO = 0.0015   # below this fraction of ink pixels => effectively blank
FAINT_MEDIAN_INK = 130     # ink median lighter than this => faint strokes
LOW_CONTRAST = 90          # ink barely darker than background => faint


def analyze_gray(gray: np.ndarray, page_no: int) -> PageStats:
    """Compute faintness metrics for a grayscale page image (uint8).

    All thresholds are measured RELATIVE to the page background so the
    detector works for sparse pages (a few lines of text) and dense
    pages alike, and catches very faint ink that a fixed absolute
    threshold would miss entirely.
    """
    background = float(np.percentile(gray, 90))
    ink_mask = gray < (background - INK_DELTA)
    ink_ratio = float(ink_mask.mean())

    if ink_ratio < BLANK_INK_RATIO:
        # Nothing detectable even before Captiva touches it
        return PageStats(page_no, round(background, 1), round(ink_ratio, 5),
                         255.0, 0.0, True, False, "warn-blank")

    median_ink = float(np.median(gray[ink_mask]))
    contrast = background - median_ink

    is_faint = (median_ink > FAINT_MEDIAN_INK) or (contrast < LOW_CONTRAST)

    return PageStats(page_no, round(background, 1), round(ink_ratio, 5),
                     round(median_ink, 1), round(contrast, 1),
                     False, is_faint, "enhance" if is_faint else "pass")


# ----------------------------------------------------------------------------
# Enhancement
# ----------------------------------------------------------------------------

def contrast_stretch(gray: np.ndarray, lo_pct=2.0, hi_pct=98.0) -> np.ndarray:
    """Percentile-based auto-levels: maps lo_pct -> 0 and hi_pct -> 255."""
    lo = np.percentile(gray, lo_pct)
    hi = np.percentile(gray, hi_pct)
    if hi - lo < 1:
        return gray
    out = (gray.astype(np.float32) - lo) * (255.0 / (hi - lo))
    return np.clip(out, 0, 255).astype(np.uint8)


def gamma_darken(gray: np.ndarray, gamma: float) -> np.ndarray:
    """gamma < 1.0 darkens midtones (faint gray text -> near black)."""
    lut = (np.power(np.arange(256) / 255.0, gamma) * 255.0).astype(np.uint8)
    return lut[gray]


def bradley_threshold(gray: np.ndarray, window_frac=0.08, t=0.15) -> np.ndarray:
    """
    Bradley/Roth adaptive thresholding via integral image.
    Robust against uneven illumination; rescues faint strokes that a
    fixed global threshold (typical capture binarizer) would erase.
    """
    h, w = gray.shape
    s = max(int(min(h, w) * window_frac), 16)
    half = s // 2

    integral = np.cumsum(np.cumsum(gray.astype(np.float64), axis=0), axis=1)
    integral = np.pad(integral, ((1, 0), (1, 0)), mode="constant")

    ys = np.arange(h)
    xs = np.arange(w)
    y1 = np.clip(ys - half, 0, h - 1)
    y2 = np.clip(ys + half, 0, h - 1)
    x1 = np.clip(xs - half, 0, w - 1)
    x2 = np.clip(xs + half, 0, w - 1)

    Y1, X1 = np.meshgrid(y1, x1, indexing="ij")
    Y2, X2 = np.meshgrid(y2, x2, indexing="ij")

    counts = (Y2 - Y1 + 1) * (X2 - X1 + 1)
    sums = (integral[Y2 + 1, X2 + 1] - integral[Y1, X2 + 1]
            - integral[Y2 + 1, X1] + integral[Y1, X1])
    means = sums / counts

    out = np.where(gray < means * (1.0 - t), 0, 255).astype(np.uint8)
    return out


def enhance_page(gray: np.ndarray, gamma: float, bitonal: bool) -> np.ndarray:
    out = contrast_stretch(gray)
    out = gamma_darken(out, gamma)
    if bitonal:
        out = bradley_threshold(out)
    return out


# ----------------------------------------------------------------------------
# PDF processing
# ----------------------------------------------------------------------------

def render_gray(page: fitz.Page, dpi: int) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def process_pdf(in_path: str, out_path: str, dpi: int, gamma: float,
                bitonal: bool, force: bool, analyze_only: bool) -> dict:
    src = fitz.open(in_path)
    report = {"file": os.path.basename(in_path), "pages": [], "enhanced": 0,
              "passed": 0, "blank_warnings": 0}

    dst = None if analyze_only else fitz.open()

    for i, page in enumerate(src):
        gray = render_gray(page, dpi)
        stats = analyze_gray(gray, i + 1)

        if force and not stats.is_blankish:
            stats.action = "enhance"

        report["pages"].append(asdict(stats))

        if analyze_only:
            continue

        if stats.action == "enhance":
            enhanced = enhance_page(gray, gamma, bitonal)
            img = Image.fromarray(enhanced, mode="L")
            if bitonal:
                img = img.convert("1")  # CCITT-friendly 1-bit
            tmp = fitz.open()
            w_pt, h_pt = page.rect.width, page.rect.height
            new_page = tmp.new_page(width=w_pt, height=h_pt)
            import io
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            new_page.insert_image(new_page.rect, stream=buf.getvalue())
            dst.insert_pdf(tmp)
            tmp.close()
            report["enhanced"] += 1
        else:
            # Copy original page object untouched — zero quality loss
            dst.insert_pdf(src, from_page=i, to_page=i)
            report["passed"] += 1
            if stats.action == "warn-blank":
                report["blank_warnings"] += 1

    if dst is not None:
        dst.save(out_path, garbage=3, deflate=True)
        dst.close()
        report["output"] = out_path
    src.close()
    return report


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Analyze and darken faint scanned PDFs before Captiva ingestion.")
    ap.add_argument("inputs", nargs="+", help="Input PDF file(s); wildcards ok")
    ap.add_argument("-o", "--output", help="Output file (single input only)")
    ap.add_argument("--outdir", help="Output directory (batch mode)")
    ap.add_argument("--dpi", type=int, default=300, help="Raster DPI (default 300)")
    ap.add_argument("--gamma", type=float, default=0.55,
                    help="Darkening gamma, <1 darkens (default 0.55)")
    ap.add_argument("--bitonal", action="store_true",
                    help="Adaptive-threshold faint pages to 1-bit B/W")
    ap.add_argument("--force", action="store_true",
                    help="Enhance every page, not just pages detected as faint")
    ap.add_argument("--analyze-only", action="store_true",
                    help="Print the faintness report without writing a PDF")
    ap.add_argument("--json", action="store_true", help="Emit report as JSON")
    args = ap.parse_args()

    files = []
    for pattern in args.inputs:
        files.extend(glob.glob(pattern))
    files = [f for f in files if f.lower().endswith(".pdf")]
    if not files:
        sys.exit("No PDF inputs found.")
    if args.output and len(files) > 1:
        sys.exit("-o/--output is for a single input; use --outdir for batches.")

    reports = []
    for f in files:
        if args.analyze_only:
            out = None
        elif args.output:
            out = args.output
        else:
            base, ext = os.path.splitext(os.path.basename(f))
            outdir = args.outdir or os.path.dirname(f) or "."
            os.makedirs(outdir, exist_ok=True)
            out = os.path.join(outdir, f"{base}_enhanced{ext}")

        rep = process_pdf(f, out, args.dpi, args.gamma,
                          args.bitonal, args.force, args.analyze_only)
        reports.append(rep)

        if not args.json:
            print(f"\n=== {rep['file']} ===")
            for p in rep["pages"]:
                flag = {"enhance": "DARKENED", "warn-blank": "BLANK?  ",
                        "pass": "ok      "}[p["action"]]
                print(f"  p{p['page']:>3}  [{flag}] ink={p['ink_ratio']*100:5.2f}%  "
                      f"median_ink={p['median_ink']:5.1f}  contrast={p['contrast']:5.1f}")
            if not args.analyze_only:
                print(f"  -> {rep['enhanced']} enhanced, {rep['passed']} untouched"
                      f"  ->  {rep['output']}")
            if rep["blank_warnings"]:
                print(f"  !! {rep['blank_warnings']} page(s) look blank even before "
                      f"processing — source rescan may be required.")

    if args.json:
        print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
