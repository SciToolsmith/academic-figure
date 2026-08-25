#!/usr/bin/env Rscript

# Render validated ordered-response curves from a long-form CSV using base R.

all_args <- commandArgs(trailingOnly = FALSE)
file_arg <- sub("^--file=", "", all_args[grep("^--file=", all_args)])
script_dir <- if (length(file_arg)) {
  dirname(normalizePath(file_arg[[1]], mustWork = TRUE))
} else {
  getwd()
}
template_dir <- dirname(script_dir)

defaults <- list(
  input = file.path(template_dir, "demo", "demo_simulated_seed164.csv"),
  output_prefix = file.path(getwd(), "ordered_response_r"),
  title = "Ordered response curves",
  x_label = "Ordered input",
  y_label = "Response",
  dpi = 320L
)

parse_args <- function(args, defaults) {
  values <- defaults
  aliases <- c(
    input = "input",
    `output-prefix` = "output_prefix",
    title = "title",
    `x-label` = "x_label",
    `y-label` = "y_label",
    dpi = "dpi"
  )
  index <- 1L
  while (index <= length(args)) {
    token <- args[[index]]
    if (!startsWith(token, "--")) {
      stop(sprintf("Unknown argument: %s", token), call. = FALSE)
    }
    stripped <- substring(token, 3L)
    if (grepl("=", stripped, fixed = TRUE)) {
      pieces <- strsplit(stripped, "=", fixed = TRUE)[[1]]
      key <- pieces[[1]]
      value <- paste(pieces[-1], collapse = "=")
    } else {
      key <- stripped
      index <- index + 1L
      if (index > length(args)) {
        stop(sprintf("Missing value for --%s", key), call. = FALSE)
      }
      value <- args[[index]]
    }
    if (!key %in% names(aliases)) {
      stop(sprintf("Unknown option: --%s", key), call. = FALSE)
    }
    values[[aliases[[key]]]] <- value
    index <- index + 1L
  }
  dpi_value <- suppressWarnings(as.integer(values$dpi))
  if (is.na(dpi_value) || dpi_value < 150L) {
    stop("--dpi must be an integer of at least 150.", call. = FALSE)
  }
  values$dpi <- dpi_value
  values
}

stop_contract <- function(message) {
  stop(sprintf("Input validation failed: %s", message), call. = FALSE)
}

column_or_blank <- function(data, column) {
  if (column %in% names(data)) trimws(data[[column]]) else rep("", nrow(data))
}

parse_number <- function(value, field, row_number) {
  text <- trimws(value)
  if (!nzchar(text)) {
    stop_contract(sprintf("CSV row %d: '%s' must not be blank.", row_number, field))
  }
  number <- suppressWarnings(as.numeric(text))
  if (is.na(number) || !is.finite(number)) {
    stop_contract(sprintf(
      "CSV row %d: '%s' must be a finite numeric value, got '%s'.",
      row_number, field, text
    ))
  }
  number
}

ordered_unique <- function(values) values[!duplicated(values)]

