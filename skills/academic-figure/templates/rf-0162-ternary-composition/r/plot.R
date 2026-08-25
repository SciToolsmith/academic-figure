#!/usr/bin/env Rscript

abort <- function(message, status = 2L) {
  writeLines(paste0("ERROR: ", message), con = stderr())
  quit(save = "no", status = status)
}

script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_path <- if (length(script_arg)) normalizePath(sub("^--file=", "", script_arg[[1]]), mustWork = TRUE) else normalizePath(".")
root <- dirname(dirname(script_path))
defaults <- list(
  input = file.path(root, "data", "simulated_fixed_seed_demo.csv"),
  output_prefix = file.path(getwd(), "ternary_r"),
  title = "Three-part compositions",
  component_labels = "Component A,Component B,Component C",
  sum_target = "1",
  sum_tolerance = "1e-6",
  normalize = "false",
  dpi = "320"
)

parse_args <- function(values) {
  result <- defaults
  i <- 1L
  while (i <= length(values)) {
    token <- values[[i]]
    if (!startsWith(token, "--")) abort(paste0("unexpected argument: ", token))
    clean <- substring(token, 3L)
    if (grepl("=", clean, fixed = TRUE)) {
      pieces <- strsplit(clean, "=", fixed = TRUE)[[1]]
      key <- pieces[[1]]
      value <- paste(pieces[-1], collapse = "=")
    } else {
      key <- clean
      if (key == "normalize") {
        value <- "true"
      } else {
        if (i == length(values)) abort(paste0("missing value for --", key))
        i <- i + 1L
        value <- values[[i]]
      }
    }
    key <- gsub("-", "_", key, fixed = TRUE)
    if (!key %in% names(result)) abort(paste0("unknown argument: --", clean))
    result[[key]] <- value
    i <- i + 1L
  }
  result
}

as_flag <- function(value, name) {
  lowered <- tolower(trimws(value))
  if (lowered %in% c("true", "1", "yes")) return(TRUE)
  if (lowered %in% c("false", "0", "no")) return(FALSE)
  abort(paste0(name, " must be true or false"))
}

as_number <- function(value, name) {
  parsed <- suppressWarnings(as.numeric(value))
  if (length(parsed) != 1L || !is.finite(parsed)) abort(paste0(name, " must be a finite number"))
  parsed
}

first_unique <- function(values) unique(values)

args <- parse_args(commandArgs(trailingOnly = TRUE))
normalize_rows <- as_flag(args$normalize, "--normalize")
sum_target <- as_number(args$sum_target, "--sum-target")
sum_tolerance <- as_number(args$sum_tolerance, "--sum-tolerance")
dpi <- as_number(args$dpi, "--dpi")
if (sum_target <= 0) abort("--sum-target must be positive")
if (sum_tolerance < 0) abort("--sum-tolerance must be nonnegative")
if (dpi < 150 || dpi > 1200) abort("--dpi must be between 150 and 1200")
component_labels <- trimws(strsplit(args$component_labels, ",", fixed = TRUE)[[1]])
if (length(component_labels) != 3L || any(!nzchar(component_labels))) {
  abort("--component-labels must contain exactly three nonempty comma-separated labels")
}
if (!file.exists(args$input)) abort(paste0("input CSV does not exist: ", args$input))

data <- tryCatch(
  read.csv(args$input, stringsAsFactors = FALSE, check.names = FALSE, na.strings = character()),
  error = function(e) abort(paste0("could not read input CSV: ", conditionMessage(e)))
)
required <- c("sample_id", "component_a", "component_b", "component_c")
missing <- setdiff(required, names(data))
if (length(missing)) abort(paste0("missing required column(s): ", paste(missing, collapse = ", ")))
if (!nrow(data)) abort("input CSV has no data rows")

