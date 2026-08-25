#!/usr/bin/env Rscript

# Render a generalized raincloud plot from a semantic CSV contract.

DEFAULT_TITLE <- "Group distributions"
DEFAULT_X_LABEL <- "Value"
GOLDEN_FRACTION <- 0.6180339887498949

fail <- function(message_text) {
  stop(message_text, call. = FALSE)
}

usage <- function() {
  paste(
    "Usage: Rscript r/plot.R --input FILE --output-prefix PREFIX",
    "[--title TEXT] [--x-label TEXT]",
    sep = "\n"
  )
}

parse_args <- function(args) {
  config <- list(
    input = NULL,
    output_prefix = NULL,
    title = DEFAULT_TITLE,
    x_label = DEFAULT_X_LABEL
  )

  index <- 1L
  while (index <= length(args)) {
    token <- args[[index]]
    if (token %in% c("--help", "-h")) {
      cat(usage(), "\n")
      quit(save = "no", status = 0L)
    }
    if (!startsWith(token, "--")) {
      fail(paste0("unexpected argument: ", token, "\n", usage()))
    }

    token_body <- substring(token, 3L)
    if (grepl("=", token_body, fixed = TRUE)) {
      pieces <- strsplit(token_body, "=", fixed = TRUE)[[1L]]
      key <- pieces[[1L]]
      value <- paste(pieces[-1L], collapse = "=")
    } else {
      key <- token_body
      if (index == length(args)) {
        fail(paste0("missing value for --", key))
      }
      index <- index + 1L
      value <- args[[index]]
    }
    key <- gsub("-", "_", key, fixed = TRUE)
    if (!key %in% names(config)) {
      fail(paste0("unknown option: --", token_body))
    }
    config[[key]] <- value
    index <- index + 1L
  }

  if (is.null(config$input) || !nzchar(config$input)) {
    fail(paste0("--input is required\n", usage()))
  }
  if (is.null(config$output_prefix) || !nzchar(config$output_prefix)) {
    fail(paste0("--output-prefix is required\n", usage()))
  }
  if (grepl("\\.(png|svg)$", config$output_prefix, ignore.case = TRUE)) {
    fail("--output-prefix must not include .png or .svg")
  }
  config
}

read_input <- function(path) {
  if (!file.exists(path)) {
    fail(paste0("input file does not exist: ", path))
  }

  data <- tryCatch(
    read.csv(
      path,
      header = TRUE,
      check.names = FALSE,
      stringsAsFactors = FALSE,
      colClasses = "character",
      na.strings = character(),
      fileEncoding = "UTF-8-BOM"
    ),
    error = function(error) fail(paste0("could not read CSV: ", conditionMessage(error)))
  )
  if (anyDuplicated(names(data))) {
    fail("input contains duplicate column names")
  }
  missing_columns <- setdiff(c("group", "value"), names(data))
  if (length(missing_columns)) {
    fail(paste0("missing required column(s): ", paste(missing_columns, collapse = ", ")))
  }
  if (!nrow(data)) {
    fail("input contains no observations")
  }

  has_facet <- "facet" %in% names(data)
  has_id <- "id" %in% names(data)
  data$group <- trimws(data$group)
  value_text <- trimws(data$value)
  data$facet <- if (has_facet) trimws(data$facet) else rep("All observations", nrow(data))
  data$id <- if (has_id) trimws(data$id) else paste0("row-", seq_len(nrow(data)) + 1L)

  row_errors <- rep("", nrow(data))
  add_error <- function(current, condition, label) {
    current[condition] <- ifelse(
      nzchar(current[condition]),
      paste(current[condition], label, sep = "; "),
      label
    )
    current
  }
  row_errors <- add_error(row_errors, !nzchar(data$group) | is.na(data$group), "group is empty")
  row_errors <- add_error(row_errors, !nzchar(value_text) | is.na(value_text), "value is empty")
  row_errors <- add_error(row_errors, !nzchar(data$facet) | is.na(data$facet), "facet is empty")
  row_errors <- add_error(row_errors, !nzchar(data$id) | is.na(data$id), "id is empty")

  numeric_value <- suppressWarnings(as.numeric(value_text))
  row_errors <- add_error(
    row_errors,
    nzchar(value_text) & !is.na(value_text) & (is.na(numeric_value) | !is.finite(numeric_value)),
    "value must be finite numeric"
  )
  invalid <- which(nzchar(row_errors))
  if (length(invalid)) {
    displayed <- head(invalid, 10L)
    details <- paste0("row ", displayed + 1L, ": ", row_errors[displayed])
    suffix <- if (length(invalid) > length(displayed)) "\n  (additional errors omitted)" else ""
    fail(paste0(
      "input rows violate the data contract:\n  - ",
      paste(details, collapse = "\n  - "),
      suffix
    ))
  }

  data$value <- numeric_value
  data$source_row <- seq_len(nrow(data)) + 1L
  if (has_id) {
    duplicate_key <- paste(data$facet, data$group, data$id, sep = "\034")
    duplicated_rows <- which(duplicated(duplicate_key) | duplicated(duplicate_key, fromLast = TRUE))
    if (length(duplicated_rows)) {
      displayed <- head(duplicated_rows, 10L)
      details <- paste0(
        "row ", displayed + 1L, ": duplicate (facet, group, id)=('",
        data$facet[displayed], "', '", data$group[displayed], "', '", data$id[displayed], "')"
      )
      fail(paste0(
        "id must be unique within each facet and group:\n  - ",
        paste(details, collapse = "\n  - ")
      ))
    }
  }

  list(
    data = data,
    facet_order = unique(data$facet),
    group_order = unique(data$group),
    has_facet = has_facet,
    has_id = has_id
  )
}

