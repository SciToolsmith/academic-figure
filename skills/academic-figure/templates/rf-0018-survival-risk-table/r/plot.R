#!/usr/bin/env Rscript

# Plot supplied survival step coordinates and supplied risk counts using base R.

all_args <- commandArgs(trailingOnly = FALSE)
file_arg <- sub("^--file=", "", all_args[grep("^--file=", all_args)])
script_dir <- if (length(file_arg)) dirname(normalizePath(file_arg[[1]], mustWork = TRUE)) else getwd()
template_dir <- dirname(script_dir)
demo_steps <- file.path(template_dir, "demo", "demo_survival_steps_seed18.csv")
demo_risk <- file.path(template_dir, "demo", "demo_risk_table_seed18.csv")
demo_annotations <- file.path(template_dir, "demo", "demo_annotations_seed18.csv")

defaults <- list(
  steps = "", risk = "", annotations = "",
  output_prefix = file.path(getwd(), "survival_supplied_r"),
  title = "Supplied survival step coordinates", x_label = "Time", dpi = 320L
)

parse_args <- function(args) {
  result <- defaults
  aliases <- c(steps = "steps", risk = "risk", annotations = "annotations", `output-prefix` = "output_prefix", title = "title", `x-label` = "x_label", dpi = "dpi")
  index <- 1L
  while (index <= length(args)) {
    token <- args[[index]]
    if (!startsWith(token, "--")) stop(sprintf("Unknown argument: %s", token), call. = FALSE)
    stripped <- substring(token, 3L)
    if (grepl("=", stripped, fixed = TRUE)) {
      pieces <- strsplit(stripped, "=", fixed = TRUE)[[1]]
      key <- pieces[[1]]; value <- paste(pieces[-1], collapse = "=")
    } else {
      key <- stripped; index <- index + 1L
      if (index > length(args)) stop(sprintf("Missing value for --%s", key), call. = FALSE)
      value <- args[[index]]
    }
    if (!key %in% names(aliases)) stop(sprintf("Unknown option: --%s", key), call. = FALSE)
    result[[aliases[[key]]]] <- value
    index <- index + 1L
  }
  if (xor(nzchar(result$steps), nzchar(result$risk))) stop("Provide --steps and --risk together.", call. = FALSE)
  if (!nzchar(result$steps)) {
    result$steps <- demo_steps; result$risk <- demo_risk
    if (!nzchar(result$annotations)) result$annotations <- demo_annotations
  }
  result$dpi <- suppressWarnings(as.integer(result$dpi))
  if (is.na(result$dpi) || result$dpi < 150L) stop("--dpi must be at least 150.", call. = FALSE)
  result
}

stop_contract <- function(message) stop(sprintf("Input validation failed: %s", message), call. = FALSE)
ordered_unique <- function(values) values[!duplicated(values)]

read_character_csv <- function(path, required, label) {
  if (!file.exists(path) || dir.exists(path)) stop_contract(sprintf("%s does not exist: %s", label, path))
  data <- tryCatch(
    utils::read.csv(path, stringsAsFactors = FALSE, check.names = FALSE, colClasses = "character", na.strings = character()),
    error = function(error) stop_contract(conditionMessage(error))
  )
  names(data) <- trimws(names(data))
  if (any(!nzchar(names(data))) || anyDuplicated(names(data))) stop_contract(sprintf("%s headers must be nonblank and unique.", label))
  missing <- setdiff(required, names(data))
  if (length(missing)) stop_contract(sprintf("%s is missing columns: %s", label, paste(missing, collapse = ", ")))
  if (nrow(data)) {
    keep <- apply(data, 1L, function(row) any(nzchar(trimws(row))))
    data <- data[keep, , drop = FALSE]
  }
  if (!nrow(data)) stop_contract(sprintf("%s contains no data rows.", label))
  data
}

finite_number <- function(text, field, row_number) {
  value <- trimws(text)
  if (!nzchar(value)) stop_contract(sprintf("Row %d: '%s' must not be blank.", row_number, field))
  number <- suppressWarnings(as.numeric(value))
  if (is.na(number) || !is.finite(number)) stop_contract(sprintf("Row %d: '%s' must be finite numeric.", row_number, field))
  number
}

