#!/usr/bin/env Rscript

# Render a strictly validated subject timeline as PNG and PDF using base R.

PAGE_LIMIT <- 36L
ALLOWED_MARKERS <- c(circle = 21L, diamond = 23L, triangle = 24L, square = 22L, cross = 4L)

abort <- function(message) {
  stop(message, call. = FALSE)
}

script_args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", script_args, value = TRUE)
if (length(file_arg) != 1L) abort("Cannot determine plot.R location")
script_dir <- dirname(normalizePath(sub("^--file=", "", file_arg), mustWork = TRUE))
template_root <- dirname(script_dir)
data_dir <- file.path(template_root, "data")

usage <- paste(
  "Usage: Rscript r/plot.R --output-prefix=PATH [options]",
  "Options: --subjects --intervals --events --interval-styles --event-styles --title --dpi",
  sep = "\n"
)

parse_cli <- function(args) {
  options <- list(
    subjects = file.path(data_dir, "simulated_fixed_seed_subjects.csv"),
    intervals = file.path(data_dir, "simulated_fixed_seed_intervals.csv"),
    events = NULL,
    interval_styles = file.path(data_dir, "interval_types.csv"),
    event_styles = NULL,
    output_prefix = NULL,
    title = "Subject timelines",
    dpi = "320"
  )
  aliases <- c(
    subjects = "subjects", intervals = "intervals", events = "events",
    `interval-styles` = "interval_styles", `event-styles` = "event_styles",
    `output-prefix` = "output_prefix", title = "title", dpi = "dpi"
  )
  index <- 1L
  while (index <= length(args)) {
    token <- args[[index]]
    if (token %in% c("--help", "-h")) {
      cat(usage, "\n")
      quit(status = 0L)
    }
    if (!startsWith(token, "--")) abort(paste0("Unexpected argument: ", token, "\n", usage))
    body <- substring(token, 3L)
    equals <- regexpr("=", body, fixed = TRUE)[1L]
    if (equals > 0L) {
      key <- substring(body, 1L, equals - 1L)
      value <- substring(body, equals + 1L)
    } else {
      key <- body
      index <- index + 1L
      if (index > length(args) || startsWith(args[[index]], "--")) {
        abort(paste0("Missing value for --", key))
      }
      value <- args[[index]]
    }
    if (!key %in% names(aliases)) abort(paste0("Unknown option --", key, "\n", usage))
    if (!nzchar(value)) abort(paste0("Empty value for --", key))
    options[[aliases[[key]]]] <- value
    index <- index + 1L
  }
  if (is.null(options$output_prefix)) abort("--output-prefix is required")
  if (xor(is.null(options$events), is.null(options$event_styles))) {
    abort("--events and --event-styles must be supplied together or both omitted")
  }
  if (grepl("\\.(png|svg|pdf)$", options$output_prefix, ignore.case = TRUE)) {
    abort("--output-prefix must not include .png, .svg, or .pdf")
  }
  if (!grepl("^[0-9]+$", options$dpi)) abort("--dpi must be an integer from 300 to 1200")
  options$dpi <- as.integer(options$dpi)
  if (is.na(options$dpi) || options$dpi < 300L || options$dpi > 1200L) {
    abort("--dpi must be an integer from 300 to 1200")
  }
  options
}

read_table <- function(path, name, required, allow_empty = FALSE) {
  if (!file.exists(path) || dir.exists(path)) abort(paste0(name, " file not found: ", path))
  table <- tryCatch(
    read.csv(
      path, stringsAsFactors = FALSE, check.names = FALSE,
      colClasses = "character", na.strings = character(), strip.white = FALSE
    ),
    error = function(error) abort(paste0("Cannot read ", name, " as CSV: ", conditionMessage(error)))
  )
  headers <- names(table)
  if (any(!nzchar(trimws(headers)))) abort(paste0(name, " contains an empty column name"))
  if (anyDuplicated(headers)) abort(paste0(name, " contains duplicate column names"))
  missing <- setdiff(required, headers)
  if (length(missing)) abort(paste0(name, " is missing required columns: ", paste(missing, collapse = ", ")))
  if (!nrow(table) && !allow_empty) abort(paste0(name, " must contain at least one data row"))
  for (column in headers) table[[column]] <- trimws(table[[column]])
  attr(table, "source_headers") <- headers
  table
}

