#!/usr/bin/env Rscript

MAX_GROUPS <- 12L
MAX_ANNOTATIONS <- 3L
MAX_ANNOTATION_LENGTH <- 300L
POINT_SHAPES <- c(21L, 22L, 24L, 23L, 25L, 7L, 8L, 0L, 2L, 5L, 6L, 1L)

abort <- function(message) stop(message, call. = FALSE)

script_args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", script_args, value = TRUE)
if (length(file_arg) != 1L) abort("Cannot determine plot.R location")
script_dir <- dirname(normalizePath(sub("^--file=", "", file_arg), mustWork = TRUE))
data_dir <- file.path(dirname(script_dir), "data")

parse_cli <- function(args) {
  options <- list(input = file.path(data_dir, "simulated_fixed_seed_ordination.csv"),
                  group_column = NULL, axis_metadata = NULL, supplied_annotations = NULL,
                  output_prefix = NULL, title = "Precomputed ordination", dpi = "320")
  aliases <- c(input = "input", `group-column` = "group_column", `axis-metadata` = "axis_metadata",
               `supplied-annotations` = "supplied_annotations", `output-prefix` = "output_prefix",
               title = "title", dpi = "dpi")
  index <- 1L
  while (index <= length(args)) {
    token <- args[[index]]
    if (token %in% c("--help", "-h")) {
      cat("Usage: Rscript r/plot.R --output-prefix=PATH [--group-column=group] [--axis-metadata=FILE] [--supplied-annotations=FILE]\n")
      quit(status = 0L)
    }
    if (!startsWith(token, "--")) abort(paste0("Unexpected argument: ", token))
    body <- substring(token, 3L)
    equals <- regexpr("=", body, fixed = TRUE)[1L]
    if (equals > 0L) {
      key <- substring(body, 1L, equals - 1L)
      value <- substring(body, equals + 1L)
    } else {
      key <- body
      index <- index + 1L
      if (index > length(args) || startsWith(args[[index]], "--")) abort(paste0("Missing value for --", key))
      value <- args[[index]]
    }
    if (!key %in% names(aliases)) abort(paste0("Unknown option --", key))
    if (!nzchar(value)) abort(paste0("Empty value for --", key))
    options[[aliases[[key]]]] <- value
    index <- index + 1L
  }
  if (is.null(options$output_prefix)) abort("--output-prefix is required")
  if (grepl("\\.(png|svg|pdf)$", options$output_prefix, ignore.case = TRUE)) abort("--output-prefix must not include an extension")
  if (!grepl("^[0-9]+$", options$dpi)) abort("--dpi must be an integer from 300 to 1200")
  options$dpi <- as.integer(options$dpi)
  if (is.na(options$dpi) || options$dpi < 300L || options$dpi > 1200L) abort("--dpi must be an integer from 300 to 1200")
  options
}

read_table <- function(path, name, required) {
  if (!file.exists(path) || dir.exists(path)) abort(paste0(name, " file not found: ", path))
  table <- tryCatch(
    read.csv(path, stringsAsFactors = FALSE, check.names = FALSE, colClasses = "character",
             na.strings = character(), strip.white = FALSE),
    error = function(error) abort(paste0("Cannot read ", name, " as CSV: ", conditionMessage(error)))
  )
  if (!nrow(table)) abort(paste0(name, " must contain at least one data row"))
  if (any(!nzchar(trimws(names(table))))) abort(paste0(name, " contains an empty column name"))
  if (anyDuplicated(names(table))) abort(paste0(name, " contains duplicate column names"))
  missing <- setdiff(required, names(table))
  if (length(missing)) abort(paste0(name, " is missing required columns: ", paste(missing, collapse = ", ")))
  for (column in names(table)) table[[column]] <- trimws(table[[column]])
  attr(table, "source_headers") <- names(table)
  table
}

provenance_value <- function(table, name) {
  headers <- attr(table, "source_headers")
  has_status <- "data_status" %in% headers
  has_seed <- "simulation_seed" %in% headers
  if (xor(has_status, has_seed)) abort(paste0(name, " must provide data_status and simulation_seed together"))
  if (!has_status) return(NULL)
  if (any(!nzchar(table$data_status)) || any(!nzchar(table$simulation_seed))) abort(paste0(name, " has empty provenance values"))
  values <- unique(paste(table$data_status, table$simulation_seed, sep = "\r"))
  if (length(values) != 1L) abort(paste0(name, " has inconsistent provenance values"))
  values[[1L]]
}