metadata_columns <- function(data) {
  data$status <- if ("data_status" %in% names(data)) toupper(trimws(data$data_status)) else rep("", nrow(data))
  data$seed <- if ("simulation_seed" %in% names(data)) trimws(data$simulation_seed) else rep("", nrow(data))
  data
}

read_steps <- function(path) {
  data <- metadata_columns(read_character_csv(path, c("time", "estimate", "curve_id"), "Step CSV"))
  data$curve_id <- trimws(data$curve_id)
  data$time_num <- NA_real_; data$estimate_num <- NA_real_
  for (index in seq_len(nrow(data))) {
    row_number <- index + 1L
    if (!nzchar(data$curve_id[[index]])) stop_contract(sprintf("Row %d: curve_id must not be blank.", row_number))
    data$time_num[[index]] <- finite_number(data$time[[index]], "time", row_number)
    data$estimate_num[[index]] <- finite_number(data$estimate[[index]], "estimate", row_number)
    if (data$time_num[[index]] < 0) stop_contract(sprintf("Row %d: time must be >= 0.", row_number))
    if (data$estimate_num[[index]] < 0 || data$estimate_num[[index]] > 1) stop_contract(sprintf("Row %d: estimate must lie in [0, 1].", row_number))
  }
  curves <- ordered_unique(data$curve_id)
  for (curve in curves) {
    subset <- data[data$curve_id == curve, , drop = FALSE]
    if (nrow(subset) < 2L) stop_contract(sprintf("Curve '%s' needs at least two coordinates.", curve))
    if (any(diff(subset$time_num) <= 0)) stop_contract(sprintf("Curve '%s' must appear in strictly increasing time order.", curve))
    if (any(diff(subset$estimate_num) > 1e-12)) stop_contract(sprintf("Curve '%s' increases; supplied survival steps must be non-increasing.", curve))
  }
  list(data = data, curves = curves)
}

read_risk <- function(path, steps) {
  data <- metadata_columns(read_character_csv(path, c("time", "curve_id", "n_at_risk"), "Risk CSV"))
  data$curve_id <- trimws(data$curve_id)
  data$time_num <- NA_real_; data$n_num <- NA_integer_
  known <- steps$curves
  for (index in seq_len(nrow(data))) {
    row_number <- index + 1L
    curve <- data$curve_id[[index]]
    if (!curve %in% known) stop_contract(sprintf("Risk row %d: unknown curve_id '%s'.", row_number, curve))
    data$time_num[[index]] <- finite_number(data$time[[index]], "time", row_number)
    curve_times <- steps$data$time_num[steps$data$curve_id == curve]
    if (data$time_num[[index]] < min(curve_times) || data$time_num[[index]] > max(curve_times)) stop_contract(sprintf("Risk row %d: time is outside the supplied curve range.", row_number))
    count <- suppressWarnings(as.integer(trimws(data$n_at_risk[[index]])))
    if (is.na(count) || count < 0L || as.character(count) != trimws(data$n_at_risk[[index]])) stop_contract(sprintf("Risk row %d: n_at_risk must be a nonnegative integer.", row_number))
    data$n_num[[index]] <- count
  }
  if (anyDuplicated(paste(data$curve_id, data$time_num, sep = "\r"))) stop_contract("Risk curve_id/time pairs must be unique.")
  grids <- lapply(known, function(curve) {
    subset <- data[data$curve_id == curve, , drop = FALSE]
    if (!nrow(subset)) stop_contract(sprintf("Risk table is missing curve '%s'.", curve))
    if (any(diff(subset$time_num) <= 0)) stop_contract(sprintf("Risk rows for '%s' must appear in increasing time order.", curve))
    subset$time_num
  })
  if (any(vapply(grids[-1], function(grid) !identical(grid, grids[[1]]), logical(1)))) stop_contract("All curves must use the same ordered risk-table time grid.")
  list(data = data, times = grids[[1]])
}

