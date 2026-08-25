#!/usr/bin/env Rscript

MAX_COMPONENTS <- 20L
MAX_SAMPLES_PER_FACET <- 60L

fail <- function(text) stop(text, call. = FALSE)
ordered_unique <- function(values) values[!duplicated(values)]
sample_key <- function(facet, sample) paste(facet, sample, sep = "\034")

parse_args <- function(args) {
  config <- list(
    input = NULL,
    style = NULL,
    output_prefix = NULL,
    input_mode = NULL,
    normalize = NULL,
    sum_tolerance = "1e-6",
    sample_order = "input",
    title = "Faceted composition",
    value_label = "Value"
  )
  index <- 1L
  while (index <= length(args)) {
    token <- args[[index]]
    if (!startsWith(token, "--")) fail(paste0("unexpected argument: ", token))
    body <- substring(token, 3L)
    if (grepl("=", body, fixed = TRUE)) {
      pieces <- strsplit(body, "=", fixed = TRUE)[[1L]]
      key <- pieces[[1L]]
      value <- paste(pieces[-1L], collapse = "=")
    } else {
      key <- body
      if (index == length(args)) fail(paste0("missing value for --", key))
      index <- index + 1L
      value <- args[[index]]
    }
    key <- gsub("-", "_", key, fixed = TRUE)
    if (!key %in% names(config)) fail(paste0("unknown option: --", body))
    config[[key]] <- value
    index <- index + 1L
  }
  for (required in c("input", "output_prefix", "input_mode", "normalize")) {
    if (is.null(config[[required]]) || !nzchar(config[[required]])) fail(paste0("--", gsub("_", "-", required), " is required"))
  }
  if (!config$input_mode %in% c("proportion", "value")) fail("--input-mode must be proportion or value")
  if (!tolower(config$normalize) %in% c("true", "false")) fail("--normalize must be true or false")
  config$normalize <- tolower(config$normalize) == "true"
  if (config$input_mode == "proportion" && config$normalize) fail("proportion input is already normalized; use --normalize false")
  tolerance <- suppressWarnings(as.numeric(config$sum_tolerance))
  if (length(tolerance) != 1L || !is.finite(tolerance) || tolerance < 0) fail("--sum-tolerance must be finite and non-negative")
  config$sum_tolerance <- tolerance
  if (!config$sample_order %in% c("input", "alphabetical", "total-desc")) fail("--sample-order must be input, alphabetical or total-desc")
  if (grepl("\\.(png|svg)$", config$output_prefix, ignore.case = TRUE)) fail("--output-prefix must not include .png or .svg")
  config
}

read_style <- function(path, components) {
  if (is.null(path)) {
    return(data.frame(
      component = components,
      label = components,
      color = hcl.colors(length(components), palette = "Dark 3"),
      order = seq_along(components),
      stringsAsFactors = FALSE
    ))
  }
  if (!file.exists(path)) fail(paste0("style file does not exist: ", path))
  style <- read.csv(
    path,
    header = TRUE,
    check.names = FALSE,
    stringsAsFactors = FALSE,
    colClasses = "character",
    na.strings = character(),
    fileEncoding = "UTF-8-BOM"
  )
  required <- c("component", "label", "color", "order")
  if (!all(required %in% names(style))) fail(paste0("style must contain: ", paste(required, collapse = ", ")))
  for (field in required) style[[field]] <- trimws(style[[field]])
  order_value <- suppressWarnings(as.integer(style$order))
  if (any(!nzchar(style$component)) || any(!nzchar(style$label)) || any(!grepl("^#[0-9A-Fa-f]{6}$", style$color)) || any(is.na(order_value)) || any(order_value < 1L)) {
    fail("style contains an invalid component, label, #RRGGBB color, or order")
  }
  style$order <- order_value
  if (anyDuplicated(style$component) || anyDuplicated(style$order) || anyDuplicated(toupper(style$color))) {
    fail("style component, order and color values must be unique")
  }
  if (!setequal(style$component, components) || nrow(style) != length(components)) {
    fail("style must list every observed component exactly once")
  }
  style[order(style$order), , drop = FALSE]
}

