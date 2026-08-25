#!/usr/bin/env Rscript

# Render validated, panel-aware forest plots from a single long-form CSV.

locate_script <- function() {
  arguments <- commandArgs(trailingOnly = FALSE)
  file_argument <- grep("^--file=", arguments, value = TRUE)
  if (length(file_argument) > 0) {
    return(normalizePath(sub("^--file=", "", file_argument[[1]]), winslash = "/", mustWork = TRUE))
  }
  frame_files <- vapply(
    sys.frames(),
    function(frame) if (is.null(frame$ofile)) "" else as.character(frame$ofile)[[1]],
    character(1)
  )
  frame_files <- frame_files[nzchar(frame_files)]
  if (length(frame_files) > 0) {
    return(normalizePath(tail(frame_files, 1), winslash = "/", mustWork = TRUE))
  }
  stop("Unable to determine the script location", call. = FALSE)
}

script_file <- locate_script()
script_dir <- dirname(script_file)
template_dir <- dirname(script_dir)

defaults <- list(
  input = file.path(template_dir, "demo", "demo_simulated_seed172.csv"),
  output_prefix = file.path(template_dir, "output", "forest_r"),
  title = "Forest plot of source-supplied effect estimates",
  dpi = 320L
)

parse_arguments <- function(arguments) {
  result <- defaults
  index <- 1L
  while (index <= length(arguments)) {
    key <- arguments[[index]]
    if (!key %in% c("--input", "--output-prefix", "--title", "--dpi")) {
      stop(sprintf("Unknown argument: %s", key), call. = FALSE)
    }
    if (index == length(arguments)) {
      stop(sprintf("Missing value after %s", key), call. = FALSE)
    }
    value <- arguments[[index + 1L]]
    if (key == "--input") result$input <- value
    if (key == "--output-prefix") result$output_prefix <- value
    if (key == "--title") result$title <- value
    if (key == "--dpi") result$dpi <- suppressWarnings(as.integer(value))
    index <- index + 2L
  }
  if (is.na(result$dpi) || result$dpi < 150L) {
    stop("--dpi must be an integer of at least 150", call. = FALSE)
  }
  result
}

config <- parse_arguments(commandArgs(trailingOnly = TRUE))

required_columns <- c("label", "estimate", "ci_low", "ci_high")
additive_metrics <- c(
  "",
  "additive",
  "difference",
  "mean_difference",
  "risk_difference",
  "beta",
  "coefficient",
  "correlation",
  "log_ratio",
  "log_odds",
  "log_hazard"
)
ratio_metrics <- c(
  "ratio",
  "odds_ratio",
  "risk_ratio",
  "rate_ratio",
  "hazard_ratio",
  "prevalence_ratio"
)
base_colors <- c(
  "#277DA1",
  "#D97745",
  "#548C68",
  "#7A6FA6",
  "#B34F62",
  "#4D646F",
  "#C39A2E",
  "#4C956C"
)
base_markers <- c(21, 22, 23, 24, 25, 21, 22, 23)
background <- "#FBFAF7"
ink <- "#17242C"
muted <- "#5C696E"
grid_color <- "#DADDD8"

ordered_unique <- function(values) values[!duplicated(values)]

column_or_blank <- function(data, name) {
  if (name %in% names(data)) as.character(data[[name]]) else rep("", nrow(data))
}

normalize_metric <- function(value, row_number) {
  normalized <- gsub("[ -]", "_", tolower(trimws(value)))
  if (normalized %in% additive_metrics) {
    return(list(metric = if (normalized == "") "additive" else normalized, family = "additive"))
  }
  if (normalized %in% ratio_metrics) {
    return(list(metric = normalized, family = "ratio"))
  }
  allowed <- sort(setdiff(unique(c(additive_metrics, ratio_metrics)), ""))
  stop(
    sprintf(
      "Row %d: unsupported metric %s. Use one of: %s",
      row_number,
      shQuote(value),
      paste(allowed, collapse = ", ")
    ),
    call. = FALSE
  )
}

parse_numeric <- function(values, name, required) {
  text <- trimws(as.character(values))
  missing <- is.na(text) | !nzchar(text)
  converted <- suppressWarnings(as.numeric(text))
  invalid <- (!missing & is.na(converted)) | (!is.na(converted) & !is.finite(converted))
  if (required) invalid <- invalid | missing
  if (any(invalid)) {
    row_number <- which(invalid)[[1]] + 1L
    qualifier <- if (required) "must be finite numeric" else "must be finite numeric when supplied"
    stop(sprintf("Row %d: %s %s", row_number, name, qualifier), call. = FALSE)
  }
  converted
}

