#!/usr/bin/env Rscript

MAX_GROUPS <- 12L
MAX_SAMPLES <- 5000L
POINT_SHAPES <- c(21L, 22L, 24L, 23L, 25L, 7L, 8L, 0L, 2L, 5L, 6L, 1L)
abort <- function(message) stop(message, call. = FALSE)

script_args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", script_args, value = TRUE)
if (length(file_arg) != 1L) abort("Cannot determine plot.R location")
script_dir <- dirname(normalizePath(sub("^--file=", "", file_arg), mustWork = TRUE))
demo <- file.path(dirname(script_dir), "data", "simulated_fixed_seed_supplied_diagnostics.csv")

parse_cli <- function(args) {
  options <- list(input = demo, group_column = NULL, output_prefix = NULL,
                  title = "Supplied regression diagnostics", dpi = "320")
  aliases <- c(input = "input", `group-column` = "group_column", `output-prefix` = "output_prefix",
               title = "title", dpi = "dpi")
  index <- 1L
  while (index <= length(args)) {
    token <- args[[index]]
    if (!startsWith(token, "--")) abort(paste0("Unexpected argument: ", token))
    body <- substring(token, 3L); equals <- regexpr("=", body, fixed = TRUE)[1L]
    if (equals > 0L) {
      key <- substring(body, 1L, equals - 1L); value <- substring(body, equals + 1L)
    } else {
      key <- body; index <- index + 1L
      if (index > length(args) || startsWith(args[[index]], "--")) abort(paste0("Missing value for --", key))
      value <- args[[index]]
    }
    if (!key %in% names(aliases)) abort(paste0("Unknown option --", key))
    if (!nzchar(value)) abort(paste0("Empty value for --", key))
    options[[aliases[[key]]]] <- value; index <- index + 1L
  }
  if (is.null(options$output_prefix)) abort("--output-prefix is required")
  if (grepl("\\.(png|svg|pdf)$", options$output_prefix, ignore.case = TRUE)) abort("--output-prefix must not include an extension")
  if (!grepl("^[0-9]+$", options$dpi)) abort("--dpi must be an integer from 300 to 1200")
  options$dpi <- as.integer(options$dpi)
  if (is.na(options$dpi) || options$dpi < 300L || options$dpi > 1200L) abort("--dpi must be an integer from 300 to 1200")
  options
}

read_input <- function(path) {
  if (!file.exists(path) || dir.exists(path)) abort(paste0("Input file not found: ", path))
  table <- tryCatch(read.csv(path, stringsAsFactors = FALSE, check.names = FALSE, colClasses = "character",
                             na.strings = character(), strip.white = FALSE),
                    error = function(error) abort(paste0("Cannot read input: ", conditionMessage(error))))
  if (nrow(table) < 5L) abort("At least 5 samples are required")
  if (nrow(table) > MAX_SAMPLES) abort(paste0("At most ", MAX_SAMPLES, " samples can be rendered"))
  if (any(!nzchar(trimws(names(table)))) || anyDuplicated(names(table))) abort("Input has empty/duplicate column names")
  missing <- setdiff(c("sample_id", "x", "y", "fitted", "residual"), names(table))
  if (length(missing)) abort(paste0("Input is missing columns: ", paste(missing, collapse = ", ")))
  for (column in names(table)) table[[column]] <- trimws(table[[column]])
  table
}

finite_column <- function(values, name) {
  parsed <- suppressWarnings(as.numeric(values))
  bad <- !nzchar(values) | is.na(parsed) | !is.finite(parsed)
  if (any(bad)) abort(paste0(name, " must contain finite values; invalid CSV lines: ", paste(which(bad) + 1L, collapse = ", ")))
  parsed
}

validate_data <- function(table, group_column) {
  if (any(!nzchar(table$sample_id)) || anyDuplicated(table$sample_id)) abort("sample_id must be non-empty and unique")
  x <- finite_column(table$x, "x"); y <- finite_column(table$y, "y")
  fitted <- finite_column(table$fitted, "fitted"); residual <- finite_column(table$residual, "residual")
  for (item in list(x = x, y = y, fitted = fitted)) if (diff(range(item)) == 0) abort("x, y, and fitted must each vary")
  groups <- NULL
  if (!is.null(group_column)) {
    if (!group_column %in% names(table)) abort(paste0("Input is missing group column '", group_column, "'"))
    groups <- table[[group_column]]
    if (any(!nzchar(groups))) abort("The selected group column cannot contain empty values")
    levels <- unique(groups)
    if (length(levels) > MAX_GROUPS) abort(paste0("The group column exceeds ", MAX_GROUPS, " levels"))
    counts <- table(groups)
    if (any(counts < 2L)) abort("Every group needs at least 2 samples")
  }
  has_status <- "data_status" %in% names(table); has_seed <- "simulation_seed" %in% names(table)
  if (xor(has_status, has_seed)) abort("data_status and simulation_seed must be supplied together")
  if (has_status) {
    provenance <- unique(paste(table$data_status, table$simulation_seed, sep = "\r"))
    if (any(!nzchar(table$data_status)) || any(!nzchar(table$simulation_seed)) || length(provenance) != 1L) abort("Simulation provenance must be non-empty and consistent")
  }
  list(x = x, y = y, fitted = fitted, residual = residual, groups = groups)
}

