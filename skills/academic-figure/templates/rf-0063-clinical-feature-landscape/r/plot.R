#!/usr/bin/env Rscript

MAX_SAMPLES <- 60L
MAX_FEATURES <- 16L
abort <- function(message) stop(message, call. = FALSE)

script_args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", script_args, value = TRUE)
if (length(file_arg) != 1L) abort("Cannot determine plot.R location")
script_dir <- dirname(normalizePath(sub("^--file=", "", file_arg), mustWork = TRUE))
data_dir <- file.path(dirname(script_dir), "data")

parse_cli <- function(args) {
  options <- list(samples = file.path(data_dir, "simulated_fixed_seed_samples.csv"),
                  feature_spec = file.path(data_dir, "simulated_fixed_seed_feature_spec.csv"),
                  output_prefix = NULL, title = "Mixed feature landscape", dpi = "320")
  aliases <- c(samples = "samples", `feature-spec` = "feature_spec", `output-prefix` = "output_prefix",
               title = "title", dpi = "dpi")
  index <- 1L
  while (index <= length(args)) {
    token <- args[[index]]
    if (!startsWith(token, "--")) abort(paste0("Unexpected argument: ", token))
    body <- substring(token, 3L)
    equals <- regexpr("=", body, fixed = TRUE)[1L]
    if (equals > 0L) {
      key <- substring(body, 1L, equals - 1L); value <- substring(body, equals + 1L)
    } else {
      key <- body; index <- index + 1L
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
  table <- tryCatch(read.csv(path, stringsAsFactors = FALSE, check.names = FALSE, colClasses = "character",
                             na.strings = character(), strip.white = FALSE),
                    error = function(error) abort(paste0("Cannot read ", name, ": ", conditionMessage(error))))
  if (!nrow(table)) abort(paste0(name, " must contain at least one row"))
  if (any(!nzchar(trimws(names(table)))) || anyDuplicated(names(table))) abort(paste0(name, " has empty/duplicate column names"))
  missing <- setdiff(required, names(table))
  if (length(missing)) abort(paste0(name, " is missing columns: ", paste(missing, collapse = ", ")))
  for (column in names(table)) table[[column]] <- trimws(table[[column]])
  attr(table, "source_headers") <- names(table)
  table
}

provenance <- function(table, name) {
  headers <- attr(table, "source_headers")
  has_status <- "data_status" %in% headers; has_seed <- "simulation_seed" %in% headers
  if (xor(has_status, has_seed)) abort(paste0(name, " must provide data_status and simulation_seed together"))
  if (!has_status) return(NULL)
  values <- unique(paste(table$data_status, table$simulation_seed, sep = "\r"))
  if (any(!nzchar(table$data_status)) || any(!nzchar(table$simulation_seed)) || length(values) != 1L) abort(paste0(name, " provenance must be non-empty and consistent"))
  values[[1L]]
}

positive_integer <- function(values, context) {
  if (any(!grepl("^[0-9]+$", values))) abort(paste0(context, " must contain positive integers"))
  parsed <- suppressWarnings(as.integer(values))
  if (any(is.na(parsed) | parsed < 1L)) abort(paste0(context, " must contain positive integers"))
  parsed
}

split_pipe <- function(value, context) {
  items <- trimws(strsplit(value, "|", fixed = TRUE)[[1L]])
  if (any(!nzchar(items)) || anyDuplicated(items)) abort(paste0(context, " contains empty/duplicate items"))
  items
}

validate_specs <- function(table) {
  if (nrow(table) > MAX_FEATURES) abort(paste0("At most ", MAX_FEATURES, " features can be rendered"))
  if (any(!nzchar(table$feature_id)) || anyDuplicated(table$feature_id)) abort("feature_id must be non-empty and unique")
  if (any(!nzchar(table$feature_label))) abort("feature_label cannot be empty")
  if (any(!table$feature_type %in% c("continuous", "categorical", "binary"))) abort("feature_type must be continuous, categorical, or binary")
  table$order_num <- positive_integer(table$display_order, "feature display_order")
  if (anyDuplicated(table$order_num)) abort("feature display_order must be unique")
  if (any(!nzchar(table$missing_label)) || any(!grepl("^#[0-9A-Fa-f]{6}$", table$missing_color))) abort("Every feature needs a missing label and #RRGGBB missing color")
  specs <- vector("list", nrow(table))
  for (index in seq_len(nrow(table))) {
    row <- table[index, , drop = FALSE]
    id <- row$feature_id
    colors <- split_pipe(row$colors, paste0(id, " colors"))
    if (any(!grepl("^#[0-9A-Fa-f]{6}$", colors))) abort(paste0(id, " colors must use #RRGGBB"))
    if (tolower(row$missing_color) %in% tolower(colors)) abort(paste0(id, " missing color must differ from observed colors"))
    levels <- character(); minimum <- maximum <- NA_real_
    if (row$feature_type == "continuous") {
      if (!nzchar(row$display_min) || !nzchar(row$display_max)) abort(paste0("continuous feature ", id, " requires display_min and display_max"))
      minimum <- suppressWarnings(as.numeric(row$display_min)); maximum <- suppressWarnings(as.numeric(row$display_max))
      if (!is.finite(minimum) || !is.finite(maximum) || minimum >= maximum) abort(paste0(id, " requires finite display_min < display_max"))
      if (nzchar(row$levels) || length(colors) != 2L) abort(paste0(id, " continuous spec requires empty levels and two colors"))
    } else {
      if (nzchar(row$display_min) || nzchar(row$display_max)) abort(paste0(id, " non-continuous spec must leave display bounds empty"))
      levels <- split_pipe(row$levels, paste0(id, " levels"))
      if (row$feature_type == "binary" && length(levels) != 2L) abort(paste0(id, " binary spec requires two levels"))
      if (row$feature_type == "categorical" && (length(levels) < 2L || length(levels) > 8L)) abort(paste0(id, " categorical spec requires 2-8 levels"))
      if (length(colors) != length(levels)) abort(paste0(id, " needs one color per level"))
    }
    specs[[index]] <- list(id = id, label = row$feature_label, type = row$feature_type,
                           order = row$order_num, minimum = minimum, maximum = maximum,
                           levels = levels, colors = colors, missing_label = row$missing_label,
                           missing_color = row$missing_color)
  }
  specs[order(vapply(specs, function(item) item$order, integer(1)))]
}

validate_samples <- function(table, specs) {
  if (nrow(table) > MAX_SAMPLES) abort(paste0("At most ", MAX_SAMPLES, " samples can be rendered"))
  feature_ids <- vapply(specs, function(item) item$id, character(1))
  missing <- setdiff(feature_ids, names(table))
  if (length(missing)) abort(paste0("samples is missing feature columns: ", paste(missing, collapse = ", ")))
  if (any(!nzchar(table$sample_id)) || anyDuplicated(table$sample_id)) abort("sample_id must be non-empty and unique")
  if (any(!nzchar(table$sample_label))) abort("sample_label cannot be empty")
  table$order_num <- positive_integer(table$display_order, "sample display_order")
  if (anyDuplicated(table$order_num)) abort("sample display_order must be unique")
  missing_count <- 0L
  for (spec in specs) {
    values <- table[[spec$id]]
    is_missing <- is.na(values) | values %in% c("", "NA")
    missing_count <- missing_count + sum(is_missing)
    observed <- values[!is_missing]
    if (spec$type == "continuous") {
      numeric_values <- suppressWarnings(as.numeric(observed))
      if (any(is.na(numeric_values) | !is.finite(numeric_values))) abort(paste0(spec$id, " contains invalid continuous values"))
      if (any(numeric_values < spec$minimum | numeric_values > spec$maximum)) abort(paste0(spec$id, " has values outside its explicit display domain"))
    } else if (any(!observed %in% spec$levels)) {
      abort(paste0(spec$id, " contains unknown levels: ", paste(unique(observed[!observed %in% spec$levels]), collapse = ", ")))
    }
  }
  table <- table[order(table$order_num), , drop = FALSE]
  list(table = table, missing_count = missing_count)
}

value_color <- function(value, spec) {
  if (is.na(value) || value %in% c("", "NA")) return(spec$missing_color)
  if (spec$type == "continuous") {
    palette <- grDevices::colorRampPalette(spec$colors)(256)
    fraction <- (as.numeric(value) - spec$minimum) / (spec$maximum - spec$minimum)
    return(palette[max(1L, min(256L, floor(fraction * 255) + 1L))])
  }
  setNames(spec$colors, spec$levels)[[value]]
}

draw_plot <- function(samples, specs, title) {
  count <- nrow(samples); feature_count <- length(specs)
  sample_labels <- paste0(samples$sample_label, " [", samples$sample_id, "]")
  layout(matrix(c(1, 2), nrow = 1L), widths = c(max(4, feature_count), 5.0))
  par(oma = c(4.0, 0.5, 5.0, 0.5))
  par(mar = c(2.0, min(19, 6 + max(nchar(sample_labels, type = "width")) / 3.5),
              min(14, 5 + max(nchar(vapply(specs, function(item) item$label, character(1)), type = "width")) / 4), 0.8))
  plot(NA, xlim = c(0.5, feature_count + 0.5), ylim = c(0.5, count + 0.5), axes = FALSE, xlab = "", ylab = "", xaxs = "i", yaxs = "i")
  y_positions <- rev(seq_len(count))
  for (row in seq_len(count)) {
    for (column in seq_along(specs)) {
      spec <- specs[[column]]; value <- samples[[spec$id]][row]
      missing <- is.na(value) || value %in% c("", "NA")
      rect(column - 0.5, y_positions[row] - 0.5, column + 0.5, y_positions[row] + 0.5,
           col = value_color(value, spec), border = "white", lwd = 0.8)
      if (missing) {
        segments(column - 0.42, y_positions[row] - 0.42, column + 0.42, y_positions[row] + 0.42, col = "#6B7280", lwd = 0.55)
        segments(column - 0.42, y_positions[row] + 0.42, column + 0.42, y_positions[row] - 0.42, col = "#6B7280", lwd = 0.55)
      }
    }
  }
  axis(2, at = y_positions, labels = sample_labels, las = 1, tick = FALSE, cex.axis = 0.72)
  axis(3, at = seq_along(specs), labels = vapply(specs, function(item) item$label, character(1)), las = 2, tick = FALSE, cex.axis = 0.72)
  box(col = "#9CA3AF")

  par(mar = c(2.0, 0.5, 2.0, 0.5))
  plot(NA, xlim = c(0, 1), ylim = c(0, feature_count + 1.35), axes = FALSE, xlab = "", ylab = "", bty = "n")
  for (index in seq_along(specs)) {
    spec <- specs[[index]]; y <- feature_count - index + 1.30
    text(0.01, y + 0.23, paste0(spec$label, " [", spec$type, "]"), adj = 0, font = 2, cex = 0.72)
    if (spec$type == "continuous") {
      palette <- grDevices::colorRampPalette(spec$colors)(24)
      for (step in seq_along(palette)) rect(0.04 + (step - 1) * 0.021, y - 0.10, 0.04 + step * 0.021, y + 0.09, col = palette[step], border = NA)
      text(0.04, y - 0.19, format(spec$minimum, trim = TRUE), adj = 0, cex = 0.62)
      text(0.544, y - 0.19, format(spec$maximum, trim = TRUE), adj = 1, cex = 0.62)
    } else {
      slot <- 0.90 / length(spec$levels)
      for (level_index in seq_along(spec$levels)) {
        x <- 0.03 + (level_index - 1) * slot
        rect(x, y - 0.10, x + 0.035, y + 0.09, col = spec$colors[level_index], border = "#4B5563", lwd = 0.4)
        text(x + 0.045, y, spec$levels[level_index], adj = 0, cex = 0.62)
      }
    }
  }
  missing_pairs <- unique(vapply(specs, function(item) paste(item$missing_label, item$missing_color, sep = "\r"), character(1)))
  text(0.01, 0.70, "Missing encoding", adj = 0, font = 2, cex = 0.72)
  for (index in seq_along(missing_pairs)) {
    fields <- strsplit(missing_pairs[index], "\r", fixed = TRUE)[[1L]]; x <- 0.04 + (index - 1) * 0.30
    rect(x, 0.26, x + 0.06, 0.46, col = fields[2L], border = "#4B5563")
    segments(x, 0.26, x + 0.06, 0.46, col = "#6B7280", lwd = 0.5)
    text(x + 0.075, 0.36, fields[1L], adj = 0, cex = 0.64)
  }
  mtext(title, side = 3, outer = TRUE, line = 3.2, font = 2, cex = 1.25)
  mtext("Feature types/scales supplied explicitly; sample order from input display_order.", side = 3, outer = TRUE, line = 1.6, cex = 0.78, col = "#374151")
  mtext("Missing is encoded separately and never treated as zero; no clustering or inference is performed.", side = 1, outer = TRUE, line = 2.1, cex = 0.70, col = "#4B5563")
}

main <- function() {
  options <- parse_cli(commandArgs(trailingOnly = TRUE))
  specs_table <- read_table(options$feature_spec, "feature spec", c("feature_id", "feature_label", "feature_type", "display_order", "display_min", "display_max", "levels", "colors", "missing_label", "missing_color"))
  samples_table <- read_table(options$samples, "samples", c("sample_id", "sample_label", "display_order"))
  spec_provenance <- provenance(specs_table, "feature spec"); sample_provenance <- provenance(samples_table, "samples")
  if (!is.null(spec_provenance) && !is.null(sample_provenance) && spec_provenance != sample_provenance) abort("samples and feature spec provenance do not match")
  specs <- validate_specs(specs_table)
  prepared <- validate_samples(samples_table, specs)
  samples <- prepared$table
  width <- max(12, 6.4 + 0.72 * length(specs) + 0.04 * (max(nchar(paste0(samples$sample_label, samples$sample_id), type = "width")) + max(nchar(vapply(specs, function(item) item$label, character(1)), type = "width"))))
  height <- max(7, 2.8 + 0.34 * nrow(samples))
  parent <- dirname(options$output_prefix)
  if (!dir.exists(parent) && !dir.create(parent, recursive = TRUE, showWarnings = FALSE)) abort(paste0("Cannot create output directory: ", parent))
  png_path <- paste0(options$output_prefix, ".png"); pdf_path <- paste0(options$output_prefix, ".pdf")
  png(png_path, width = width, height = height, units = "in", res = options$dpi, bg = "white")
  tryCatch(draw_plot(samples, specs, options$title), finally = dev.off())
  cairo_pdf(pdf_path, width = width, height = height, bg = "white", onefile = TRUE)
  tryCatch(draw_plot(samples, specs, options$title), finally = dev.off())
  types <- vapply(specs, function(item) item$type, character(1))
  cat(sprintf("Validated %d unique samples and %d features; missing cells: %d; invalid rows excluded: 0.\n", nrow(samples), length(specs), prepared$missing_count))
  cat(sprintf("Feature types: continuous=%d, categorical=%d, binary=%d.\n", sum(types == "continuous"), sum(types == "categorical"), sum(types == "binary")))
  cat("Sample order source: input display_order; clustering/reordering performed: no.\n")
  cat("Wrote ", png_path, "\n", sep = ""); cat("Wrote ", pdf_path, "\n", sep = "")
}

tryCatch(main(), error = function(error) { message("ERROR: ", conditionMessage(error)); quit(status = 2L) })