read_data <- function(config) {
  if (!file.exists(config$input)) fail(paste0("input file does not exist: ", config$input))
  data <- read.csv(
    config$input,
    header = TRUE,
    check.names = FALSE,
    stringsAsFactors = FALSE,
    colClasses = "character",
    na.strings = character(),
    fileEncoding = "UTF-8-BOM"
  )
  required <- c("facet", "sample", "component", "value")
  if (!all(required %in% names(data))) fail(paste0("input must contain: ", paste(required, collapse = ", ")))
  if (anyDuplicated(names(data))) fail("input contains duplicate column names")
  if (!nrow(data)) fail("input contains no composition rows")
  for (field in c("facet", "sample", "component")) data[[field]] <- trimws(data[[field]])
  value_text <- trimws(data$value)
  if (any(!nzchar(data$facet)) || any(!nzchar(data$sample)) || any(!nzchar(data$component)) || any(!nzchar(value_text))) {
    fail("facet, sample, component and value are required")
  }
  value <- suppressWarnings(as.numeric(value_text))
  if (any(is.na(value)) || any(!is.finite(value)) || any(value < 0)) fail("value must be finite and nonnegative")
  data$value <- value
  key <- paste(data$facet, data$sample, data$component, sep = "\034")
  if (anyDuplicated(key)) fail("duplicate (facet, sample, component) key")
  components <- ordered_unique(data$component)
  if (length(components) > MAX_COMPONENTS) fail(paste0("found ", length(components), " components; maximum readable legend is ", MAX_COMPONENTS))
  facet_order <- ordered_unique(data$facet)
  sample_table <- unique(data[c("facet", "sample")])
  for (facet_name in facet_order) {
    count <- sum(sample_table$facet == facet_name)
    if (count > MAX_SAMPLES_PER_FACET) fail(paste0("facet ", facet_name, " has ", count, " samples; maximum is ", MAX_SAMPLES_PER_FACET))
  }
  for (index in seq_len(nrow(sample_table))) {
    facet_name <- sample_table$facet[[index]]
    sample_name <- sample_table$sample[[index]]
    present <- data$component[data$facet == facet_name & data$sample == sample_name]
    if (!setequal(present, components) || length(present) != length(components)) {
      missing <- setdiff(components, present)
      fail(paste0(
        "sample ('", facet_name, "', '", sample_name,
        "') does not contain the full component grid; add explicit zero rows for: ", paste(missing, collapse = ", ")
      ))
    }
  }
  row_sample_key <- sample_key(data$facet, data$sample)
  totals <- tapply(data$value, row_sample_key, sum)
  if (any(totals <= 0)) fail("a sample has zero total; composition is undefined")
  if (config$input_mode == "proportion") {
    deviation <- abs(totals - 1)
    if (any(deviation > config$sum_tolerance)) {
      bad_key <- names(totals)[which(deviation > config$sum_tolerance)[[1L]]]
      bad_parts <- strsplit(bad_key, "\034", fixed = TRUE)[[1L]]
      readable_key <- paste0("('", bad_parts[[1L]], "', '", bad_parts[[2L]], "')")
      fail(paste0(
        "proportion sample ", readable_key, " sums to ", format(totals[[bad_key]], digits = 12),
        ", outside 1 ± ", config$sum_tolerance, "; the script will not normalize silently"
      ))
    }
  }
  original_totals <- totals
  if (config$normalize) data$value <- data$value / totals[row_sample_key]
  style <- read_style(config$style, components)
  list(
    data = data,
    facet_order = facet_order,
    component_order = style$component,
    style = style,
    input_mode = config$input_mode,
    normalized = config$normalize,
    original_totals = original_totals,
    sample_order_mode = config$sample_order
  )
}

samples_for <- function(input_data, facet_name) {
  observed <- ordered_unique(input_data$data$sample[input_data$data$facet == facet_name])
  if (input_data$sample_order_mode == "input") return(observed)
  if (input_data$sample_order_mode == "alphabetical") return(sort(observed))
  totals <- input_data$original_totals[sample_key(facet_name, observed)]
  observed[order(-totals, observed)]
}