validate_provenance <- function(named_tables) {
  values <- lapply(names(named_tables), function(name) provenance_value(named_tables[[name]], name))
  values <- unlist(values, use.names = FALSE)
  if (length(values) > 1L && length(unique(values)) != 1L) abort("Provenance values do not match across supplied tables")
}

finite_column <- function(values, name) {
  parsed <- suppressWarnings(as.numeric(values))
  bad <- !nzchar(values) | is.na(parsed) | !is.finite(parsed)
  if (any(bad)) abort(paste0(name, " must contain finite coordinates; invalid CSV lines: ", paste(which(bad) + 1L, collapse = ", ")))
  parsed
}

validate_coordinates <- function(table, group_column) {
  if (any(!nzchar(table$sample_id))) abort("sample_id cannot be empty")
  if (anyDuplicated(table$sample_id)) abort("sample_id values must be unique")
  x <- finite_column(table$axis1, "axis1")
  y <- finite_column(table$axis2, "axis2")
  if (length(x) < 3L) abort("At least 3 coordinate rows are required")
  if (diff(range(x)) == 0 || diff(range(y)) == 0) abort("axis1 and axis2 must each vary")
  groups <- NULL
  if (!is.null(group_column)) {
    if (!group_column %in% names(table)) abort(paste0("Input is missing group column '", group_column, "'"))
    groups <- table[[group_column]]
    if (any(!nzchar(groups))) abort("The selected group column cannot contain missing/empty values")
    levels <- unique(groups)
    if (length(levels) > MAX_GROUPS) abort(paste0("The group column exceeds ", MAX_GROUPS, " levels"))
    counts <- table(groups)
    if (any(counts < 2L)) abort(paste0("Every group needs at least 2 samples; too small: ", paste(names(counts)[counts < 2L], collapse = ", ")))
  }
  list(x = x, y = y, groups = groups)
}

validate_axis_metadata <- function(table) {
  if (nrow(table) != 2L) abort("axis metadata must contain exactly 2 rows")
  if (anyDuplicated(table$axis_key)) abort("axis metadata has duplicate axis_key values")
  if (!setequal(table$axis_key, c("axis1", "axis2"))) abort("axis metadata must contain axis1 and axis2 exactly once")
  if (any(!nzchar(table$axis_label))) abort("axis metadata has an empty axis_label")
  variance <- suppressWarnings(as.numeric(table$explained_variance))
  if (any(is.na(variance) | !is.finite(variance) | variance < 0 | variance > 1)) abort("explained_variance must contain finite 0-1 proportions")
  names(variance) <- table$axis_key
  if (sum(variance) > 1.000001) abort("axis1 + axis2 explained_variance cannot exceed 1")
  labels <- setNames(table$axis_label, table$axis_key)
  c(axis1 = sprintf("%s (%.1f%%)", labels[["axis1"]], 100 * variance[["axis1"]]),
    axis2 = sprintf("%s (%.1f%%)", labels[["axis2"]], 100 * variance[["axis2"]]))
}

validate_annotations <- function(table) {
  if (nrow(table) > MAX_ANNOTATIONS) abort(paste0("At most ", MAX_ANNOTATIONS, " supplied annotations are allowed"))
  if (any(!nzchar(table$annotation_id))) abort("supplied annotations has an empty annotation_id")
  if (anyDuplicated(table$annotation_id)) abort("supplied annotation IDs must be unique")
  if (any(!nzchar(table$annotation_text)) || any(!nzchar(table$source_label))) abort("supplied annotations require non-empty text and source")
  if (any(nchar(table$annotation_text, type = "chars") > MAX_ANNOTATION_LENGTH)) abort(paste0("Each supplied annotation is limited to ", MAX_ANNOTATION_LENGTH, " characters"))
  paste0("SUPPLIED — ", table$source_label, ": ", table$annotation_text)
}

expanded_limits <- function(x, y) {
  span <- max(diff(range(x)), diff(range(y))) * 1.14
  x_mid <- mean(range(x))
  y_mid <- mean(range(y))
  list(x = c(x_mid - span / 2, x_mid + span / 2), y = c(y_mid - span / 2, y_mid + span / 2))
}