data$sample_id <- trimws(as.character(data$sample_id))
if (any(!nzchar(data$sample_id))) abort("sample_id must not be empty")
if (anyDuplicated(data$sample_id)) abort(paste0("duplicate sample_id: ", data$sample_id[duplicated(data$sample_id)][[1]]))
for (column in c("component_a", "component_b", "component_c")) {
  parsed <- suppressWarnings(as.numeric(data[[column]]))
  if (any(!is.finite(parsed))) abort(paste0(column, " must contain finite numeric values"))
  if (any(parsed < 0)) abort(paste0(column, " must be nonnegative"))
  data[[column]] <- parsed
}
totals <- data$component_a + data$component_b + data$component_c
if (any(totals <= 0)) abort("each row must have a positive component total")
if (normalize_rows) {
  data$component_a <- data$component_a / totals
  data$component_b <- data$component_b / totals
  data$component_c <- data$component_c / totals
} else {
  bad <- which(abs(totals - sum_target) > sum_tolerance)
  if (length(bad)) {
    abort(sprintf(
      "row %d: component sum is %.12g, expected %.12g ± %.3g; use --normalize only when scientifically intended",
      bad[[1]] + 1L, totals[[bad[[1]]]], sum_target, sum_tolerance
    ))
  }
  data$component_a <- data$component_a / sum_target
  data$component_b <- data$component_b / sum_target
  data$component_c <- data$component_c / sum_target
}

if (!"group" %in% names(data)) data$group <- "All samples"
if (!"facet" %in% names(data)) data$facet <- "Composition"
if (!"label" %in% names(data)) data$label <- ""
data$group <- trimws(as.character(data$group))
data$facet <- trimws(as.character(data$facet))
data$label <- trimws(as.character(data$label))
if (any(!nzchar(data$group)) || any(!nzchar(data$facet))) abort("group and facet must not be empty when supplied")
facets <- first_unique(data$facet)
groups <- first_unique(data$group)
if (length(facets) > 9L) abort(paste0(length(facets), " facets exceed the readable single-figure limit of 9"))
if (length(groups) > 16L) abort(paste0(length(groups), " groups exceed the supported color/marker combinations (16)"))
if (sum(nzchar(data$label)) > 18L) abort(paste0(sum(nzchar(data$label)), " labels exceed the readable single-figure limit of 18"))

has_type <- "source_type" %in% names(data)
has_seed <- "source_seed" %in% names(data)
if (xor(has_type, has_seed)) abort("source_type and source_seed must be supplied together")
provenance_note <- NULL
if (has_type) {
  data$source_type <- trimws(as.character(data$source_type))
  data$source_seed <- trimws(as.character(data$source_seed))
  if (any(!nzchar(data$source_type)) || any(!nzchar(data$source_seed))) abort("provenance fields must not be empty")
  pairs <- unique(paste(data$source_type, data$source_seed, sep = "\r"))
  if (length(pairs) != 1L) abort("source_type/source_seed must be constant across the file")
  if (tolower(data$source_type[[1]]) == "simulated") {
    seed <- suppressWarnings(as.integer(data$source_seed[[1]]))
    if (is.na(seed) || seed <= 0L || as.character(seed) != data$source_seed[[1]]) abort("simulated data require one positive integer source_seed")
    provenance_note <- paste0("SIMULATED DEMONSTRATION DATA · fixed seed ", seed)
  } else {
    provenance_note <- paste0("Declared source: ", data$source_type[[1]])
  }
}

height_triangle <- sqrt(3) / 2
data$x <- data$component_b + 0.5 * data$component_c
data$y <- height_triangle * data$component_c
palette <- c("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#6A3D9A", "#8C6D31", "#1B9E77", "#7570B3", "#E7298A", "#66A61E", "#A6761D", "#1F78B4", "#B15928", "#4D4D4D")
pch_values <- c(21, 22, 24, 23, 25, 21, 22, 24, 23, 25, 21, 22, 24, 23, 25, 21)
group_color <- setNames(palette[seq_along(groups)], groups)
group_pch <- setNames(pch_values[seq_along(groups)], groups)