geometry <- function(input_data) {
  facet_count <- length(input_data$facet_order)
  columns <- if (facet_count == 1L) 1L else if (facet_count %in% c(2L, 3L)) facet_count else if (facet_count == 4L) 2L else min(3L, facet_count)
  rows <- ceiling(facet_count / columns)
  sample_counts <- vapply(input_data$facet_order, function(facet_name) length(samples_for(input_data, facet_name)), integer(1L))
  sample_labels <- unlist(lapply(input_data$facet_order, function(facet_name) samples_for(input_data, facet_name)))
  panel_width <- min(11, max(5.2, 3.8 + 0.18 * max(sample_counts) + 0.025 * max(nchar(sample_labels, type = "width"))))
  list(rows = rows, columns = columns, width = panel_width * columns + 2.3, height = 4.8 * rows)
}

wrap_label <- function(text, width = 12L) paste(strwrap(text, width = width), collapse = "\n")

draw_figure <- function(input_data, title_text, value_label, layout_info) {
  proportion_plot <- input_data$input_mode == "proportion" || input_data$normalized
  plot_totals <- tapply(input_data$data$value, sample_key(input_data$data$facet, input_data$data$sample), sum)
  global_max <- if (proportion_plot) 1 else max(plot_totals)
  panel_left <- 0.06
  panel_right <- 0.79
  panel_bottom <- if (layout_info$rows == 1L) 0.17 else 0.10
  panel_top <- 0.84
  gap_x <- 0.018
  gap_y <- 0.075
  panel_width <- (panel_right - panel_left - gap_x * (layout_info$columns - 1L)) / layout_info$columns
  panel_height <- (panel_top - panel_bottom - gap_y * (layout_info$rows - 1L)) / layout_info$rows

  for (facet_index in seq_along(input_data$facet_order)) {
    facet_name <- input_data$facet_order[[facet_index]]
    row_index <- (facet_index - 1L) %/% layout_info$columns
    column_index <- (facet_index - 1L) %% layout_info$columns
    x0 <- panel_left + column_index * (panel_width + gap_x)
    x1 <- x0 + panel_width
    y1 <- panel_top - row_index * (panel_height + gap_y)
    y0 <- y1 - panel_height
    par(
      fig = c(x0, x1, y0, y1),
      mar = c(5.4, 4.0, 2.2, 0.5),
      mgp = c(2.4, 0.65, 0),
      tcl = -0.24,
      family = "sans",
      bg = "white",
      new = facet_index > 1L
    )
    samples <- samples_for(input_data, facet_name)
    matrix_values <- sapply(samples, function(sample_name) {
      values <- input_data$data$value[input_data$data$facet == facet_name & input_data$data$sample == sample_name]
      names(values) <- input_data$data$component[input_data$data$facet == facet_name & input_data$data$sample == sample_name]
      values[input_data$component_order]
    })
    if (length(samples) == 1L) matrix_values <- matrix(matrix_values, ncol = 1L, dimnames = list(input_data$component_order, samples))
    positions <- barplot(matrix_values, plot = FALSE, space = 0.12, axisnames = FALSE)
    plot.new()
    plot.window(xlim = c(min(positions) - 0.55, max(positions) + 0.55), ylim = c(0, if (proportion_plot) 1 else global_max * 1.04), xaxs = "i", yaxs = "i")
    abline(h = if (proportion_plot) seq(0, 1, 0.25) else pretty(c(0, global_max), n = 5), col = "#E5E8EB", lwd = 0.65)
    barplot(
      matrix_values,
      col = input_data$style$color[match(input_data$component_order, input_data$style$component)],
      border = "white",
      lwd = 0.45,
      space = 0.12,
      axes = FALSE,
      axisnames = FALSE,
      add = TRUE
    )
    stride <- max(1L, ceiling(length(samples) / 20L))
    tick_index <- seq(1L, length(samples), by = stride)
    axis(1, at = positions[tick_index], labels = vapply(samples[tick_index], wrap_label, character(1L)), las = 2, tick = FALSE, cex.axis = 0.60, padj = 0.6)
    if (proportion_plot) {
      axis(2, at = seq(0, 1, 0.25), labels = paste0(seq(0, 100, 25), "%"), las = 1, cex.axis = 0.72, col = "#6C7680", col.axis = "#4E5965")
    } else {
      axis(2, las = 1, cex.axis = 0.72, col = "#6C7680", col.axis = "#4E5965")
    }
    box(bty = "l", col = "#6C7680", lwd = 0.8)
    mtext(paste0(facet_name, " · ", length(samples), " samples"), side = 3, line = 0.65, adj = 0, cex = 0.88, font = 2)
    if (stride > 1L) mtext(paste0("sample labels shown every ", stride), side = 1, line = 4.2, adj = 1, cex = 0.58, col = "#6A737D")
  }

  par(fig = c(0.81, 0.99, 0.18, 0.82), mar = c(0, 0, 0, 0), new = TRUE)
  plot.new()
  legend(
    "topleft",
    legend = input_data$style$label,
    fill = input_data$style$color,
    border = NA,
    title = "Component",
    bty = "n",
    cex = 0.76,
    ncol = if (nrow(input_data$style) > 10L) 2L else 1L,
    x.intersp = 0.55,
    y.intersp = 1.05
  )

  mode_text <- if (input_data$input_mode == "proportion") "validated proportions; no normalization" else if (input_data$normalized) "raw values normalized per sample" else "raw values; no normalization"
  par(fig = c(0, 1, 0, 1), mar = c(0, 0, 0, 0), new = TRUE)
  plot.new()
  text(0.06, 0.965, title_text, adj = c(0, 1), cex = 1.50, font = 2, col = "#20262E")
  text(
    0.06,
    0.922,
    sprintf("%d facets · %d components · %s", length(input_data$facet_order), length(input_data$component_order), mode_text),
    adj = c(0, 1),
    cex = 0.84,
    col = "#5E6872"
  )
  text(0.015, 0.50, if (proportion_plot) "Proportion" else value_label, srt = 90, cex = 0.95)
  text(
    0.06,
    0.025,
    paste0("Each bar is one facet/sample key. All component keys are explicit; omitted components are not treated as zero. Sample order: ", input_data$sample_order_mode, "."),
    adj = c(0, 0),
    cex = 0.64,
    col = "#66707A"
  )
}

