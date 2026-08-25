#!/usr/bin/env Rscript

# Direction-aware benchmark heatmap using base R.

all_args <- commandArgs(trailingOnly = FALSE)
file_arg <- sub("^--file=", "", all_args[grep("^--file=", all_args)])
script_dir <- if (length(file_arg)) dirname(normalizePath(file_arg[[1]], mustWork = TRUE)) else getwd()
template_dir <- dirname(script_dir)

defaults <- list(
  input = file.path(template_dir, "demo", "demo_benchmark_seed109.csv"),
  metric_spec = file.path(template_dir, "demo", "demo_metric_spec.csv"),
  output_prefix = file.path(getwd(), "benchmark_heatmap_r"),
  title = "Benchmark performance matrix",
  dpi = 320L
)
max_metrics <- 18L
max_methods <- 80L

parse_args <- function(args) {
  result <- defaults
  aliases <- c(input = "input", `metric-spec` = "metric_spec", `output-prefix` = "output_prefix", title = "title", dpi = "dpi")
  index <- 1L
  while (index <= length(args)) {
    token <- args[[index]]
    if (!startsWith(token, "--")) stop(sprintf("Unknown argument: %s", token), call. = FALSE)
    stripped <- substring(token, 3L)
    if (grepl("=", stripped, fixed = TRUE)) {
      pieces <- strsplit(stripped, "=", fixed = TRUE)[[1]]
      key <- pieces[[1]]
      value <- paste(pieces[-1], collapse = "=")
    } else {
      key <- stripped
      index <- index + 1L
      if (index > length(args)) stop(sprintf("Missing value for --%s", key), call. = FALSE)
      value <- args[[index]]
    }
    if (!key %in% names(aliases)) stop(sprintf("Unknown option: --%s", key), call. = FALSE)
    result[[aliases[[key]]]] <- value
    index <- index + 1L
  }
  result$dpi <- suppressWarnings(as.integer(result$dpi))
  if (is.na(result$dpi) || result$dpi < 150L) stop("--dpi must be at least 150.", call. = FALSE)
  result
}

stop_contract <- function(message) stop(sprintf("Input validation failed: %s", message), call. = FALSE)
ordered_unique <- function(values) values[!duplicated(values)]

read_character_csv <- function(path, label) {
  if (!file.exists(path) || dir.exists(path)) stop_contract(sprintf("%s does not exist: %s", label, path))
  data <- tryCatch(
    utils::read.csv(path, stringsAsFactors = FALSE, check.names = FALSE, colClasses = "character", na.strings = character()),
    error = function(error) stop_contract(conditionMessage(error))
  )
  names(data) <- trimws(names(data))
  if (!ncol(data)) stop_contract(sprintf("%s has no header row.", label))
  if (any(!nzchar(names(data))) || anyDuplicated(names(data))) stop_contract(sprintf("%s headers must be nonblank and unique.", label))
  if (nrow(data)) {
    keep <- apply(data, 1L, function(row) any(nzchar(trimws(row))))
    data <- data[keep, , drop = FALSE]
  }
  data
}

finite_number <- function(text, field, row_number, allow_blank = FALSE) {
  value <- trimws(text)
  if (!nzchar(value)) {
    if (allow_blank) return(NA_real_)
    stop_contract(sprintf("Row %d: '%s' must not be blank.", row_number, field))
  }
  number <- suppressWarnings(as.numeric(value))
  if (is.na(number) || !is.finite(number)) stop_contract(sprintf("Row %d: '%s' must be finite numeric.", row_number, field))
  number
}