draw_triangle <- function(panel, show_legend = FALSE) {
  plot.new()
  plot.window(xlim = c(-0.11, 1.11), ylim = c(-0.09, height_triangle + 0.10), asp = 1)
  polygon(c(0, 1, 0.5), c(0, 0, height_triangle), border = "#31383D", lwd = 1.05, col = NA)
  for (fraction in c(0.25, 0.5, 0.75)) {
    segments(0.5 * (1 - fraction), height_triangle * (1 - fraction), 1 - fraction, 0, col = "#DCE2E1", lwd = 0.65)
    segments(fraction + 0.5 * (1 - fraction), height_triangle * (1 - fraction), fraction, 0, col = "#DCE2E1", lwd = 0.65)
    segments(0.5 * fraction, height_triangle * fraction, 1 - 0.5 * fraction, height_triangle * fraction, col = "#DCE2E1", lwd = 0.65)
  }
  text(0.025, 0.025, component_labels[[1]], adj = c(0, 0), cex = 0.76, font = 2, col = "#202528")
  text(0.975, 0.025, component_labels[[2]], adj = c(1, 0), cex = 0.76, font = 2, col = "#202528")
  text(0.5, height_triangle + 0.035, component_labels[[3]], adj = c(0.5, 0), cex = 0.82, font = 2, col = "#202528")
  panel_data <- data[data$facet == panel, , drop = FALSE]
  for (group in groups) {
    subset <- panel_data[panel_data$group == group, , drop = FALSE]
    if (!nrow(subset)) next
    points(subset$x, subset$y, pch = group_pch[[group]], bg = group_color[[group]], col = "#FBFAF7", cex = 1.15, lwd = 0.8)
    labelled <- subset[nzchar(subset$label), , drop = FALSE]
    if (nrow(labelled)) text(labelled$x, labelled$y, labels = labelled$label, pos = 4, offset = 0.35, cex = 0.64, col = "#202528")
  }
  title(main = paste0(panel, " · n=", nrow(panel_data)), adj = 0, line = 0.2, cex.main = 1.0, font.main = 2, col.main = "#182128")
  if (show_legend && length(groups) > 1L) {
    legend("topright", legend = groups, pch = unname(group_pch[groups]), pt.bg = unname(group_color[groups]), col = "#FBFAF7", pt.cex = 1.05, cex = 0.68, bty = "n", inset = c(0.01, 0.08))
  }
}

ncols <- min(3L, length(facets))
nrows <- ceiling(length(facets) / ncols)
width <- max(5.8, 4.25 * ncols)
height <- 1.35 + 3.9 * nrows + if (length(groups) > 1L) 0.25 else 0
output_parent <- dirname(args$output_prefix)
if (!dir.exists(output_parent)) dir.create(output_parent, recursive = TRUE, showWarnings = FALSE)

render <- function(device) {
  if (device == "png") {
    png(paste0(args$output_prefix, ".png"), width = width, height = height, units = "in", res = dpi, bg = "#FBFAF7", type = if (capabilities("cairo")) "cairo" else getOption("bitmapType"))
  } else {
    cairo_pdf(paste0(args$output_prefix, ".pdf"), width = width, height = height, onefile = TRUE, bg = "#FBFAF7")
  }
  on.exit(dev.off(), add = TRUE)
  par(mfrow = c(nrows, ncols), mar = c(0.4, 0.4, 1.8, 0.4), oma = c(1.5, 0.8, if (is.null(provenance_note)) 3.4 else 4.2, 0.8), bg = "#FBFAF7", family = "sans")
  for (index in seq_along(facets)) draw_triangle(facets[[index]], show_legend = index == 1L)
  if (length(facets) < nrows * ncols) for (unused in seq_len(nrows * ncols - length(facets))) plot.new()
  mtext(args$title, side = 3, outer = TRUE, adj = 0, line = if (is.null(provenance_note)) 1.6 else 2.4, cex = 1.45, font = 2, col = "#182128")
  subtitle <- paste0(nrow(data), " samples · ", length(groups), " group(s) · ", length(facets), " facet(s)", if (normalize_rows) " · rows explicitly normalized for display" else "")
  if (!is.null(provenance_note)) mtext(provenance_note, side = 3, outer = TRUE, adj = 0, line = 1.2, cex = 0.78, col = "#59666F")
  mtext(subtitle, side = 3, outer = TRUE, adj = 0, line = 0.3, cex = 0.72, col = "#59666F")
  mtext("Compositional display only; grid lines are not thresholds or significance regions.", side = 1, outer = TRUE, adj = 0, line = 0.25, cex = 0.64, col = "#66737B")
}

render("png")
render("pdf")
mode_text <- if (normalize_rows) "explicitly normalized" else paste0("validated sum target ", format(sum_target, trim = TRUE))
writeLines(paste0("Validated ", nrow(data), " rows, ", length(groups), " group(s), ", length(facets), " facet(s); ", mode_text, "; excluded rows: 0."))
if (!is.null(provenance_note)) writeLines(provenance_note)
writeLines(paste0("Wrote ", args$output_prefix, ".png"))
writeLines(paste0("Wrote ", args$output_prefix, ".pdf"))