finite_numeric <- function(values, context) {
  parsed <- suppressWarnings(as.numeric(values))
  bad <- is.na(parsed) | !is.finite(parsed)
  if (any(bad)) {
    rows <- paste(which(bad) + 1L, collapse = ", ")
    abort(paste0(context, " must be finite numeric values; invalid CSV lines: ", rows))
  }
  parsed
}

check_metadata <- function(named_tables) {
  declarations <- list()
  for (name in names(named_tables)) {
    table <- named_tables[[name]]
    headers <- attr(table, "source_headers")
    has_status <- "data_status" %in% headers
    has_seed <- "simulation_seed" %in% headers
    if (xor(has_status, has_seed)) {
      abort(paste0(name, " must provide data_status and simulation_seed together"))
    }
    if (!has_status || !nrow(table)) next
    if (any(!nzchar(table$data_status)) || any(!nzchar(table$simulation_seed))) {
      abort(paste0(name, " has empty simulation provenance values"))
    }
    pairs <- unique(paste(table$data_status, table$simulation_seed, sep = "\r"))
    if (length(pairs) != 1L) abort(paste0(name, " has inconsistent simulation provenance values"))
    declarations[[name]] <- pairs[[1L]]
  }
  if (length(declarations) > 1L && length(unique(unlist(declarations))) != 1L) {
    abort("Simulation provenance values do not match across supplied core tables")
  }
}

validate_styles <- function(table, type_col, label_col, name) {
  if (any(!nzchar(table[[type_col]]))) abort(paste0(name, " has an empty ", type_col))
  if (anyDuplicated(table[[type_col]])) abort(paste0(name, " has duplicate type identifiers"))
  if (any(!nzchar(table[[label_col]]))) abort(paste0(name, " has an empty legend label"))
  if (any(!grepl("^#[0-9A-Fa-f]{6}$", table$color))) {
    abort(paste0(name, " colors must use exact #RRGGBB notation"))
  }
  table
}

validate_subjects <- function(subjects) {
  if (any(!nzchar(subjects$subject_id))) abort("subjects has an empty subject_id")
  if (anyDuplicated(subjects$subject_id)) abort("subjects has duplicate subject_id values")
  if (any(!nzchar(subjects$subject_label))) abort("subjects has an empty subject_label")
  if (any(!grepl("^[0-9]+$", subjects$display_order))) {
    abort("subjects display_order values must be positive integers")
  }
  subjects$display_order_num <- suppressWarnings(as.integer(subjects$display_order))
  if (any(is.na(subjects$display_order_num)) || any(subjects$display_order_num < 1L)) {
    abort("subjects display_order values must be positive integers")
  }
  if (anyDuplicated(subjects$display_order_num)) abort("subjects has duplicate display_order values")
  subjects$observation_start_num <- finite_numeric(subjects$observation_start, "subjects observation_start")
  subjects$observation_end_num <- finite_numeric(subjects$observation_end, "subjects observation_end")
  if (any(subjects$observation_start_num >= subjects$observation_end_num)) {
    abort("Every subject requires observation_start < observation_end")
  }
  if (any(!nzchar(subjects$time_unit))) abort("subjects has an empty time_unit")
  units <- unique(subjects$time_unit)
  if (length(units) != 1L) {
    abort(paste0("subjects must use exactly one time_unit; found: ", paste(units, collapse = ", ")))
  }
  subjects[order(subjects$display_order_num), , drop = FALSE]
}

