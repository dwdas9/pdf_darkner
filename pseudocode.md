```pseudocode
FUNCTION darken_pdf(input_pdf):
    FOR each page IN input_pdf:
        image    = render page to grayscale
        metrics  = ANALYZE(image)

        IF metrics.verdict == "faint":
            enhanced = ENHANCE(image, metrics)
            write enhanced page to output
        ELSE:
            write original page to output   // healthy pages untouched
    RETURN output_pdf


FUNCTION ANALYZE(image):
    histogram  = count how many pixels fall at each brightness (0=black .. 255=white)
    background = brightness of the paper            (90th percentile of histogram)
    ink_pixels = pixels meaningfully darker than the background
    ink_amount = how much of the page is ink
    ink_darkness = typical brightness of the ink pixels
    contrast   = background − ink_darkness

    IF ink_amount is almost zero:        verdict = "blank"   // nothing to recover
    ELSE IF ink is too light OR contrast is too low:  verdict = "faint"
    ELSE:                                verdict = "ok"

    RETURN { background, ink_darkness, contrast, verdict }


FUNCTION ENHANCE(image, metrics):
    // 1. Levels stretch: map the faint ink band down toward black,
    //    keep the paper white
    black_point = darkest meaningful ink
    white_point = paper background
    FOR each pixel:
        normalize pixel between black_point and white_point   // spread to full 0..255

    // 2. Gamma: pull mid-tones further toward black
    FOR each pixel:
        pixel = pixel ^ gamma            // gamma < 1 darkens

    // 3. (optional) for the worst scans, convert to pure black & white
    IF bitonal mode:
        FOR each pixel:
            pixel = (pixel < threshold) ? black : white

    RETURN enhanced image
```