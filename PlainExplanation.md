
How it was built

The application is a plain HTML app relying on JavaScript. This approach was used so that there are no security or deployment related issues in a security tight environment. It is a single HTML file that opens in any browser, so there is nothing to install and no admin rights needed. Everything runs locally in the browser. The document is never uploaded and the app makes no network calls, which matters because these are customer documents.

It uses two small open-source libraries that do the heavy lifting. pdf.js renders each page so it can be shown and read pixel by pixel. pdf-lib builds the darkened pages back into a PDF the user can download. Both are embedded inside the HTML file, so it works fully offline. The rest, like the darkening logic and the comparison, is plain JavaScript I wrote.

The layout

The HTML is a three pane workspace:

- Left: a navigator with thumbnails of every page. Faint pages are flagged so the user can see where the problems are.
- Middle: the original page (Before), with zoom and pan to inspect it.
- Right: the processed page (After), so the original and the result sit side by side.

The two view panes stay synced by default, so scrolling or zooming one moves the other. There is also a difference view that highlights what changed between Before and After. One key point on the design: nothing is changed automatically. The user decides what to apply, whether it is one page, selected pages, all pages, or just a drawn region when only part of a page is faint.

The pseudo code

In one line: read each page's pixels, find where the ink sits versus the paper, and if the ink is too light, stretch and darken it. Good pages are left untouched.

  FUNCTION darken_pdf(input_pdf):
      FOR each page IN input_pdf:
          image   = render page to grayscale
          metrics = ANALYZE(image)
          IF metrics.verdict == "faint":
              write ENHANCE(image, metrics) to output
          ELSE:
              write original page to output      // healthy pages untouched
      RETURN output_pdf

  FUNCTION ANALYZE(image):
      background   = brightness of the paper
      ink_amount   = how much of the page is ink
      ink_darkness = typical brightness of the ink
      contrast     = background - ink_darkness
      IF ink_amount is almost zero:                      verdict = "blank"
      ELSE IF ink is too light OR contrast is too low:   verdict = "faint"
      ELSE:                                              verdict = "ok"
      RETURN { background, ink_darkness, contrast, verdict }

  FUNCTION ENHANCE(image, metrics):
      // 1. Stretch the faint ink down toward black, keep the paper white
      // 2. Apply gamma to pull mid-tones further toward black
      // 3. (optional) for the worst scans, convert to pure black & white
      RETURN enhanced image

Two things to note: it works per page and only touches the faint ones, so normal documents are never degraded. And it is not inventing content, just re-stretching the faint ink so it survives the capture step. That is the same thing the print, darken and rescan workaround does, only digitally.