render_output <- function(kind, path, input_data, title_text, value_label, layout_info) {
  if (kind == "png") {
    png(path, width = layout_info$width, height = layout_info$height, units = "in", res = 320, type = if (capabilities("cairo")) "cairo" else getOption("bitmapType"), bg = "white")
  } else {
    svg(path, width = layout_info$width, height = layout_info$height, onefile = TRUE, bg = "white", family = "sans")
  }
  device_id <- dev.cur()
  on.exit(if (dev.cur() == device_id) dev.off(), add = FALSE)
  draw_figure(input_data, title_text, value_label, layout_info)
  dev.off()
  on.exit(NULL, add = FALSE)
}

report_data <- function(input_data) {
  totals <- as.numeric(input_data$original_totals)
  cat(sprintf(
    "Loaded %d composition rows: %d facet(s), %d sample(s), %d component(s); input_mode=%s, normalized=%s, 0 rows excluded.\n",
    nrow(input_data$data), length(input_data$facet_order), length(input_data$original_totals), length(input_data$component_order), input_data$input_mode, tolower(as.character(input_data$normalized))
  ))
  cat(sprintf("original sample totals: min=%s | max=%s\n", format(min(totals), digits = 12), format(max(totals), digits = 12)))
  if (input_data$input_mode == "proportion") cat(sprintf("maximum absolute deviation from 1: %s\n", format(max(abs(totals - 1)), digits = 12)))
  for (facet_name in input_data$facet_order) {
    samples <- samples_for(input_data, facet_name)
    stride <- max(1L, ceiling(length(samples) / 20L))
    cat(sprintf("facet=%s | samples=%d | label_stride=%d\n", facet_name, length(samples), stride))
  }
}

main <- function() {
  config <- parse_args(commandArgs(trailingOnly = TRUE))
  input_data <- read_data(config)
  layout_info <- geometry(input_data)
  output_directory <- dirname(config$output_prefix)
  if (!dir.exists(output_directory)) dir.create(output_directory, recursive = TRUE, showWarnings = FALSE)
  png_path <- paste0(config$output_prefix, ".png")
  svg_path <- paste0(config$output_prefix, ".svg")
  render_output("png", png_path, input_data, config$title, config$value_label, layout_info)
  render_output("svg", svg_path, input_data, config$title, config$value_label, layout_info)
  report_data(input_data)
  cat("Wrote ", png_path, "\n", sep = "")
  cat("Wrote ", svg_path, "\n", sep = "")
}

status <- tryCatch({main(); 0L}, error = function(error) {message("ERROR: ", conditionMessage(error)); 2L})
quit(save = "no", status = status)