read_and_validate <- function(path) {
  if (!file.exists(path) || dir.exists(path)) {
    stop_contract(sprintf("Input CSV does not exist: %s", path))
  }
  data <- tryCatch(
    utils::read.csv(
      path,
      stringsAsFactors = FALSE,
      check.names = FALSE,
      colClasses = "character",
      na.strings = character(),
      strip.white = FALSE
    ),
    error = function(error) stop_contract(conditionMessage(error))
  )
  if (!ncol(data)) stop_contract("Input CSV has no header row.")
  names(data) <- trimws(names(data))
  if (any(!nzchar(names(data)))) stop_contract("CSV headers must not be blank.")
  if (anyDuplicated(names(data))) stop_contract("CSV headers must be unique.")

  required <- c("series", "group", "x", "y", "data_mode")
  missing <- setdiff(required, names(data))
  if (length(missing)) {
    stop_contract(sprintf("Missing required columns: %s", paste(missing, collapse = ", ")))
  }
  if (!nrow(data)) stop_contract("Input CSV contains no data rows.")

  nonblank <- apply(data, 1L, function(row) any(nzchar(trimws(row))))
  data <- data[nonblank, , drop = FALSE]
  if (!nrow(data)) stop_contract("Input CSV contains no data rows.")

  result <- data.frame(
    source_row = seq_len(nrow(data)) + 1L,
    series = trimws(data$series),
    group = trimws(data$group),
    x = rep(NA_real_, nrow(data)),
    y = rep(NA_real_, nrow(data)),
    data_mode = tolower(trimws(data$data_mode)),
    replicate = column_or_blank(data, "replicate"),
    panel = column_or_blank(data, "panel"),
    y_lower = rep(NA_real_, nrow(data)),
    y_upper = rep(NA_real_, nrow(data)),
    x_scale = tolower(column_or_blank(data, "x_scale")),
    data_status = toupper(column_or_blank(data, "data_status")),
    simulation_seed = column_or_blank(data, "simulation_seed"),
    stringsAsFactors = FALSE
  )
  result$panel[!nzchar(result$panel)] <- "Ordered response"
  result$x_scale[!nzchar(result$x_scale)] <- "linear"

  for (index in seq_len(nrow(result))) {
    csv_row <- result$source_row[[index]]
    if (!nzchar(result$series[[index]])) {
      stop_contract(sprintf("CSV row %d: 'series' must not be blank.", csv_row))
    }
    if (!nzchar(result$group[[index]])) {
      stop_contract(sprintf("CSV row %d: 'group' must not be blank.", csv_row))
    }
    if (!result$data_mode[[index]] %in% c("raw", "summary")) {
      stop_contract(sprintf(
        "CSV row %d: 'data_mode' must be 'raw' or 'summary'.", csv_row
      ))
    }
    if (!result$x_scale[[index]] %in% c("linear", "log")) {
      stop_contract(sprintf(
        "CSV row %d: 'x_scale' must be 'linear' or 'log'.", csv_row
      ))
    }

    result$x[[index]] <- parse_number(data$x[[index]], "x", csv_row)
    result$y[[index]] <- parse_number(data$y[[index]], "y", csv_row)
    lower_text <- column_or_blank(data, "y_lower")[[index]]
    upper_text <- column_or_blank(data, "y_upper")[[index]]
    if (xor(nzchar(lower_text), nzchar(upper_text))) {
      stop_contract(sprintf(
        "CSV row %d: provide both 'y_lower' and 'y_upper', or neither.", csv_row
      ))
    }
    if (nzchar(lower_text)) {
      result$y_lower[[index]] <- parse_number(lower_text, "y_lower", csv_row)
      result$y_upper[[index]] <- parse_number(upper_text, "y_upper", csv_row)
      if (!(result$y_lower[[index]] < result$y_upper[[index]])) {
        stop_contract(sprintf("CSV row %d: require y_lower < y_upper.", csv_row))
      }
      if (!(result$y_lower[[index]] <= result$y[[index]] &&
            result$y[[index]] <= result$y_upper[[index]])) {
        stop_contract(sprintf(
          "CSV row %d: y must lie inside [y_lower, y_upper].", csv_row
        ))
      }
    }
    if (result$data_mode[[index]] == "raw" && !is.na(result$y_lower[[index]])) {
      stop_contract(sprintf(
        "CSV row %d: raw rows cannot supply precomputed intervals.", csv_row
      ))
    }
    if (result$data_mode[[index]] == "summary" && nzchar(result$replicate[[index]])) {
      stop_contract(sprintf(
        "CSV row %d: summary rows cannot carry a replicate identifier.", csv_row
      ))
    }
    if (result$x_scale[[index]] == "log" && result$x[[index]] <= 0) {
      stop_contract(sprintf(
        "CSV row %d: logarithmic x requires x > 0.", csv_row
      ))
    }
  }

  statuses <- ordered_unique(result$data_status[nzchar(result$data_status)])
  seeds <- ordered_unique(result$simulation_seed[nzchar(result$simulation_seed)])
  if (length(statuses) > 1L) stop_contract("'data_status' must be constant across the file.")
  if (length(seeds) > 1L) stop_contract("'simulation_seed' must be constant across the file.")
  if (identical(statuses, "SIMULATED")) {
    if (any(result$data_status != "SIMULATED")) {
      stop_contract("Every simulated row must declare data_status=SIMULATED.")
    }
    if (length(seeds) != 1L || any(!nzchar(result$simulation_seed))) {
      stop_contract("Simulated data must provide one fixed simulation_seed on every row.")
    }
    seed_number <- suppressWarnings(as.integer(seeds[[1]]))
    if (is.na(seed_number) || seed_number <= 0L || as.character(seed_number) != seeds[[1]]) {
      stop_contract("simulation_seed must be a positive integer.")
    }
    data_note <- sprintf("SIMULATED DEMONSTRATION DATA · fixed seed %d", seed_number)
  } else {
    if (length(seeds)) {
      stop_contract("simulation_seed is only valid when data_status is SIMULATED.")
    }
    data_note <- "SOURCE-SUPPLIED DATA"
  }

  panel_names <- ordered_unique(result$panel)
  for (panel_name in panel_names) {
    panel_rows <- result[result$panel == panel_name, , drop = FALSE]
    modes <- unique(panel_rows$data_mode)
    scales <- unique(panel_rows$x_scale)
    if (length(modes) != 1L) {
      stop_contract(sprintf(
        "Panel '%s' mixes raw and summary rows; split them into panels.", panel_name
      ))
    }
    if (length(scales) != 1L) {
      stop_contract(sprintf("Panel '%s' mixes linear and log x scales.", panel_name))
    }

    curves <- unique(panel_rows[c("group", "series")])
    for (curve_index in seq_len(nrow(curves))) {
      group_name <- curves$group[[curve_index]]
      series_name <- curves$series[[curve_index]]
      curve_rows <- panel_rows[
        panel_rows$group == group_name & panel_rows$series == series_name,
        ,
        drop = FALSE
      ]
      if (length(unique(curve_rows$x)) < 2L) {
        stop_contract(sprintf(
          "Panel '%s', group '%s', series '%s' needs at least two distinct numeric x values.",
          panel_name, group_name, series_name
        ))
      }
      for (x_value in unique(curve_rows$x)) {
        cluster <- curve_rows[curve_rows$x == x_value, , drop = FALSE]
        if (modes[[1]] == "summary" && nrow(cluster) > 1L) {
          stop_contract(sprintf(
            "Summary rows must be unique by panel/group/series/x; duplicate x=%g in panel '%s'.",
            x_value, panel_name
          ))
        }
        if (modes[[1]] == "raw" && nrow(cluster) > 1L) {
          if (any(!nzchar(cluster$replicate))) {
            stop_contract(sprintf(
              paste0(
                "Repeated raw observations at x=%g in panel '%s', group '%s', ",
                "series '%s' require nonblank replicate identifiers."
              ),
              x_value, panel_name, group_name, series_name
            ))
          }
          if (anyDuplicated(cluster$replicate)) {
            stop_contract(sprintf(
              "Raw replicate identifiers must be unique within each panel/group/series/x cluster (x=%g).",
              x_value
            ))
          }
        }
      }
    }
  }

  list(data = result, data_note = data_note)
}