read_and_validate <- function(path) {
  if (!file.exists(path)) {
    stop(sprintf("Input CSV not found: %s", path), call. = FALSE)
  }
  raw <- utils::read.csv(
    path,
    check.names = FALSE,
    stringsAsFactors = FALSE,
    colClasses = "character",
    na.strings = NULL,
    strip.white = FALSE
  )
  missing_columns <- setdiff(required_columns, names(raw))
  if (length(missing_columns) > 0) {
    stop(
      sprintf("Missing required columns: %s", paste(missing_columns, collapse = ", ")),
      call. = FALSE
    )
  }
  if (nrow(raw) == 0) {
    stop("Input CSV contains no estimate rows", call. = FALSE)
  }

  label <- trimws(as.character(raw$label))
  if (any(is.na(label) | !nzchar(label))) {
    stop(sprintf("Row %d: label must not be blank", which(is.na(label) | !nzchar(label))[[1]] + 1L), call. = FALSE)
  }
  estimate <- parse_numeric(raw$estimate, "estimate", TRUE)
  ci_low <- parse_numeric(raw$ci_low, "ci_low", TRUE)
  ci_high <- parse_numeric(raw$ci_high, "ci_high", TRUE)
  invalid_width <- !(ci_low < ci_high)
  if (any(invalid_width)) {
    stop(sprintf("Row %d: require ci_low < ci_high", which(invalid_width)[[1]] + 1L), call. = FALSE)
  }
  outside <- estimate < ci_low | estimate > ci_high
  if (any(outside)) {
    stop(
      sprintf("Row %d: estimate must lie within [ci_low, ci_high]", which(outside)[[1]] + 1L),
      call. = FALSE
    )
  }

  panel <- trimws(column_or_blank(raw, "panel"))
  panel[is.na(panel) | !nzchar(panel)] <- "Forest plot"
  section <- trimws(column_or_blank(raw, "section"))
  section[is.na(section)] <- ""
  series <- trimws(column_or_blank(raw, "series"))
  series[is.na(series) | !nzchar(series)] <- "Estimate"
  metric_input <- column_or_blank(raw, "metric")
  metric_info <- lapply(seq_len(nrow(raw)), function(index) normalize_metric(metric_input[[index]], index + 1L))
  metric <- vapply(metric_info, `[[`, character(1), "metric")
  family <- vapply(metric_info, `[[`, character(1), "family")

  null_input <- parse_numeric(column_or_blank(raw, "null_value"), "null_value", FALSE)
  null_value <- null_input
  null_value[is.na(null_value) & family == "additive"] <- 0
  null_value[is.na(null_value) & family == "ratio"] <- 1
  ratio_rows <- family == "ratio"
  bad_ratio_null <- ratio_rows & abs(null_value - 1) > 1e-12
  if (any(bad_ratio_null)) {
    stop(
      sprintf("Row %d: ratio metrics require null_value = 1", which(bad_ratio_null)[[1]] + 1L),
      call. = FALSE
    )
  }
  bad_ratio_values <- ratio_rows & (estimate <= 0 | ci_low <= 0 | ci_high <= 0)
  if (any(bad_ratio_values)) {
    stop(
      sprintf("Row %d: ratio estimates and CI bounds must be > 0", which(bad_ratio_values)[[1]] + 1L),
      call. = FALSE
    )
  }

  p_value <- parse_numeric(column_or_blank(raw, "p_value"), "p_value", FALSE)
  bad_p <- !is.na(p_value) & (p_value < 0 | p_value > 1)
  if (any(bad_p)) {
    stop(sprintf("Row %d: p_value must lie within [0, 1]", which(bad_p)[[1]] + 1L), call. = FALSE)
  }
  n_value <- parse_numeric(column_or_blank(raw, "n"), "n", FALSE)
  bad_n <- !is.na(n_value) & (n_value <= 0 | abs(n_value - round(n_value)) > 1e-9)
  if (any(bad_n)) {
    stop(sprintf("Row %d: n must be a positive integer", which(bad_n)[[1]] + 1L), call. = FALSE)
  }
  n_value[!is.na(n_value)] <- round(n_value[!is.na(n_value)])

  identity <- paste(panel, section, label, series, sep = "\034")
  duplicated_identity <- duplicated(identity)
  if (any(duplicated_identity)) {
    stop(
      sprintf(
        "Row %d: duplicate panel/section/label/series combination",
        which(duplicated_identity)[[1]] + 1L
      ),
      call. = FALSE
    )
  }

  data <- data.frame(
    source_row = seq_len(nrow(raw)) + 1L,
    label = label,
    estimate = estimate,
    ci_low = ci_low,
    ci_high = ci_high,
    panel = panel,
    section = section,
    series = series,
    metric = metric,
    family = family,
    null_value = null_value,
    p_value = p_value,
    n = n_value,
    stringsAsFactors = FALSE,
    check.names = FALSE
  )

  for (panel_name in ordered_unique(data$panel)) {
    selected <- data$panel == panel_name
    if (length(unique(data$family[selected])) != 1L) {
      stop(
        sprintf("Panel %s mixes additive and ratio metrics; split it into panels", shQuote(panel_name)),
        call. = FALSE
      )
    }
    references <- data$null_value[selected]
    if (any(abs(references - references[[1]]) > 1e-12)) {
      stop(sprintf("Panel %s contains inconsistent null_value entries", shQuote(panel_name)), call. = FALSE)
    }
  }

  status <- trimws(column_or_blank(raw, "data_status"))
  status <- ordered_unique(status[!is.na(status) & nzchar(status)])
  seed <- trimws(column_or_blank(raw, "simulation_seed"))
  seed <- ordered_unique(seed[!is.na(seed) & nzchar(seed)])
  if (length(status) > 1L) stop("data_status must be constant when supplied", call. = FALSE)
  if (length(seed) > 1L) stop("simulation_seed must be constant when supplied", call. = FALSE)
  if (length(status) == 1L && toupper(status[[1]]) == "SIMULATED") {
    if (length(seed) != 1L) stop("SIMULATED data must supply simulation_seed", call. = FALSE)
    data_note <- sprintf("SIMULATED DEMONSTRATION DATA · fixed seed %s", seed[[1]])
  } else {
    data_note <- "SOURCE-SUPPLIED ESTIMATES"
  }

  list(data = data, data_note = data_note)
}