read_annotations <- function(path, steps) {
  if (!nzchar(path)) return(data.frame())
  data <- metadata_columns(read_character_csv(path, c("time", "curve_id", "label"), "Annotation CSV"))
  data$curve_id <- trimws(data$curve_id); data$label <- trimws(data$label); data$time_num <- NA_real_
  for (index in seq_len(nrow(data))) {
    row_number <- index + 1L; curve <- data$curve_id[[index]]
    if (!curve %in% steps$curves) stop_contract(sprintf("Annotation row %d: unknown curve_id.", row_number))
    if (!nzchar(data$label[[index]])) stop_contract(sprintf("Annotation row %d: label must not be blank.", row_number))
    data$time_num[[index]] <- finite_number(data$time[[index]], "time", row_number)
    limits <- range(steps$data$time_num[steps$data$curve_id == curve])
    if (data$time_num[[index]] < limits[[1]] || data$time_num[[index]] > limits[[2]]) stop_contract(sprintf("Annotation row %d: time is outside the curve range.", row_number))
  }
  if (anyDuplicated(paste(data$curve_id, data$time_num, sep = "\r"))) stop_contract("Annotation curve_id/time pairs must be unique.")
  data
}

metadata_note <- function(data_frames) {
  statuses <- unlist(lapply(data_frames, function(data) if (nrow(data)) data$status else character()))
  seeds <- unlist(lapply(data_frames, function(data) if (nrow(data)) data$seed else character()))
  unique_statuses <- ordered_unique(statuses[nzchar(statuses)])
  unique_seeds <- ordered_unique(seeds[nzchar(seeds)])
  if (length(unique_statuses) > 1L || length(unique_seeds) > 1L) stop_contract("data_status and simulation_seed must be constant across all files.")
  if (identical(unique_statuses, "SIMULATED")) {
    if (any(statuses != "SIMULATED") || any(!nzchar(seeds))) stop_contract("Every simulated row must declare the same fixed seed.")
    seed <- suppressWarnings(as.integer(unique_seeds[[1]]))
    if (is.na(seed) || seed <= 0L || as.character(seed) != unique_seeds[[1]]) stop_contract("simulation_seed must be a positive integer.")
    return(sprintf("SIMULATED DEMONSTRATION DATA · fixed seed %d", seed))
  }
  if (length(unique_seeds)) stop_contract("simulation_seed is only valid with SIMULATED data.")
  "SOURCE-SUPPLIED / PRECOMPUTED DATA"
}

step_value <- function(steps, curve, time) {
  subset <- steps[steps$curve_id == curve, , drop = FALSE]
  index <- findInterval(time, subset$time_num)
  subset$estimate_num[[max(1L, index)]]
}