validate_intervals <- function(intervals, subjects, styles, unit) {
  if (any(!nzchar(intervals$interval_id))) abort("intervals has an empty interval_id")
  if (anyDuplicated(intervals$interval_id)) abort("intervals has duplicate interval_id values")
  if (any(!nzchar(intervals$subject_id))) abort("intervals has an empty subject_id")
  unknown_subjects <- setdiff(unique(intervals$subject_id), subjects$subject_id)
  if (length(unknown_subjects)) {
    abort(paste0("intervals references unknown subject_id values: ", paste(unknown_subjects, collapse = ", ")))
  }
  unknown_types <- setdiff(unique(intervals$interval_type), styles$interval_type)
  if (length(unknown_types)) {
    abort(paste0("intervals uses unknown interval_type values: ", paste(unknown_types, collapse = ", ")))
  }
  if (any(intervals$time_unit != unit)) abort("intervals time_unit values must exactly match subjects")
  intervals$start_num <- finite_numeric(intervals$start, "intervals start")
  intervals$end_num <- finite_numeric(intervals$end, "intervals end")
  if (any(intervals$start_num >= intervals$end_num)) abort("Every interval requires start < end")
  subject_index <- match(intervals$subject_id, subjects$subject_id)
  outside <- intervals$start_num < subjects$observation_start_num[subject_index] |
    intervals$end_num > subjects$observation_end_num[subject_index]
  if (any(outside)) {
    abort(paste0("intervals outside subject observation bounds at CSV lines: ", paste(which(outside) + 1L, collapse = ", ")))
  }
  for (subject_id in subjects$subject_id) {
    rows <- which(intervals$subject_id == subject_id)
    if (!length(rows)) abort(paste0("subject ", subject_id, " has no interval row"))
    if (length(rows) > 1L) {
      if (any(diff(intervals$start_num[rows]) < 0)) {
        abort(paste0("interval rows are out of start-time order for subject ", subject_id))
      }
      if (any(intervals$start_num[rows[-1L]] < intervals$end_num[rows[-length(rows)]])) {
        abort(paste0("interval rows overlap for subject ", subject_id))
      }
    }
  }
  intervals
}

validate_events <- function(events, subjects, styles, unit) {
  if (!nrow(events)) return(events)
  if (any(!nzchar(events$event_id))) abort("events has an empty event_id")
  if (anyDuplicated(events$event_id)) abort("events has duplicate event_id values")
  if (any(!nzchar(events$subject_id))) abort("events has an empty subject_id")
  unknown_subjects <- setdiff(unique(events$subject_id), subjects$subject_id)
  if (length(unknown_subjects)) {
    abort(paste0("events references unknown subject_id values: ", paste(unknown_subjects, collapse = ", ")))
  }
  unknown_types <- setdiff(unique(events$event_type), styles$event_type)
  if (length(unknown_types)) {
    abort(paste0(
      "events uses unknown event_type values (no fallback mapping is allowed): ",
      paste(unknown_types, collapse = ", ")
    ))
  }
  if (any(events$time_unit != unit)) abort("events time_unit values must exactly match subjects")
  events$time_num <- finite_numeric(events$time, "events time")
  subject_index <- match(events$subject_id, subjects$subject_id)
  outside <- events$time_num < subjects$observation_start_num[subject_index] |
    events$time_num > subjects$observation_end_num[subject_index]
  if (any(outside)) {
    abort(paste0("events outside subject observation bounds at CSV lines: ", paste(which(outside) + 1L, collapse = ", ")))
  }
  for (subject_id in subjects$subject_id) {
    rows <- which(events$subject_id == subject_id)
    if (length(rows) > 1L && any(diff(events$time_num[rows]) < 0)) {
      abort(paste0("event rows are out of time order for subject ", subject_id))
    }
  }
  events
}