label_key <- function(section, label) paste(section, label, sep = "\035")

build_layout <- function(data, panel_name) {
  panel_data <- data[data$panel == panel_name, , drop = FALSE]
  sections <- ordered_unique(panel_data$section)
  items <- data.frame(
    kind = character(),
    text = character(),
    section = character(),
    label = character(),
    stringsAsFactors = FALSE
  )
  for (section_name in sections) {
    if (nzchar(section_name)) {
      items <- rbind(
        items,
        data.frame(kind = "header", text = section_name, section = section_name, label = "")
      )
    }
    labels <- ordered_unique(panel_data$label[panel_data$section == section_name])
    for (label_name in labels) {
      items <- rbind(
        items,
        data.frame(kind = "label", text = label_name, section = section_name, label = label_name)
      )
    }
  }
  items$y <- rev(seq_len(nrow(items)))
  label_rows <- items$kind == "label"
  label_y <- stats::setNames(items$y[label_rows], label_key(items$section[label_rows], items$label[label_rows]))
  list(
    name = panel_name,
    data = panel_data,
    items = items,
    label_y = label_y,
    series = ordered_unique(panel_data$series),
    family = panel_data$family[[1]],
    null_value = panel_data$null_value[[1]]
  )
}

panel_limits <- function(layout) {
  values <- c(layout$null_value, layout$data$ci_low, layout$data$ci_high)
  lower <- min(values)
  upper <- max(values)
  if (layout$family == "ratio") {
    log_range <- log(c(lower, upper))
    padding <- max(diff(log_range) * 0.09, 0.06)
    return(exp(log_range + c(-padding, padding)))
  }
  padding <- max((upper - lower) * 0.09, 0.05)
  c(lower - padding, upper + padding)
}

ratio_ticks <- function(limits) {
  powers <- seq(floor(log10(limits[[1]])) - 1, ceiling(log10(limits[[2]])) + 1)
  candidates <- sort(unique(as.vector(outer(c(1, 2, 5), 10 ^ powers))))
  ticks <- candidates[candidates >= limits[[1]] & candidates <= limits[[2]]]
  if (length(ticks) < 2L) ticks <- sort(unique(c(limits, 1)))
  ticks
}

format_number <- function(value) {
  magnitude <- abs(value)
  if (magnitude > 0 && (magnitude < 0.01 || magnitude >= 1000)) {
    format(value, scientific = TRUE, digits = 3)
  } else {
    sprintf("%.2f", value)
  }
}

format_p <- function(value) {
  if (value < 0.001) format(value, scientific = TRUE, digits = 3) else sprintf("%.3f", value)
}

