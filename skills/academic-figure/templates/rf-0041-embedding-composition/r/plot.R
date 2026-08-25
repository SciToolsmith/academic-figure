#!/usr/bin/env Rscript

fail <- function(msg) { message("ERROR: ", msg); quit(status = 2) }
args <- commandArgs(trailingOnly = TRUE)
opts <- list(input = NULL, `output-prefix` = NULL, title = "Embedding and sample composition", dpi = "320")
for (arg in args) {
  if (!startsWith(arg, "--") || !grepl("=", arg, fixed = TRUE)) fail(paste0("arguments must use --name=value: ", arg))
  p <- strsplit(sub("^--", "", arg), "=", fixed = TRUE)[[1]]; key <- p[1]; value <- paste(p[-1], collapse = "=")
  if (!key %in% names(opts)) fail(paste0("unknown argument --", key)); opts[[key]] <- value
}
if (is.null(opts$input) || is.null(opts$`output-prefix`)) fail("--input and --output-prefix are required")
dpi <- suppressWarnings(as.integer(opts$dpi)); if (is.na(dpi) || dpi < 72) fail("--dpi must be at least 72")
d <- tryCatch(read.csv(opts$input, stringsAsFactors = FALSE, check.names = FALSE), error = function(e) fail(conditionMessage(e)))
req <- c("observation_id", "sample_id", "x", "y", "category")
if (!all(req %in% names(d)) || nrow(d) == 0) fail(paste("CSV must contain", paste(req, collapse = ", ")))
if (nrow(d) > 200000) fail("at most 200,000 observations are supported")
for (nm in c("observation_id", "sample_id", "category")) d[[nm]] <- trimws(as.character(d[[nm]]))
if (any(d$observation_id == "") || anyDuplicated(d$observation_id) || any(d$sample_id == "") || any(d$category == "")) fail("observation_id must be unique and sample_id/category non-empty")
d$x <- suppressWarnings(as.numeric(d$x)); d$y <- suppressWarnings(as.numeric(d$y))
if (any(!is.finite(d$x)) || any(!is.finite(d$y))) fail("x and y must be finite numeric values")
if (!"sample_order" %in% names(d)) d$sample_order <- match(d$sample_id, unique(d$sample_id))
d$sample_order <- suppressWarnings(as.numeric(d$sample_order)); if (any(!is.finite(d$sample_order))) fail("sample_order must be finite")
sample_order_check <- tapply(d$sample_order, d$sample_id, function(x) length(unique(x)))
if (any(sample_order_check != 1)) fail("sample_order must be consistent within each sample")
samples <- names(sort(tapply(d$sample_order, d$sample_id, unique))); categories <- unique(d$category)
if (length(samples) < 2 || length(samples) > 40 || length(categories) < 2 || length(categories) > 16) fail("expected 2–40 samples and 2–16 categories")
palette <- c("#C8755C", "#4E8995", "#887DA5", "#789566", "#BE974A", "#A96775", "#5F91B7", "#B87C44")
cols <- setNames(rep(palette, length.out = length(categories)), categories)
counts <- table(factor(d$category, levels = categories), factor(d$sample_id, levels = samples)); totals <- colSums(counts); prop <- sweep(counts, 2, totals, "/")
draw <- function(device_fun) {
  device_fun(); par(bg = "#FBFAF7", family = "sans", oma = c(0.5, 0.5, 4.8, 0.5))
  layout(matrix(c(1, 2), nrow = 1), widths = c(1.35, 1))
  par(mar = c(4.2, 4.4, 3.6, 1.4))
  point_cex <- if (nrow(d) < 2000) 0.85 else max(0.25, 25 / sqrt(nrow(d)))
  plot(d$x, d$y, pch = 16, col = adjustcolor(cols[d$category], alpha.f = if (nrow(d) < 2000) 0.78 else max(0.15, 1200 / nrow(d))), cex = point_cex,
       xlab = "Embedding axis 1", ylab = "Embedding axis 2", axes = FALSE, asp = 1)
  axis(1, col = "#9AA5A9", col.axis = "#68767D", cex.axis = 0.75); axis(2, col = "#9AA5A9", col.axis = "#68767D", cex.axis = 0.75)
  title("A  Supplied embedding", adj = 0, cex.main = 1.0, col.main = "#20272D", font.main = 2)
  legend("topleft", legend = categories, pch = 16, col = cols[categories], bty = "n", ncol = 2, cex = 0.72)
  par(mar = c(6.2, 4.4, 3.6, 1.2))
  mids <- barplot(prop, col = cols[categories], border = "#FBFAF7", space = 0.35, names.arg = samples, las = 2, cex.names = 0.72,
                  ylim = c(0, 1.14), axes = FALSE, ylab = "Composition (%)")
  axis(2, at = c(0, .25, .5, .75, 1), labels = c(0, 25, 50, 75, 100), col = "#9AA5A9", col.axis = "#68767D", cex.axis = 0.75)
  abline(h = c(.25, .5, .75, 1), col = "#E5E1DA", lwd = 0.65); box(bty = "l", col = "#9AA5A9")
  text(mids, 1.035, paste0("n=", totals), srt = 90, adj = 0, cex = 0.62, col = "#68767D")
  title("B  Composition from the same rows", adj = 0, cex.main = 1.0, col.main = "#20272D", font.main = 2)
  mtext(opts$title, outer = TRUE, side = 3, adj = 0.04, line = 2.25, cex = 1.35, font = 2, col = "#20272D")
  mtext(sprintf("%s supplied observations · %d samples · composition denominators are reported above bars.", format(nrow(d), big.mark = ","), length(samples)),
        outer = TRUE, side = 3, adj = 0.04, line = 0.55, cex = 0.74, col = "#68767D")
  dev.off()
}
prefix <- opts$`output-prefix`; dir.create(dirname(prefix), recursive = TRUE, showWarnings = FALSE)
draw(function() png(paste0(prefix, ".png"), width = 12, height = 6.6, units = "in", res = dpi, bg = "#FBFAF7"))
draw(function() pdf(paste0(prefix, ".pdf"), width = 12, height = 6.6, bg = "#FBFAF7", useDingbats = FALSE))
message(paste0("Validated ", nrow(d), " observations; sample denominators: ", paste(paste0(samples, "=", totals), collapse = ", "), "; excluded rows: 0."))