draw_timeline <- function(subjects, intervals, events, interval_styles, event_styles, unit, title) {
  count <- nrow(subjects)
  y <- rev(seq_len(count))
  names(y) <- subjects$subject_id
  labels <- paste0(subjects$subject_label, " [", subjects$subject_id, "]")
  x_min <- min(subjects$observation_start_num)
  x_max <- max(subjects$observation_end_num)
  padding <- max((x_max - x_min) * 0.025, 0.1)
  x_limits <- c(x_min - padding, x_max + padding)

  op <- par(no.readonly = TRUE)
  on.exit(par(op), add = TRUE)
  max_label <- max(nchar(labels, type = "width"))
  legend_count <- nrow(interval_styles) + nrow(event_styles)
  legend_columns <- min(4L, max(1L, legend_count))
  legend_rows <- ceiling(max(1L, legend_count) / legend_columns)
  left_margin <- min(22, max(10, 7 + max_label / 5))
  par(mar = c(5.3, left_margin, 4.6 + 0.7 * legend_rows, 1.4), xaxs = "i", yaxs = "i")
  plot(
    NA, xlim = x_limits, ylim = c(0.35, count + 1.3 + 0.35 * legend_rows),
    axes = FALSE, xlab = "", ylab = "", bty = "n"
  )

  for (index in seq_len(count)) {
    row_y <- y[[subjects$subject_id[[index]]]]
    if (index %% 2L == 1L) rect(x_limits[1L], row_y - 0.48, x_limits[2L], row_y + 0.48, col = "#F5F6F7", border = NA)
    segments(subjects$observation_start_num[index], row_y, subjects$observation_end_num[index], row_y, col = "#6B7280", lwd = 1.2)
    segments(c(subjects$observation_start_num[index], subjects$observation_end_num[index]), row_y - 0.10,
             c(subjects$observation_start_num[index], subjects$observation_end_num[index]), row_y + 0.10,
             col = "#6B7280", lwd = 1)
  }
  interval_colors <- setNames(interval_styles$color, interval_styles$interval_type)
  for (index in seq_len(nrow(intervals))) {
    row_y <- y[[intervals$subject_id[[index]]]]
    rect(
      intervals$start_num[index], row_y - 0.28, intervals$end_num[index], row_y + 0.28,
      col = interval_colors[[intervals$interval_type[[index]]]], border = "white", lwd = 0.6
    )
  }
  if (nrow(events)) {
    event_colors <- setNames(event_styles$color, event_styles$event_type)
    event_pch <- setNames(ALLOWED_MARKERS[event_styles$marker], event_styles$event_type)
    for (index in seq_len(nrow(events))) {
      event_type <- events$event_type[[index]]
      point_code <- event_pch[[event_type]]
      point_color <- event_colors[[event_type]]
      if (point_code == 4L) {
        points(events$time_num[index], y[[events$subject_id[[index]]]], pch = point_code, col = point_color, cex = 1.05, lwd = 1.6)
      } else {
        points(events$time_num[index], y[[events$subject_id[[index]]]], pch = point_code, bg = point_color, col = "white", cex = 1.05, lwd = 0.8)
      }
    }
  }

  abline(v = pretty(c(x_min, x_max), n = 9L), col = "#D1D5DB", lwd = 0.7)
  # Redraw data over grid so marks remain foregrounded.
  for (index in seq_len(nrow(intervals))) {
    row_y <- y[[intervals$subject_id[[index]]]]
    rect(intervals$start_num[index], row_y - 0.28, intervals$end_num[index], row_y + 0.28,
         col = interval_colors[[intervals$interval_type[[index]]]], border = "white", lwd = 0.6)
  }
  if (nrow(events)) {
    for (index in seq_len(nrow(events))) {
      event_type <- events$event_type[[index]]
      point_code <- event_pch[[event_type]]
      point_color <- event_colors[[event_type]]
      if (point_code == 4L) {
        points(events$time_num[index], y[[events$subject_id[[index]]]], pch = point_code, col = point_color, cex = 1.05, lwd = 1.6)
      } else {
        points(events$time_num[index], y[[events$subject_id[[index]]]], pch = point_code, bg = point_color, col = "white", cex = 1.05, lwd = 0.8)
      }
    }
  }
  axis(1, at = pretty(c(x_min, x_max), n = 9L), col = "#4B5563", col.axis = "#374151")
  axis(2, at = y, labels = labels, las = 1, tick = FALSE, line = -0.4, cex.axis = 0.88)
  mtext(paste0("Time (", unit, ")"), side = 1, line = 2.3, cex = 0.95)
  mtext("Chronological display only; temporal order does not establish causality.", side = 1, line = 4.0, cex = 0.72, col = "#4B5563")
  title(main = title, line = 3.5, font.main = 2, cex.main = 1.25)

  legend_labels <- c(interval_styles$interval_type_label, event_styles$event_type_label)
  legend_pch <- c(rep(15L, nrow(interval_styles)), if (nrow(event_styles)) unname(ALLOWED_MARKERS[event_styles$marker]) else integer())
  legend_colors <- c(interval_styles$color, event_styles$color)
  legend_bg <- c(interval_styles$color, event_styles$color)
  legend(
    "top", inset = c(0, -0.015), legend = legend_labels, pch = legend_pch,
    col = legend_colors, pt.bg = legend_bg, pt.cex = 1.1, ncol = legend_columns,
    bty = "n", xpd = NA, cex = 0.82, text.col = "#1F2937"
  )
}