summary_label <- function(row) {
  pieces <- sprintf(
    "%s [%s, %s]",
    format_number(row$estimate),
    format_number(row$ci_low),
    format_number(row$ci_high)
  )
  if (!is.na(row$p_value)) pieces <- c(pieces, paste0("p=", format_p(row$p_value)))
  if (!is.na(row$n)) pieces <- c(pieces, paste0("n=", format(row$n, big.mark = ",", scientific = FALSE)))
  paste(pieces, collapse = " · ")
}

axis_label <- function(layout) {
  if (layout$family == "ratio") {
    "Ratio effect (95% CI; logarithmic axis)"
  } else {
    "Additive effect (95% CI; linear axis)"
  }
}

wrap_label <- function(value, width = 42L) paste(strwrap(value, width = width), collapse = "\n")

validated <- read_and_validate(config$input)
data <- validated$data
data_note <- validated$data_note
panel_order <- ordered_unique(data$panel)
layouts <- lapply(panel_order, function(panel_name) build_layout(data, panel_name))
global_series <- ordered_unique(data$series)
series_colors <- stats::setNames(
  rep(base_colors, length.out = length(global_series)),
  global_series
)
series_markers <- stats::setNames(
  rep(base_markers, length.out = length(global_series)),
  global_series
)

max_label_length <- max(nchar(data$label, type = "width"))
figure_width <- min(17, max(10.8, 10.8 + 0.055 * (max_label_length - 24)))
item_counts <- vapply(layouts, function(layout) nrow(layout$items), integer(1))
panel_heights <- pmax(2.6, item_counts * 0.43 + 1.0)
figure_height <- max(5.4, 1.7 + sum(panel_heights))
left_margin <- min(30, max(12, ceiling(max_label_length * 0.42)))
right_margin <- 21