draw_ordination <- function(x, y, groups, axis_labels, annotations, title) {
  levels <- if (is.null(groups)) "All samples" else unique(groups)
  colors <- setNames(grDevices::hcl.colors(length(levels), "Dark 3"), levels)
  shapes <- setNames(POINT_SHAPES[seq_along(levels)], levels)
  limits <- expanded_limits(x, y)
  wrapped <- unlist(lapply(annotations, function(item) strwrap(item, width = 110, exdent = 2L)), use.names = FALSE)
  outer_bottom <- 2.8 + 0.75 * length(wrapped)
  layout(matrix(c(2, 0, 1, 3), nrow = 2L, byrow = TRUE), widths = c(4.8, 1.65), heights = c(max(1.45, 0.55 + 0.24 * length(levels)), 4.6))
  par(oma = c(outer_bottom, 0.5, 4.0, 0.5))

  par(mar = c(4.2, 4.5, 0.8, 0.8))
  plot.new()
  panel_inches <- par("pin")
  base_x_span <- diff(limits$x)
  base_y_span <- diff(limits$y)
  x_span <- max(base_x_span, base_y_span * panel_inches[1L] / panel_inches[2L])
  y_span <- max(base_y_span, base_x_span * panel_inches[2L] / panel_inches[1L])
  x_mid <- mean(limits$x)
  y_mid <- mean(limits$y)
  limits$x <- c(x_mid - x_span / 2, x_mid + x_span / 2)
  limits$y <- c(y_mid - y_span / 2, y_mid + y_span / 2)
  plot.window(xlim = limits$x, ylim = limits$y, asp = 1, xaxs = "i", yaxs = "i")
  axis(1)
  axis(2)
  box(bty = "l")
  title(xlab = axis_labels[[1L]], ylab = axis_labels[[2L]])
  grid(col = "#E5E7EB", lty = 1)
  if (limits$x[1L] <= 0 && limits$x[2L] >= 0) abline(v = 0, col = "#9CA3AF", lty = 2)
  if (limits$y[1L] <= 0 && limits$y[2L] >= 0) abline(h = 0, col = "#9CA3AF", lty = 2)
  if (is.null(groups)) {
    points(x, y, pch = shapes[[1L]], bg = grDevices::adjustcolor(colors[[1L]], alpha.f = 0.84), col = "white", cex = 1.05, lwd = 0.65)
  } else {
    for (level in levels) {
      selected <- groups == level
      points(x[selected], y[selected], pch = shapes[[level]], bg = grDevices::adjustcolor(colors[[level]], alpha.f = 0.84),
             col = if (shapes[[level]] %in% 21:25) "white" else colors[[level]], cex = 1.05, lwd = 0.65)
    }
    legend("topright", legend = levels, pch = shapes, pt.bg = colors, col = colors,
           bty = "o", bg = grDevices::adjustcolor("white", alpha.f = 0.9), cex = 0.78, ncol = if (length(levels) > 6L) 2L else 1L)
  }

  if (is.null(groups)) {
    par(mar = c(0.8, 4.5, 2.0, 0.8))
    hist(x, breaks = "FD", col = grDevices::adjustcolor(colors[[1L]], alpha.f = 0.62), border = "white",
         main = "Axis 1 distribution", xlab = "", xlim = limits$x, axes = FALSE)
    axis(2, cex.axis = 0.7)
  } else {
    par(mar = c(0.8, min(13, 4.0 + max(nchar(levels, type = "width")) / 4), 2.0, 0.8))
    split_x <- split(x, factor(groups, levels = levels))
    boxplot(split_x, horizontal = TRUE, col = grDevices::adjustcolor(colors, alpha.f = 0.62), border = colors,
            outline = FALSE, axes = FALSE, xlim = limits$x, main = "Axis 1 distribution by group")
    axis(2, at = seq_along(levels), labels = levels, las = 1, tick = FALSE, cex.axis = 0.72)
  }

  if (is.null(groups)) {
    par(mar = c(4.2, 0.8, 0.8, 1.2))
    histogram <- hist(y, breaks = "FD", plot = FALSE)
    plot(NA, xlim = c(0, max(histogram$counts) * 1.08), ylim = limits$y,
         xlab = "", ylab = "", axes = FALSE, bty = "n", main = "Axis 2")
    rect(0, histogram$breaks[-length(histogram$breaks)], histogram$counts,
         histogram$breaks[-1L], col = grDevices::adjustcolor(colors[[1L]], alpha.f = 0.62), border = "white")
    axis(1, cex.axis = 0.7)
  } else {
    par(mar = c(4.2, 0.8, 2.0, 1.2))
    split_y <- split(y, factor(groups, levels = levels))
    boxplot(split_y, col = grDevices::adjustcolor(colors, alpha.f = 0.62), border = colors,
            outline = FALSE, axes = FALSE, ylim = limits$y, main = "Axis 2")
    axis(1, at = seq_along(levels), labels = FALSE, tick = FALSE)
  }

  mtext(title, side = 3, outer = TRUE, line = 2.35, font = 2, cex = 1.25)
  mtext(sprintf("Precomputed coordinates supplied; n = %d; groups = %d", length(x), if (is.null(groups)) 0L else length(levels)),
        side = 3, outer = TRUE, line = 0.9, cex = 0.8, col = "#374151")
  mtext("Plotting only: no ordination, PERMANOVA, or statistical conclusion was computed or verified.",
        side = 1, outer = TRUE, line = 0.65, cex = 0.72, col = "#4B5563")
  if (length(wrapped)) {
    for (index in seq_along(wrapped)) {
      mtext(wrapped[[index]], side = 1, outer = TRUE, line = 0.65 + 0.75 * index,
            adj = 0.08, cex = 0.68, col = "#7C2D12")
    }
  }
}