read_metric_spec <- function(path) {
  data <- read_character_csv(path, "Metric spec")
  required <- c("metric", "label", "direction", "display", "digits", "scale_min", "scale_max")
  missing <- setdiff(required, names(data))
  if (length(missing)) stop_contract(sprintf("Metric spec is missing columns: %s", paste(missing, collapse = ", ")))
  if (!nrow(data)) stop_contract("Metric spec contains no metrics.")
  data$metric <- trimws(data$metric)
  data$label <- trimws(data$label)
  data$direction <- tolower(trimws(data$direction))
  data$display <- tolower(trimws(data$display))
  data$digits_num <- NA_integer_
  data$scale_min_num <- NA_real_
  data$scale_max_num <- NA_real_
  for (index in seq_len(nrow(data))) {
    row_number <- index + 1L
    if (!nzchar(data$metric[[index]]) || !nzchar(data$label[[index]])) stop_contract(sprintf("Metric spec row %d: metric and label are required.", row_number))
    if (!data$direction[[index]] %in% c("higher", "lower")) stop_contract(sprintf("Metric spec row %d: direction must be higher or lower.", row_number))
    if (!data$display[[index]] %in% c("decimal", "percent", "integer", "scientific")) stop_contract(sprintf("Metric spec row %d: unsupported display.", row_number))
    digits <- suppressWarnings(as.integer(trimws(data$digits[[index]])))
    if (is.na(digits) || digits < 0L || digits > 6L || as.character(digits) != trimws(data$digits[[index]])) stop_contract(sprintf("Metric spec row %d: digits must be an integer from 0 to 6.", row_number))
    data$digits_num[[index]] <- digits
    data$scale_min_num[[index]] <- finite_number(data$scale_min[[index]], "scale_min", row_number)
    data$scale_max_num[[index]] <- finite_number(data$scale_max[[index]], "scale_max", row_number)
    if (!(data$scale_min_num[[index]] < data$scale_max_num[[index]])) stop_contract(sprintf("Metric spec row %d: require scale_min < scale_max.", row_number))
  }
  if (anyDuplicated(data$metric)) stop_contract("Metric identifiers must be unique.")
  if (nrow(data) > max_metrics) stop_contract(sprintf("Metric spec contains %d metrics; readable limit is %d. Split into coherent panels.", nrow(data), max_metrics))
  data
}

read_scores <- function(path, spec) {
  data <- read_character_csv(path, "Benchmark CSV")
  required <- c("method", "metric", "value")
  missing <- setdiff(required, names(data))
  if (length(missing)) stop_contract(sprintf("Benchmark CSV is missing columns: %s", paste(missing, collapse = ", ")))
  if (!nrow(data)) stop_contract("Benchmark CSV contains no data rows.")
  data$method <- trimws(data$method)
  data$metric <- trimws(data$metric)
  data$value_num <- NA_real_
  status <- if ("data_status" %in% names(data)) toupper(trimws(data$data_status)) else rep("", nrow(data))
  seed <- if ("simulation_seed" %in% names(data)) trimws(data$simulation_seed) else rep("", nrow(data))
  for (index in seq_len(nrow(data))) {
    row_number <- index + 1L
    if (!nzchar(data$method[[index]]) || !nzchar(data$metric[[index]])) stop_contract(sprintf("Row %d: method and metric are required.", row_number))
    spec_index <- match(data$metric[[index]], spec$metric)
    if (is.na(spec_index)) stop_contract(sprintf("Row %d: unknown metric '%s'.", row_number, data$metric[[index]]))
    value <- finite_number(data$value[[index]], "value", row_number, allow_blank = TRUE)
    if (is.finite(value)) {
      if (value < spec$scale_min_num[[spec_index]] || value > spec$scale_max_num[[spec_index]]) stop_contract(sprintf("Row %d: value lies outside the metric's declared scale.", row_number))
      if (spec$display[[spec_index]] == "integer" && abs(value - round(value)) > 1e-9) stop_contract(sprintf("Row %d: integer display requires an integer-valued input.", row_number))
    }
    data$value_num[[index]] <- value
  }
  if (anyDuplicated(paste(data$method, data$metric, sep = "\r"))) stop_contract("method/metric pairs must be unique.")
  methods <- ordered_unique(data$method)
  if (length(methods) > max_methods) stop_contract(sprintf("Benchmark contains %d methods; readable limit is %d. Filter or split it.", length(methods), max_methods))
  expected <- expand.grid(method = methods, metric = spec$metric, stringsAsFactors = FALSE)
  present <- paste(data$method, data$metric, sep = "\r")
  absent <- !paste(expected$method, expected$metric, sep = "\r") %in% present
  if (any(absent)) {
    first <- expected[which(absent)[[1]], ]
    stop_contract(sprintf("Missing method/metric pair '%s' + '%s'; use a blank value for explicit NA.", first$method, first$metric))
  }
  statuses <- ordered_unique(status[nzchar(status)])
  seeds <- ordered_unique(seed[nzchar(seed)])
  if (length(statuses) > 1L || length(seeds) > 1L) stop_contract("data_status and simulation_seed must each be constant.")
  if (identical(statuses, "SIMULATED")) {
    if (any(status != "SIMULATED") || any(!nzchar(seed))) stop_contract("Every simulated row must declare SIMULATED and one fixed seed.")
    seed_number <- suppressWarnings(as.integer(seeds[[1]]))
    if (is.na(seed_number) || seed_number <= 0L || as.character(seed_number) != seeds[[1]]) stop_contract("simulation_seed must be a positive integer.")
    data_note <- sprintf("SIMULATED DEMONSTRATION DATA · fixed seed %d", seed_number)
  } else {
    if (length(seeds)) stop_contract("simulation_seed is only valid with SIMULATED data.")
    data_note <- "SOURCE-SUPPLIED DATA"
  }
  list(data = data, methods = methods, data_note = data_note)
}