axis_limits <- function(values, logarithmic = FALSE) {
  limits <- range(values, finite = TRUE)
  if (logarithmic) {
    logged <- log(limits)
    span <- diff(logged)
    padding <- max(0.07 * span, 0.08)
    return(exp(logged + c(-padding, padding)))
  }
  span <- diff(limits)
  padding <- max(0.07 * span, 0.04 * max(abs(limits), 1))
  limits + c(-padding, padding)
}

curve_label <- function(group_name, series_name, panel_groups, panel_series) {
  if (length(panel_groups) > 1L && length(panel_series) > 1L) {
    return(paste(group_name, series_name, sep = " · "))
  }
  if (length(panel_groups) > 1L) return(group_name)
  if (length(panel_series) > 1L) return(series_name)
  if (group_name != series_name) paste(group_name, series_name, sep = " · ") else group_name
}

draw_figure <- function(data, data_note, options) {
  background <- "#FBFAF7"
  ink <- "#20282C"
  muted <- "#627078"
  grid_color <- "#E5E2DC"
  palette <- c(
    "#287D9B", "#D96B35", "#4F8A5B", "#8D65A8",
    "#B68A1F", "#5875B5", "#B64E68", "#477E79"
  )
  line_types <- c(1, 2, 3, 4)
  point_types <- c(21, 22, 24, 23, 25, 21, 22, 24, 23)
  panel_names <- ordered_unique(data$panel)
  group_names <- ordered_unique(data$group)
  series_names <- ordered_unique(data$series)
  group_colors <- stats::setNames(rep(palette, length.out = length(group_names)), group_names)
  series_lty <- stats::setNames(rep(line_types, length.out = length(series_names)), series_names)
  series_pch <- stats::setNames(rep(point_types, length.out = length(series_names)), series_names)

  longest_panel <- max(nchar(panel_names))
  columns <- if (length(panel_names) == 1L || longest_panel > 34L) 1L else min(2L, length(panel_names))
  rows <- ceiling(length(panel_names) / columns)
  graphics::par(
    mfrow = c(rows, columns),
    mar = c(4.4, 4.5, 3.7, 1.2),
    oma = c(2.8, 0.4, 4.2, 0.4),
    bg = background,
    fg = ink,
    col.axis = "#425159",
    col.lab = ink,
    family = "sans"
  )

  for (panel_name in panel_names) {
    panel_data <- data[data$panel == panel_name, , drop = FALSE]
    mode <- panel_data$data_mode[[1]]
    scale <- panel_data$x_scale[[1]]
    panel_groups <- ordered_unique(panel_data$group)
    panel_series <- ordered_unique(panel_data$series)
    curves <- unique(panel_data[c("group", "series")])
    x_limits <- axis_limits(panel_data$x, logarithmic = scale == "log")
    y_values <- c(panel_data$y, panel_data$y_lower, panel_data$y_upper)
    y_limits <- axis_limits(y_values[is.finite(y_values)])

    graphics::plot.new()
    graphics::plot.window(
      xlim = x_limits,
      ylim = y_limits,
      log = if (scale == "log") "x" else ""
    )
    x_ticks <- graphics::axTicks(1)
    y_ticks <- graphics::axTicks(2)
    graphics::abline(v = x_ticks, h = y_ticks, col = grid_color, lwd = 0.65)
    graphics::axis(1, cex.axis = 0.86, col = "#6D7A80", col.axis = "#425159")
    graphics::axis(2, las = 1, cex.axis = 0.86, col = "#6D7A80", col.axis = "#425159")
    graphics::box(bty = "l", col = "#6D7A80")
    graphics::mtext(options$x_label, side = 1, line = 2.6, cex = 0.92)
    graphics::mtext(options$y_label, side = 2, line = 3.0, cex = 0.92)
    graphics::mtext(panel_name, side = 3, line = 1.45, adj = 0, cex = 1.15, font = 2)
    panel_note <- if (mode == "raw") {
      "RAW: points are observations; lines connect arithmetic means at supplied x"
    } else {
      "SUMMARY: points and intervals are plotted exactly as supplied"
    }
    graphics::mtext(panel_note, side = 3, line = 0.35, adj = 0, cex = 0.72, col = muted)

    legend_labels <- character(nrow(curves))
    legend_colors <- character(nrow(curves))
    legend_lty <- integer(nrow(curves))
    legend_pch <- integer(nrow(curves))
    for (curve_index in seq_len(nrow(curves))) {
      group_name <- curves$group[[curve_index]]
      series_name <- curves$series[[curve_index]]
      curve_data <- panel_data[
        panel_data$group == group_name & panel_data$series == series_name,
        ,
        drop = FALSE
      ]
      color <- unname(group_colors[[group_name]])
      lty <- unname(series_lty[[series_name]])
      pch <- unname(series_pch[[series_name]])

      if (mode == "raw") {
        graphics::points(
          curve_data$x,
          curve_data$y,
          pch = pch,
          cex = 0.72,
          col = grDevices::adjustcolor(color, alpha.f = 0.75),
          bg = grDevices::adjustcolor(color, alpha.f = 0.33),
          lwd = 0.45
        )
        ordered_x <- sort(unique(curve_data$x))
        ordered_y <- vapply(
          ordered_x,
          function(x_value) mean(curve_data$y[curve_data$x == x_value]),
          numeric(1)
        )
      } else {
        curve_data <- curve_data[order(curve_data$x), , drop = FALSE]
        ordered_x <- curve_data$x
        ordered_y <- curve_data$y
        with_intervals <- is.finite(curve_data$y_lower) & is.finite(curve_data$y_upper)
        if (any(with_intervals)) {
          graphics::arrows(
            x0 = curve_data$x[with_intervals],
            y0 = curve_data$y_lower[with_intervals],
            x1 = curve_data$x[with_intervals],
            y1 = curve_data$y_upper[with_intervals],
            angle = 90,
            code = 3,
            length = 0.035,
            col = grDevices::adjustcolor(color, alpha.f = 0.72),
            lwd = 1.0
          )
        }
      }
      graphics::lines(ordered_x, ordered_y, col = color, lty = lty, lwd = 1.65)
      graphics::points(
        ordered_x,
        ordered_y,
        pch = pch,
        cex = 0.9,
        col = "white",
        bg = color,
        lwd = 0.65
      )

      legend_labels[[curve_index]] <- curve_label(
        group_name, series_name, panel_groups, panel_series
      )
      legend_colors[[curve_index]] <- color
      legend_lty[[curve_index]] <- lty
      legend_pch[[curve_index]] <- pch
    }

    graphics::legend(
      "topright",
      legend = legend_labels,
      col = legend_colors,
      lty = legend_lty,
      pch = legend_pch,
      pt.bg = legend_colors,
      lwd = 1.45,
      pt.cex = 0.85,
      cex = max(0.62, 0.80 - 0.015 * max(0, nrow(curves) - 4L)),
      ncol = if (nrow(curves) > 6L) 2L else 1L,
      bty = "o",
      bg = grDevices::adjustcolor(background, alpha.f = 0.92),
      box.col = "#D7D5CF"
    )
  }

  unused <- rows * columns - length(panel_names)
  if (unused > 0L) for (index in seq_len(unused)) graphics::plot.new()
  graphics::mtext(options$title, side = 3, outer = TRUE, line = 2.25, adj = 0.02, cex = 1.75, font = 2)
  graphics::mtext(data_note, side = 3, outer = TRUE, line = 0.85, adj = 0.02, cex = 0.88, col = muted)
  graphics::mtext(
    paste0(
      "Lines follow numerically ordered supplied x positions. No smoothing, ",
      "unsampled-x interpolation, or peak-based statistical inference is performed."
    ),
    side = 1,
    outer = TRUE,
    line = 1.1,
    adj = 0.02,
    cex = 0.72,
    col = muted
  )
}

