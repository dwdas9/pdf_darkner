
How it was built

The application is a plain HTML app relying on JavaScript. This approach was used so that there are no security or deployment related issues in a security tight environment. It is a single HTML file that opens in any browser, so there is nothing to install and no admin rights needed. Everything runs locally in the browser. The document is never uploaded and the app makes no network calls, which matters because these are customer documents.

It uses two small open-source libraries that do the heavy lifting. pdf.js renders each page so it can be shown and read pixel by pixel. pdf-lib builds the darkened pages back into a PDF the user can download. Both are embedded inside the HTML file, so it works fully offline. The rest, like the darkening logic and the comparison, is plain JavaScript I wrote.

The layout

The HTML is a three pane workspace:

- Left: a navigator with thumbnails of every page. Faint pages are flagged so the user can see where the problems are.
- Middle: the original page (Before), with zoom and pan to inspect it.
- Right: the processed page (After), so the original and the result sit side by side.

The two view panes stay synced by default, so scrolling or zooming one moves the other. There is also a difference view that highlights what changed between Before and After.

The pseudo code

There are two stages. The app analyses the pages on its own, but it does not change anything until the user decides to apply it.

Stage 1, when a PDF is opened (automatic, review only):

  FOR each page in the PDF:
      render the page and read the brightness of its pixels
      find the paper colour (background) and the ink (pixels darker than the paper)
      measure how dark the ink is and the contrast against the paper

      IF there is almost no ink:                          flag the page as blank
      ELSE IF the ink is too light or contrast is too low: flag the page as faint
      ELSE:                                                flag the page as ok

  // nothing is darkened here, the flags just show the user where the faint pages are

Stage 2, when the user applies (their choice of pages):

  the user sets the darkening, then picks where to apply it
  (this page, selected pages, all pages, or just a drawn region of a page)

  FOR each chosen page (or region):
      stretch the ink down toward black while keeping the paper white
      darken the mid-tones a bit more
      save the improved page

  // pages the user does not pick are left exactly as they were

A couple of things worth noting. The user is always in control, the tool only flags and never changes a page on its own. And it is not inventing anything, just re-stretching the faint ink so it survives the capture step. That is the same thing the print, darken and rescan workaround does, only digitally.