main <- function() {
  options <- parse_cli(commandArgs(trailingOnly = TRUE))
  subjects <- read_table(
    options$subjects, "subjects",
    c("subject_id", "subject_label", "display_order", "observation_start", "observation_end", "time_unit")
  )
  intervals <- read_table(
    options$intervals, "intervals",
    c("interval_id", "subject_id", "start", "end", "interval_type", "time_unit")
  )
  interval_styles <- read_table(
    options$interval_styles, "interval styles",
    c("interval_type", "interval_type_label", "color")
  )
  events <- data.frame()
  event_styles <- data.frame()
  metadata_tables <- list(subjects = subjects, intervals = intervals)
  if (!is.null(options$events)) {
    events <- read_table(
      options$events, "events",
      c("event_id", "subject_id", "time", "event_type", "time_unit"), allow_empty = TRUE
    )
    event_styles <- read_table(
      options$event_styles, "event styles",
      c("event_type", "event_type_label", "marker", "color")
    )
    metadata_tables$events <- events
  }
  check_metadata(metadata_tables)
  interval_styles <- validate_styles(interval_styles, "interval_type", "interval_type_label", "interval styles")
  if (nrow(event_styles)) {
    event_styles <- validate_styles(event_styles, "event_type", "event_type_label", "event styles")
    unknown_markers <- setdiff(unique(event_styles$marker), names(ALLOWED_MARKERS))
    if (length(unknown_markers)) {
      abort(paste0("event styles uses unsupported marker values: ", paste(unknown_markers, collapse = ", ")))
    }
  }
  subjects <- validate_subjects(subjects)
  if (nrow(subjects) > PAGE_LIMIT) {
    abort(paste0(
      "Single-page limit is ", PAGE_LIMIT, " subjects; received ", nrow(subjects),
      ". Split upstream into contiguous display_order batches or declared scientific groups, ",
      "then run each complete batch separately. Automatic pagination and truncation are disabled."
    ))
  }
  unit <- unique(subjects$time_unit)[[1L]]
  intervals <- validate_intervals(intervals, subjects, interval_styles, unit)
  events <- if (!is.null(options$events)) validate_events(events, subjects, event_styles, unit) else data.frame()

  labels <- paste0(subjects$subject_label, " [", subjects$subject_id, "]")
  legend_labels <- c(interval_styles$interval_type_label, event_styles$event_type_label)
  width <- min(17, max(10, 9 + 0.055 * max(nchar(labels, type = "width")) +
    0.025 * max(c(0, nchar(legend_labels, type = "width")))))
  legend_columns <- min(4L, max(1L, length(legend_labels)))
  legend_rows <- ceiling(max(1L, length(legend_labels)) / legend_columns)
  height <- max(5.4, 3.4 + 0.38 * nrow(subjects) + 0.35 * legend_rows)
  parent <- dirname(options$output_prefix)
  if (!dir.exists(parent) && !dir.create(parent, recursive = TRUE, showWarnings = FALSE)) {
    abort(paste0("Cannot create output directory: ", parent))
  }
  png_path <- paste0(options$output_prefix, ".png")
  pdf_path <- paste0(options$output_prefix, ".pdf")
  png(filename = png_path, width = width, height = height, units = "in", res = options$dpi, bg = "white")
  tryCatch(
    draw_timeline(subjects, intervals, events, interval_styles, event_styles, unit, options$title),
    finally = dev.off()
  )
  # Cairo preserves UTF-8 labels in the vector output on supported R builds.
  cairo_pdf(filename = pdf_path, width = width, height = height, bg = "white", onefile = TRUE)
  tryCatch(
    draw_timeline(subjects, intervals, events, interval_styles, event_styles, unit, options$title),
    finally = dev.off()
  )
  cat(sprintf("Validated %d subjects, %d intervals, and %d events; excluded rows: 0.\n", nrow(subjects), nrow(intervals), nrow(events)))
  cat(sprintf("Time unit: '%s'; single-page boundary: %d subjects (no automatic pagination).\n", unit, PAGE_LIMIT))
  cat("Wrote ", png_path, "\n", sep = "")
  cat("Wrote ", pdf_path, "\n", sep = "")
}

tryCatch(main(), error = function(error) {
  message("ERROR: ", conditionMessage(error))
  quit(status = 2L)
})