performance <- function(value, spec_row) {
  scaled <- (value - spec_row$scale_min_num) / (spec_row$scale_max_num - spec_row$scale_min_num)
  if (spec_row$direction == "higher") scaled else 1 - scaled
}

format_value <- function(value, spec_row) {
  if (!is.finite(value)) return("NA")
  digits <- spec_row$digits_num
  if (spec_row$display == "percent") return(sprintf(paste0("%.", digits, "f%%"), 100 * value))
  if (spec_row$display == "integer") return(sprintf("%.0f", value))
  if (spec_row$display == "scientific") return(sprintf(paste0("%.", digits, "e"), value))
  sprintf(paste0("%.", digits, "f"), value)
}

build_matrix <- function(validated, spec) {
  methods <- validated$methods
  values <- matrix(NA_real_, nrow = length(methods), ncol = nrow(spec), dimnames = list(methods, spec$metric))
  labels <- matrix("NA", nrow = length(methods), ncol = nrow(spec), dimnames = list(methods, spec$metric))
  perf <- values
  for (index in seq_len(nrow(validated$data))) {
    row <- validated$data[index, ]
    method_index <- match(row$method, methods)
    metric_index <- match(row$metric, spec$metric)
    values[method_index, metric_index] <- row$value_num
    labels[method_index, metric_index] <- format_value(row$value_num, spec[metric_index, ])
    if (is.finite(row$value_num)) perf[method_index, metric_index] <- performance(row$value_num, spec[metric_index, ])
  }
  coverage <- rowSums(is.finite(perf))
  available_mean <- rowMeans(perf, na.rm = TRUE)
  available_mean[coverage == 0L] <- -Inf
  complete <- coverage == ncol(perf)
  overall <- rep(NA_real_, nrow(perf))
  overall[complete] <- rowMeans(perf[complete, , drop = FALSE])
  complete_indices <- which(complete)
  complete_indices <- complete_indices[order(-overall[complete_indices], tolower(methods[complete_indices]))]
  ranks <- rep(NA_integer_, length(methods))
  previous_score <- NA_real_
  previous_rank <- 0L
  for (position in seq_along(complete_indices)) {
    index <- complete_indices[[position]]
    if (position > 1L && abs(overall[[index]] - previous_score) <= 1e-12) {
      ranks[[index]] <- previous_rank
    } else {
      ranks[[index]] <- position
      previous_rank <- position
      previous_score <- overall[[index]]
    }
  }
  incomplete_indices <- which(!complete)
  if (length(incomplete_indices)) incomplete_indices <- incomplete_indices[order(-coverage[incomplete_indices], -available_mean[incomplete_indices], tolower(methods[incomplete_indices]))]
  order_indices <- c(complete_indices, incomplete_indices)
  list(
    values = values[order_indices, , drop = FALSE],
    labels = labels[order_indices, , drop = FALSE],
    perf = perf[order_indices, , drop = FALSE],
    methods = methods[order_indices],
    ranks = ranks[order_indices],
    incomplete_count = sum(!complete)
  )
}