draw_figure <- function(steps, risk, annotations, curves, risk_times, note, options) {
  background <- "#FBFAF7"; ink <- "#20282C"; muted <- "#647078"; grid_color <- "#E5E2DC"
  palette <- c("#287D9B", "#D96B35", "#4F8A5B", "#8D65A8", "#B68A1F", "#5875B5")
  colors <- stats::setNames(rep(palette, length.out = length(curves)), curves)
  graphics::layout(matrix(c(1, 2), nrow = 2), heights = c(3.4, max(1.65, 0.55 * length(curves))))
  graphics::par(oma = c(3.0, 0.5, 4.5, 0.5), bg = background, fg = ink, family = "sans")
  all_times <- steps$time_num; span <- diff(range(all_times)); padding <- max(0.02 * span, 0.1)

  graphics::par(mar = c(0.7, 4.7, 0.7, 1.0))
  graphics::plot.new(); graphics::plot.window(xlim = range(all_times) + c(-padding, padding), ylim = c(-0.015, 1.025), xaxs = "i", yaxs = "i")
  x_ticks <- graphics::axTicks(1); y_ticks <- graphics::axTicks(2)
  graphics::abline(v = x_ticks, h = y_ticks, col = grid_color, lwd = 0.65)
  for (curve in curves) {
    subset <- steps[steps$curve_id == curve, , drop = FALSE]
    graphics::lines(subset$time_num, subset$estimate_num, type = "s", col = colors[[curve]], lwd = 1.8)
    graphics::points(subset$time_num, subset$estimate_num, pch = 21, bg = colors[[curve]], col = "white", cex = 0.78, lwd = 0.45)
  }
  if (nrow(annotations)) {
    for (index in seq_len(nrow(annotations))) {
      row <- annotations[index, ]; y <- step_value(steps, row$curve_id, row$time_num)
      graphics::segments(row$time_num, y, row$time_num + 0.18 * padding, y + 0.045, col = colors[[row$curve_id]], lwd = 0.7)
      graphics::text(row$time_num + 0.22 * padding, y + 0.055, row$label, adj = c(0, 0), cex = 0.68, col = colors[[row$curve_id]])
    }
  }
  graphics::axis(2, las = 1, cex.axis = 0.78, col = "#6D7A80")
  graphics::box(bty = "l", col = "#6D7A80")
  graphics::mtext("Supplied survival estimate", side = 2, line = 3.1, cex = 0.88)
  graphics::legend("bottomleft", legend = curves, col = unname(colors[curves]), lty = 1, lwd = 1.7, pch = 21, pt.bg = unname(colors[curves]), bty = "n", horiz = length(curves) <= 4L, cex = 0.76)

  graphics::par(mar = c(3.2, 4.7, 1.45, 1.0))
  graphics::plot.new(); graphics::plot.window(xlim = range(all_times) + c(-padding, padding), ylim = c(length(curves) + 0.5, 0.5), xaxs = "i", yaxs = "i")
  for (row_index in seq_along(curves)) if (row_index %% 2L == 1L) graphics::rect(min(all_times) - padding, row_index - 0.5, max(all_times) + padding, row_index + 0.5, col = "#F1EFE9", border = NA)
  graphics::abline(v = risk_times, col = grid_color, lwd = 0.55)
  for (row_index in seq_along(curves)) {
    curve <- curves[[row_index]]
    for (time in risk_times) {
      count <- risk$n_num[risk$curve_id == curve & risk$time_num == time]
      graphics::text(time, row_index, count, cex = 0.76)
    }
  }
  graphics::axis(1, at = risk_times, labels = format(risk_times, trim = TRUE), cex.axis = 0.78, col = "#6D7A80")
  graphics::axis(2, at = seq_along(curves), labels = curves, las = 1, tick = FALSE, cex.axis = 0.78)
  graphics::box(bty = "l", col = "#6D7A80")
  graphics::mtext(options$x_label, side = 1, line = 2.4, cex = 0.88)
  graphics::mtext("Supplied number at risk", side = 3, line = 0.45, adj = 0, cex = 0.88, font = 2)

  graphics::mtext(options$title, side = 3, outer = TRUE, line = 2.8, adj = 0.02, cex = 1.75, font = 2)
  graphics::mtext(note, side = 3, outer = TRUE, line = 1.35, adj = 0.02, cex = 0.86, col = muted)
  graphics::mtext("SUPPLIED/PRECOMPUTED coordinates, risk counts, and optional annotations; no Kaplan-Meier fit, confidence interval, or log-rank test is computed.", side = 3, outer = TRUE, line = 0.25, adj = 0.02, cex = 0.72, col = muted)
  graphics::mtext("Post-step convention: each estimate is held until the next supplied coordinate. Statistical interpretation remains upstream.", side = 1, outer = TRUE, line = 1.35, adj = 0.02, cex = 0.69, col = muted)
}

options <- parse_args(commandArgs(trailingOnly = TRUE))
steps <- read_steps(options$steps)
risk <- read_risk(options$risk, steps)
annotations <- read_annotations(options$annotations, steps)
note <- metadata_note(list(steps$data, risk$data, annotations))
width <- min(17, max(9, 7.2 + 0.62 * length(risk$times) + 0.03 * max(nchar(steps$curves))))
height <- max(7.0, 5.2 + 0.42 * length(steps$curves))
prefix <- file.path(dirname(options$output_prefix), tools::file_path_sans_ext(basename(options$output_prefix)))
dir.create(dirname(prefix), recursive = TRUE, showWarnings = FALSE)
png_path <- paste0(prefix, ".png"); pdf_path <- paste0(prefix, ".pdf")
grDevices::png(png_path, width = width, height = height, units = "in", res = options$dpi, bg = "#FBFAF7")
draw_figure(steps$data, risk$data, annotations, steps$curves, risk$times, note, options); grDevices::dev.off()
grDevices::pdf(pdf_path, width = width, height = height, bg = "#FBFAF7", onefile = TRUE)
draw_figure(steps$data, risk$data, annotations, steps$curves, risk$times, note, options); grDevices::dev.off()
message(sprintf("Validated %d supplied step coordinates, %d risk counts, %d supplied annotations, %d curves", nrow(steps$data), nrow(risk$data), nrow(annotations), length(steps$curves)))
message(sprintf("Data status: %s", note))
message(sprintf("PNG: %s", normalizePath(png_path, mustWork = TRUE)))
message(sprintf("PDF: %s", normalizePath(pdf_path, mustWork = TRUE)))