draw_marginal <- function(values, groups, colors, title, x_label) {
  histogram <- hist(values, breaks = "FD", plot = FALSE)
  curves <- list()
  maximum <- max(histogram$density)
  if (!is.null(groups)) {
    for (level in unique(groups)) {
      selected <- values[groups == level]
      if (length(selected) >= 2L && diff(range(selected)) > 0) {
        curves[[level]] <- density(selected)
        maximum <- max(maximum, curves[[level]]$y)
      }
    }
  }
  plot(histogram, col = "#E5E7EB", border = "white", main = title, xlab = x_label,
       ylab = "Density", freq = FALSE, ylim = c(0, maximum * 1.06))
  for (level in names(curves)) lines(curves[[level]]$x, curves[[level]]$y, col = colors[[level]], lwd = 1.3)
}

draw_plot <- function(data, title) {
  x <- data$x; y <- data$y; fitted <- data$fitted; residual <- data$residual; groups <- data$groups
  levels <- if (is.null(groups)) "All samples" else unique(groups)
  colors <- setNames(grDevices::hcl.colors(length(levels), "Dark 3"), levels)
  shapes <- setNames(POINT_SHAPES[seq_along(levels)], levels)
  group_values <- if (is.null(groups)) rep("All samples", length(x)) else groups
  point_colors <- unname(colors[group_values]); point_shapes <- unname(shapes[group_values])
  layout(matrix(c(1, 2, 4, 1, 3, 4), nrow = 2L, byrow = TRUE), widths = c(4.2, 2.6, 4.2), heights = c(1, 1))
  par(oma = c(4.2, 0.5, 6.0, 0.5))

  par(mar = c(4.2, 4.2, 2.8, 0.8))
  plot(x, y, pch = point_shapes, bg = grDevices::adjustcolor(point_colors, alpha.f = 0.80),
       col = ifelse(point_shapes %in% 21:25, "white", point_colors), xlab = "Supplied x", ylab = "Supplied y / fitted",
       main = "A  Relationship", cex = 0.85)
  grid(col = "#E5E7EB")
  points(x, fitted, pch = 23, bg = NA, col = point_colors, cex = 0.75, lwd = 0.9)
  legend("topleft", legend = c("Supplied y", "Supplied fitted"), pch = c(21, 23), pt.bg = c("#6B7280", NA),
         col = c("white", "#374151"), bty = "n", cex = 0.72)
  if (!is.null(groups)) legend("bottomright", legend = levels, pch = shapes, pt.bg = colors, col = colors,
                               bty = "n", cex = 0.68, ncol = if (length(levels) > 6L) 2L else 1L)

  par(mar = c(3.8, 3.5, 2.8, 0.5))
  draw_marginal(x, groups, colors, "B  Marginal x", "Supplied x")
  par(mar = c(3.8, 3.5, 2.8, 0.5))
  draw_marginal(y, groups, colors, "Marginal y", "Supplied y")

  par(mar = c(4.2, 4.2, 2.8, 0.8))
  plot(fitted, residual, pch = point_shapes, bg = grDevices::adjustcolor(point_colors, alpha.f = 0.80),
       col = ifelse(point_shapes %in% 21:25, "white", point_colors), xlab = "Supplied fitted", ylab = "Supplied residual",
       main = "C  Residual diagnostic", cex = 0.85)
  grid(col = "#E5E7EB"); abline(h = 0, lty = 2, lwd = 1.0)

  mtext(title, side = 3, outer = TRUE, line = 4.2, font = 2, cex = 1.25)
  mtext("All fitted and residual values are supplied; this script fits no model and computes no P values.",
        side = 3, outer = TRUE, line = 2.4, cex = 0.78, col = "#374151")
  mtext("Descriptive visualization only; supplied residuals are not recomputed or statistically verified.",
        side = 1, outer = TRUE, line = 2.2, cex = 0.70, col = "#4B5563")
}

main <- function() {
  options <- parse_cli(commandArgs(trailingOnly = TRUE))
  table <- read_input(options$input); prepared <- validate_data(table, options$group_column)
  levels <- if (is.null(prepared$groups)) character() else unique(prepared$groups)
  width <- max(13.2, 12.8 + 0.04 * max(c(0, nchar(levels, type = "width"))))
  height <- 7.5 + 0.12 * max(0, length(levels) - 4L)
  parent <- dirname(options$output_prefix)
  if (!dir.exists(parent) && !dir.create(parent, recursive = TRUE, showWarnings = FALSE)) abort(paste0("Cannot create output directory: ", parent))
  png_path <- paste0(options$output_prefix, ".png"); pdf_path <- paste0(options$output_prefix, ".pdf")
  png(png_path, width = width, height = height, units = "in", res = options$dpi, bg = "white")
  tryCatch(draw_plot(prepared, options$title), finally = dev.off())
  cairo_pdf(pdf_path, width = width, height = height, bg = "white", onefile = TRUE)
  tryCatch(draw_plot(prepared, options$title), finally = dev.off())
  cat(sprintf("Validated %d unique samples; missing diagnostic values: 0; group levels: %d.\n", nrow(table), length(levels)))
  cat("Supplied fields plotted: x, y, fitted, residual. Models fitted: 0; P values computed: 0.\n")
  cat("Residuals recomputed or statistically verified: no.\n")
  cat("Wrote ", png_path, "\n", sep = ""); cat("Wrote ", pdf_path, "\n", sep = "")
}

tryCatch(main(), error = function(error) { message("ERROR: ", conditionMessage(error)); quit(status = 2L) })