draw_figure <- function(matrix_data, spec, data_note, options) {
  background <- "#FBFAF7"
  ink <- "#20282C"
  muted <- "#637078"
  missing_color <- "#DDDCD7"
  colors <- grDevices::colorRampPalette(c("#B75C45", "#F0EADF", "#277C80"))(101)
  n_methods <- length(matrix_data$methods)
  n_metrics <- nrow(spec)
  graphics::layout(matrix(c(1, 2), nrow = 2), heights = c(10.5, 2.2))
  graphics::par(mar = c(1.0, min(15, 7 + 0.30 * max(nchar(matrix_data$methods))), 7.0, 1.0), bg = background, fg = ink, family = "sans")
  graphics::plot.new()
  graphics::plot.window(xlim = c(0.5, n_metrics + 0.5), ylim = c(n_methods + 0.5, 0.5), xaxs = "i", yaxs = "i")
  for (row_index in seq_len(n_methods)) {
    for (col_index in seq_len(n_metrics)) {
      score <- matrix_data$perf[row_index, col_index]
      fill <- if (is.finite(score)) colors[[1L + round(100 * score)]] else missing_color
      graphics::rect(col_index - 0.5, row_index - 0.5, col_index + 0.5, row_index + 0.5, col = fill, border = background, lwd = 2)
      text_color <- if (is.finite(score) && (score < 0.19 || score > 0.81)) "white" else ink
      graphics::text(col_index, row_index, matrix_data$labels[row_index, col_index], cex = max(0.52, 0.80 - 0.02 * max(0, n_metrics - 8)), col = text_color, font = if (is.finite(score)) 2 else 1)
    }
  }
  row_labels <- ifelse(is.na(matrix_data$ranks), paste("NR", matrix_data$methods, sep = "  "), paste0("#", matrix_data$ranks, "  ", matrix_data$methods))
  graphics::axis(2, at = seq_len(n_methods), labels = row_labels, las = 1, tick = FALSE, cex.axis = max(0.62, 0.84 - 0.006 * max(0, n_methods - 20)), line = -0.5)
  column_labels <- paste0(spec$label, "\n", ifelse(spec$direction == "higher", "higher is better", "lower is better"))
  if (n_metrics <= 10L) {
    graphics::axis(3, at = seq_len(n_metrics), labels = column_labels, tick = FALSE, cex.axis = 0.76, line = -0.3)
  } else {
    graphics::text(seq_len(n_metrics), 0.18, labels = column_labels, srt = 34, adj = c(0, 0.5), xpd = NA, cex = max(0.55, 0.74 - 0.015 * (n_metrics - 10)))
  }
  graphics::box(col = "#D0CEC8")
  graphics::mtext(options$title, side = 3, line = 5.2, adj = 0, cex = 1.75, font = 2)
  graphics::mtext(data_note, side = 3, line = 3.65, adj = 0, cex = 0.88, col = muted)
  graphics::mtext("Cell text = original value · color = direction-aligned performance on the metric's declared [scale_min, scale_max]", side = 3, line = 2.45, adj = 0, cex = 0.76, col = muted)

  graphics::par(mar = c(3.5, 8.0, 0.2, 8.0), bg = background)
  graphics::plot.new()
  graphics::plot.window(xlim = c(0, 1), ylim = c(0, 1), xaxs = "i", yaxs = "i")
  breaks <- seq(0, 1, length.out = length(colors) + 1L)
  for (index in seq_along(colors)) graphics::rect(breaks[[index]], 0.66, breaks[[index + 1L]], 0.88, col = colors[[index]], border = NA)
  graphics::axis(1, at = c(0, 0.5, 1), labels = c("0 · worse", "0.5", "1 · better"), pos = 0.63, cex.axis = 0.75, col = NA, col.axis = ink)
  graphics::text(0.5, 0.30, "Comparable normalized performance", cex = 0.78, col = ink)
  graphics::mtext(sprintf("Complete methods use equal-weight mean normalized performance; exact ties share competition rank. NR = at least one NA (%d method(s)). No significance testing.", matrix_data$incomplete_count), side = 1, line = 2.0, adj = 0.5, cex = 0.67, col = muted)
}

options <- parse_args(commandArgs(trailingOnly = TRUE))
spec <- read_metric_spec(options$metric_spec)
validated <- read_scores(options$input, spec)
matrix_data <- build_matrix(validated, spec)
longest_method <- max(nchar(matrix_data$methods))
device_width <- min(22, max(8.8, 3.3 + 1.55 * nrow(spec) + 0.035 * longest_method))
device_height <- max(5.8, 2.8 + 0.52 * length(matrix_data$methods))
prefix <- file.path(dirname(options$output_prefix), tools::file_path_sans_ext(basename(options$output_prefix)))
dir.create(dirname(prefix), recursive = TRUE, showWarnings = FALSE)
png_path <- paste0(prefix, ".png")
pdf_path <- paste0(prefix, ".pdf")

grDevices::png(png_path, width = device_width, height = device_height, units = "in", res = options$dpi, bg = "#FBFAF7")
draw_figure(matrix_data, spec, validated$data_note, options)
grDevices::dev.off()
grDevices::pdf(pdf_path, width = device_width, height = device_height, bg = "#FBFAF7", onefile = TRUE)
draw_figure(matrix_data, spec, validated$data_note, options)
grDevices::dev.off()

message(sprintf("Validated %d rows: %d methods × %d metrics; %d explicit NA cells; %d unranked method(s)", nrow(validated$data), length(validated$methods), nrow(spec), sum(!is.finite(validated$data$value_num)), matrix_data$incomplete_count))
message(sprintf("Data status: %s", validated$data_note))
message(sprintf("PNG: %s", normalizePath(png_path, mustWork = TRUE)))
message(sprintf("PDF: %s", normalizePath(pdf_path, mustWork = TRUE)))