values_for <- function(input_data, facet_name, group_name) {
  rows <- input_data$data$facet == facet_name & input_data$data$group == group_name
  input_data$data$value[rows]
}

rows_for <- function(input_data, facet_name, group_name) {
  rows <- input_data$data$facet == facet_name & input_data$data$group == group_name
  input_data$data[rows, , drop = FALSE]
}

density_profile <- function(values, grid) {
  if (length(values) < 3L) {
    return(list(y = NULL, bandwidth = NULL, status = "skipped: n < 3"))
  }
  if (length(unique(values)) < 3L) {
    return(list(y = NULL, bandwidth = NULL, status = "skipped: fewer than 3 distinct values"))
  }

  standard_deviation <- sd(values)
  scale_value <- max(1, max(abs(values)))
  if (!is.finite(standard_deviation) || standard_deviation <= .Machine$double.eps * scale_value) {
    return(list(y = NULL, bandwidth = NULL, status = "skipped: zero or near-zero variance"))
  }
  bandwidth <- standard_deviation * length(values)^(-0.2)
  if (!is.finite(bandwidth) || bandwidth <= .Machine$double.eps * scale_value) {
    return(list(y = NULL, bandwidth = NULL, status = "skipped: invalid bandwidth"))
  }

  estimate <- density(
    values,
    bw = bandwidth,
    kernel = "gaussian",
    from = min(grid),
    to = max(grid),
    n = length(grid),
    cut = 0
  )
  if (!all(is.finite(estimate$y)) || max(estimate$y) <= 0) {
    return(list(y = NULL, bandwidth = bandwidth, status = "skipped: density evaluation failed"))
  }
  list(y = estimate$y, bandwidth = bandwidth, status = "drawn")
}

box_statistics <- function(values) {
  quartiles <- quantile(values, probs = c(0.25, 0.5, 0.75), type = 7, names = FALSE)
  q1 <- quartiles[[1L]]
  median_value <- quartiles[[2L]]
  q3 <- quartiles[[3L]]
  iqr <- q3 - q1
  lower_values <- values[values >= q1 - 1.5 * iqr]
  upper_values <- values[values <= q3 + 1.5 * iqr]
  c(min(lower_values), q1, median_value, q3, max(upper_values))
}

global_limits <- function(values) {
  limits <- range(values)
  span <- diff(limits)
  if (span <= 0) {
    padding <- max(abs(limits[[1L]]) * 0.1, 1)
  } else {
    overall_sd <- if (length(values) > 1L) sd(values) else 0
    padding <- max(0.06 * span, 0.25 * overall_sd)
  }
  c(limits[[1L]] - padding, limits[[2L]] + padding)
}

figure_geometry <- function(input_data) {
  facet_count <- length(input_data$facet_order)
  columns <- if (facet_count == 1L) 1L else if (facet_count <= 4L) 2L else min(3L, facet_count)
  rows <- ceiling(facet_count / columns)
  groups_per_facet <- vapply(
    input_data$facet_order,
    function(facet_name) length(unique(input_data$data$group[input_data$data$facet == facet_name])),
    integer(1L)
  )
  labels <- unlist(lapply(input_data$facet_order, function(facet_name) {
    present <- input_data$group_order[input_data$group_order %in% input_data$data$group[input_data$data$facet == facet_name]]
    vapply(
      present,
      function(group_name) paste0(group_name, "  n=", nrow(rows_for(input_data, facet_name, group_name))),
      character(1L)
    )
  }))
  maximum_label_length <- max(nchar(labels, type = "width"))
  panel_width <- min(9.6, max(7.2, 6.7 + 0.075 * maximum_label_length))
  panel_height <- max(4.2, 1.02 * max(groups_per_facet) + 1.7)
  list(
    rows = rows,
    columns = columns,
    width = panel_width * columns,
    height = panel_height * rows,
    maximum_label_length = maximum_label_length
  )
}