main <- function() {
  options <- parse_cli(commandArgs(trailingOnly = TRUE))
  coordinates <- read_table(options$input, "coordinates", c("sample_id", "axis1", "axis2"))
  tables <- list(coordinates = coordinates)
  axis_labels <- c("Axis 1", "Axis 2")
  if (!is.null(options$axis_metadata)) {
    axis_metadata <- read_table(options$axis_metadata, "axis metadata", c("axis_key", "axis_label", "explained_variance"))
    tables[["axis metadata"]] <- axis_metadata
    axis_labels <- validate_axis_metadata(axis_metadata)
  }
  annotations <- character()
  if (!is.null(options$supplied_annotations)) {
    annotation_table <- read_table(options$supplied_annotations, "supplied annotations", c("annotation_id", "annotation_text", "source_label"))
    tables[["supplied annotations"]] <- annotation_table
    annotations <- validate_annotations(annotation_table)
  }
  validate_provenance(tables)
  prepared <- validate_coordinates(coordinates, options$group_column)
  levels <- if (is.null(prepared$groups)) character() else unique(prepared$groups)
  wrapped_count <- sum(vapply(annotations, function(item) length(strwrap(item, width = 110, exdent = 2L)), integer(1)))
  width <- max(10, 10.2 + 0.035 * max(c(0, nchar(levels, type = "width"))))
  height <- 8.3 + 0.18 * max(0, length(levels) - 3L) + 0.24 * wrapped_count
  parent <- dirname(options$output_prefix)
  if (!dir.exists(parent) && !dir.create(parent, recursive = TRUE, showWarnings = FALSE)) abort(paste0("Cannot create output directory: ", parent))
  png_path <- paste0(options$output_prefix, ".png")
  pdf_path <- paste0(options$output_prefix, ".pdf")
  png(png_path, width = width, height = height, units = "in", res = options$dpi, bg = "white")
  tryCatch(draw_ordination(prepared$x, prepared$y, prepared$groups, axis_labels, annotations, options$title), finally = dev.off())
  cairo_pdf(pdf_path, width = width, height = height, bg = "white", onefile = TRUE)
  tryCatch(draw_ordination(prepared$x, prepared$y, prepared$groups, axis_labels, annotations, options$title), finally = dev.off())
  cat(sprintf("Validated %d unique samples; missing coordinates: 0; group levels: %d.\n", length(prepared$x), length(levels)))
  cat("Coordinates were treated as precomputed; ordination and statistical tests computed: 0.\n")
  cat(sprintf("Axis metadata supplied: %s; supplied annotations displayed: %d (not statistically verified).\n",
              if (is.null(options$axis_metadata)) "no" else "yes", length(annotations)))
  cat("Wrote ", png_path, "\n", sep = "")
  cat("Wrote ", pdf_path, "\n", sep = "")
}

tryCatch(main(), error = function(error) {
  message("ERROR: ", conditionMessage(error))
  quit(status = 2L)
})