draw_figure <- function() {
  layout(matrix(seq_along(layouts), ncol = 1), heights = panel_heights)
  par(
    oma = c(4.4, 0.7, 5.3, 0.7),
    family = "sans",
    bg = background,
    fg = ink,
    col.axis = "#3E4C53",
    col.lab = ink
  )

  for (panel_index in seq_along(layouts)) {
    panel_layout <- layouts[[panel_index]]
    panel_data <- panel_layout$data
    limits <- panel_limits(panel_layout)
    y_limits <- c(0.35, nrow(panel_layout$items) + 0.65)
    par(mar = c(4.2, left_margin, 3.8, right_margin))
    plot.new()
    plot.window(
      xlim = limits,
      ylim = y_limits,
      xaxs = "i",
      yaxs = "i",
      log = if (panel_layout$family == "ratio") "x" else ""
    )

    ticks <- if (panel_layout$family == "ratio") ratio_ticks(limits) else pretty(limits, n = 6)
    abline(v = ticks, col = grid_color, lwd = 0.65)
    abline(v = panel_layout$null_value, col = "#5F6D73", lty = 2, lwd = 1.0)

    label_items <- panel_layout$items[panel_layout$items$kind == "label", , drop = FALSE]
    axis(
      2,
      at = label_items$y,
      labels = vapply(label_items$text, wrap_label, character(1)),
      las = 1,
      tick = FALSE,
      cex.axis = 0.76,
      line = -0.3
    )
    if (panel_layout$family == "ratio") {
      axis(1, at = ticks, labels = format(ticks, trim = TRUE, scientific = FALSE), cex.axis = 0.78)
    } else {
      axis(1, at = ticks, labels = format(ticks, trim = TRUE, digits = 4), cex.axis = 0.78)
    }
    segments(limits[[1]], y_limits[[1]], limits[[2]], y_limits[[1]], col = "#738087", lwd = 0.8)
    mtext(axis_label(panel_layout), side = 1, line = 2.7, cex = 0.82)
    mtext(panel_layout$name, side = 3, line = 2.0, adj = 0, cex = 1.05, font = 2)

    header_items <- panel_layout$items[panel_layout$items$kind == "header", , drop = FALSE]
    if (nrow(header_items) > 0) {
      header_x <- if (panel_layout$family == "ratio") {
        exp(log(limits[[1]]) + 0.018 * diff(log(limits)))
      } else {
        limits[[1]] + 0.018 * diff(limits)
      }
      for (header_index in seq_len(nrow(header_items))) {
        header_y <- header_items$y[[header_index]]
        segments(limits[[1]], header_y, limits[[2]], header_y, col = "#BFC5C2", lwd = 0.75)
        text(
          header_x,
          header_y,
          header_items$text[[header_index]],
          adj = c(0, 0.5),
          cex = 0.72,
          font = 2,
          col = "#415159"
        )
      }
    }

    panel_series <- panel_layout$series
    offsets <- if (length(panel_series) == 1L) {
      stats::setNames(0, panel_series)
    } else {
      span <- min(0.60, 0.30 * (length(panel_series) - 1L))
      # Keep the first series visually above later series, matching the Python output.
      stats::setNames(seq(span / 2, -span / 2, length.out = length(panel_series)), panel_series)
    }
    summary_x <- if (panel_layout$family == "ratio") {
      exp(log(limits[[2]]) + 0.065 * diff(log(limits)))
    } else {
      limits[[2]] + 0.065 * diff(limits)
    }

    for (row_index in seq_len(nrow(panel_data))) {
      row <- panel_data[row_index, , drop = FALSE]
      row_y <- unname(panel_layout$label_y[[label_key(row$section, row$label)]]) + offsets[[row$series]]
      row_color <- series_colors[[row$series]]
      segments(row$ci_low, row_y, row$ci_high, row_y, col = row_color, lwd = 1.45)
      segments(row$ci_low, row_y - 0.045, row$ci_low, row_y + 0.045, col = row_color, lwd = 0.9)
      segments(row$ci_high, row_y - 0.045, row$ci_high, row_y + 0.045, col = row_color, lwd = 0.9)
      points(
        row$estimate,
        row_y,
        pch = series_markers[[row$series]],
        bg = row_color,
        col = background,
        lwd = 0.7,
        cex = 0.88
      )
      text(
        summary_x,
        row_y,
        summary_label(row),
        adj = c(0, 0.5),
        cex = 0.62,
        col = "#46545B",
        xpd = NA
      )
    }

    text(
      summary_x,
      y_limits[[2]] + 0.12,
      "Estimate [95% CI] · optional p and n",
      adj = c(0, 0),
      cex = 0.64,
      font = 2,
      col = "#526068",
      xpd = NA
    )

    if (length(panel_series) > 1L) {
      legend(
        "topright",
        inset = c(0, -0.18),
        legend = panel_series,
        pch = unname(series_markers[panel_series]),
        pt.bg = unname(series_colors[panel_series]),
        col = background,
        pt.cex = 0.95,
        horiz = TRUE,
        bty = "n",
        cex = 0.68,
        xpd = NA,
        x.intersp = 0.65,
        y.intersp = 0.8
      )
    }
  }

  mtext(config$title, side = 3, outer = TRUE, line = 3.6, adj = 0, cex = 1.48, font = 2, col = ink)
  mtext(
    sprintf("%s · estimates and intervals are plotted as supplied; no statistics are recomputed", data_note),
    side = 3,
    outer = TRUE,
    line = 2.0,
    adj = 0,
    cex = 0.76,
    col = muted
  )
  mtext(
    "Additive panels use linear axes; ratio panels require positive estimates and bounds, null = 1, and logarithmic axes.",
    side = 1,
    outer = TRUE,
    line = 2.3,
    adj = 0,
    cex = 0.68,
    col = muted
  )
}

output_prefix <- sub("\\.(png|pdf|svg)$", "", config$output_prefix, ignore.case = TRUE)
output_directory <- dirname(output_prefix)
if (!dir.exists(output_directory)) dir.create(output_directory, recursive = TRUE)
png_path <- paste0(output_prefix, ".png")
pdf_path <- paste0(output_prefix, ".pdf")

grDevices::png(
  filename = png_path,
  width = figure_width,
  height = figure_height,
  units = "in",
  res = config$dpi,
  bg = background,
  type = if (.Platform$OS.type == "windows") "windows" else if (capabilities("cairo")) "cairo" else getOption("bitmapType")
)
draw_figure()
invisible(grDevices::dev.off())

grDevices::pdf(
  file = pdf_path,
  width = figure_width,
  height = figure_height,
  onefile = FALSE,
  bg = background,
  useDingbats = FALSE
)
draw_figure()
invisible(grDevices::dev.off())

panel_summary <- vapply(
  panel_order,
  function(panel_name) sprintf("%s=%d rows", panel_name, sum(data$panel == panel_name)),
  character(1)
)
cat(sprintf("Validated %d estimate rows (%s)\n", nrow(data), paste(panel_summary, collapse = ", ")))
cat(sprintf("Data status: %s\n", data_note))
cat(sprintf("PNG: %s\n", png_path))
cat(sprintf("PDF: %s\n", pdf_path))