report_data <- function(input_data, grid) {
  cat(sprintf(
    "Loaded %d rows: %d facet(s), %d group(s); 0 rows excluded.\n",
    nrow(input_data$data),
    length(input_data$facet_order),
    length(input_data$group_order)
  ))
  cat("facet | group | n | min | median | max | KDE\n")
  for (facet_name in input_data$facet_order) {
    for (group_name in input_data$group_order) {
      values <- values_for(input_data, facet_name, group_name)
      if (!length(values)) next
      profile <- density_profile(values, grid)
      kde_text <- profile$status
      if (!is.null(profile$bandwidth) && identical(profile$status, "drawn")) {
        kde_text <- paste0(kde_text, " (bandwidth=", format(profile$bandwidth, digits = 6), ")")
      }
      cat(sprintf(
        "%s | %s | %d | %s | %s | %s | %s\n",
        facet_name,
        group_name,
        length(values),
        format(min(values), digits = 6),
        format(median(values), digits = 6),
        format(max(values), digits = 6),
        kde_text
      ))
    }
  }
}

draw_figure <- function(input_data, title_text, x_label, geometry, x_limits, grid, colors) {
  left_margin <- min(19, max(7, 4.2 + 0.30 * geometry$maximum_label_length))
  label_cex <- if (geometry$maximum_label_length <= 24) 0.86 else if (geometry$maximum_label_length <= 40) 0.76 else 0.68
  par(
    mfrow = c(geometry$rows, geometry$columns),
    mar = c(3.0, left_margin, if (input_data$has_facet) 2.0 else 1.0, 0.8),
    oma = c(4.4, 0.4, 3.3, 0.4),
    mgp = c(1.8, 0.55, 0),
    tcl = -0.25,
    family = "sans",
    bg = "white"
  )

  for (facet_name in input_data$facet_order) {
    groups <- input_data$group_order[
      input_data$group_order %in% input_data$data$group[input_data$data$facet == facet_name]
    ]
    y_positions <- rev(seq_along(groups))
    plot.new()
    plot.window(
      xlim = x_limits,
      ylim = c(0.20, length(groups) + 0.53),
      xaxs = "i",
      yaxs = "i"
    )
    x_ticks <- pretty(x_limits)
    abline(v = x_ticks, col = "#E7EAF0", lwd = 0.65)

    labels <- character(length(groups))
    for (group_index in seq_along(groups)) {
      group_name <- groups[[group_index]]
      y_base <- y_positions[[group_index]]
      group_rows <- rows_for(input_data, facet_name, group_name)
      values <- group_rows$value
      color <- colors[[group_name]]
      profile <- density_profile(values, grid)

      segments(x_limits[[1L]], y_base, x_limits[[2L]], y_base, col = "#D9DEE5", lwd = 0.7)
      if (!is.null(profile$y)) {
        scaled <- profile$y / max(profile$y) * 0.42
        polygon(
          c(grid, rev(grid)),
          c(rep(y_base, length(grid)), rev(y_base + scaled)),
          border = adjustcolor(color, alpha.f = 0.9),
          col = adjustcolor(color, alpha.f = 0.32),
          lwd = 1
        )
      }

      stats <- box_statistics(values)
      lower <- stats[[1L]]
      q1 <- stats[[2L]]
      median_value <- stats[[3L]]
      q3 <- stats[[4L]]
      upper <- stats[[5L]]
      box_y <- y_base - 0.27
      segments(lower, box_y, upper, box_y, col = "#30343B", lwd = 1)
      segments(lower, box_y - 0.06, lower, box_y + 0.06, col = "#30343B", lwd = 1)
      segments(upper, box_y - 0.06, upper, box_y + 0.06, col = "#30343B", lwd = 1)
      rect(q1, box_y - 0.075, q3, box_y + 0.075, col = "white", border = "#30343B", lwd = 1)
      segments(median_value, box_y - 0.075, median_value, box_y + 0.075, col = color, lwd = 1.6)

      point_order <- order(values, group_rows$id, group_rows$source_row)
      point_values <- values[point_order]
      offsets <- (((seq_along(values) * GOLDEN_FRACTION) %% 1) - 0.5) * 0.22
      point_y <- y_base - 0.50 + offsets
      point_cex <- max(0.32, min(0.75, 0.86 - 0.13 * log10(length(values) + 1)))
      point_alpha <- if (length(values) <= 500L) 0.50 else 0.25
      points(
        point_values,
        point_y,
        pch = 16,
        cex = point_cex,
        col = adjustcolor(color, alpha.f = point_alpha)
      )
      labels[[group_index]] <- paste0(group_name, "  n=", length(values))
    }

    axis(1, at = x_ticks, labels = format(x_ticks, trim = TRUE), cex.axis = 0.82, col = "#747B85", col.axis = "#4A5058")
    axis(2, at = y_positions, labels = labels, las = 1, tick = FALSE, cex.axis = label_cex, col.axis = "#30343B")
    box(bty = "l", col = "#747B85", lwd = 0.8)
    if (input_data$has_facet) {
      mtext(facet_name, side = 3, line = 0.45, adj = 0, font = 2, cex = 1.0, col = "#20242A")
    }
  }

  unused_panels <- geometry$rows * geometry$columns - length(input_data$facet_order)
  if (unused_panels > 0L) {
    for (index in seq_len(unused_panels)) plot.new()
  }

  facet_word <- if (length(input_data$facet_order) == 1L) "facet" else "facets"
  subtitle <- sprintf(
    "%d observations · %d groups · %d %s",
    nrow(input_data$data),
    length(input_data$group_order),
    length(input_data$facet_order),
    facet_word
  )
  mtext(title_text, side = 3, outer = TRUE, line = 1.25, adj = 0, font = 2, cex = 1.35, col = "#20242A")
  mtext(subtitle, side = 3, outer = TRUE, line = 0.05, adj = 0, cex = 0.82, col = "#59616B")
  mtext(x_label, side = 1, outer = TRUE, line = 1.45, cex = 0.95, col = "#20242A")
  mtext(
    "Each KDE is independently scaled within its group; sparse or constant groups omit KDE.",
    side = 1,
    outer = TRUE,
    line = 3.25,
    adj = 0,
    cex = 0.68,
    col = "#68717C"
  )
}