options <- parse_args(commandArgs(trailingOnly = TRUE), defaults)
validated <- read_and_validate(options$input)
data <- validated$data
panel_names <- ordered_unique(data$panel)
longest_panel <- max(nchar(panel_names))
columns <- if (length(panel_names) == 1L || longest_panel > 34L) 1L else min(2L, length(panel_names))
rows <- ceiling(length(panel_names) / columns)
device_width <- columns * 6.35
device_height <- 1.45 + rows * 4.15

prefix <- file.path(
  dirname(options$output_prefix),
  tools::file_path_sans_ext(basename(options$output_prefix))
)
dir.create(dirname(prefix), recursive = TRUE, showWarnings = FALSE)
png_path <- paste0(prefix, ".png")
pdf_path <- paste0(prefix, ".pdf")

grDevices::png(
  png_path,
  width = device_width,
  height = device_height,
  units = "in",
  res = options$dpi,
  bg = "#FBFAF7"
)
draw_figure(data, validated$data_note, options)
grDevices::dev.off()

grDevices::pdf(
  pdf_path,
  width = device_width,
  height = device_height,
  bg = "#FBFAF7",
  onefile = TRUE
)
draw_figure(data, validated$data_note, options)
grDevices::dev.off()

panel_summaries <- vapply(panel_names, function(panel_name) {
  panel_data <- data[data$panel == panel_name, , drop = FALSE]
  sprintf(
    "%s=%d %s rows (%s x)",
    panel_name,
    nrow(panel_data),
    panel_data$data_mode[[1]],
    panel_data$x_scale[[1]]
  )
}, character(1))
message(sprintf("Validated %d rows: %s", nrow(data), paste(panel_summaries, collapse = "; ")))
message(sprintf("Data status: %s", validated$data_note))
message(sprintf("PNG: %s", normalizePath(png_path, mustWork = TRUE)))
message(sprintf("PDF: %s", normalizePath(pdf_path, mustWork = TRUE)))