render_output <- function(kind, path, geometry, draw_callback) {
  if (identical(kind, "png")) {
    png(
      path,
      width = geometry$width,
      height = geometry$height,
      units = "in",
      res = 300,
      type = if (capabilities("cairo")) "cairo" else getOption("bitmapType")
    )
  } else if (identical(kind, "svg")) {
    svg(path, width = geometry$width, height = geometry$height, onefile = TRUE, bg = "white", family = "sans")
  } else {
    fail(paste0("unsupported output kind: ", kind))
  }

  device_id <- dev.cur()
  on.exit({
    if (dev.cur() == device_id) dev.off()
  }, add = FALSE)
  draw_callback()
  dev.off()
  on.exit(NULL, add = FALSE)
}

main <- function() {
  config <- parse_args(commandArgs(trailingOnly = TRUE))
  input_data <- read_input(config$input)
  all_values <- input_data$data$value
  x_limits <- global_limits(all_values)
  grid <- seq(x_limits[[1L]], x_limits[[2L]], length.out = 512L)
  geometry <- figure_geometry(input_data)
  colors <- setNames(hcl.colors(length(input_data$group_order), palette = "Dark 3"), input_data$group_order)

  output_directory <- dirname(config$output_prefix)
  if (!dir.exists(output_directory)) {
    dir.create(output_directory, recursive = TRUE, showWarnings = FALSE)
  }
  if (!dir.exists(output_directory)) {
    fail(paste0("could not create output directory: ", output_directory))
  }

  draw_callback <- function() {
    draw_figure(input_data, config$title, config$x_label, geometry, x_limits, grid, colors)
  }
  png_path <- paste0(config$output_prefix, ".png")
  svg_path <- paste0(config$output_prefix, ".svg")
  render_output("png", png_path, geometry, draw_callback)
  render_output("svg", svg_path, geometry, draw_callback)
  report_data(input_data, grid)
  cat("Wrote ", png_path, "\n", sep = "")
  cat("Wrote ", svg_path, "\n", sep = "")
}

status <- tryCatch(
  {
    main()
    0L
  },
  error = function(error) {
    message("ERROR: ", conditionMessage(error))
    2L
  }
)
quit(save = "no", status = status)
