#!/usr/bin/env Rscript

fail <- function(message) {
  cat(sprintf("ERROR: %s\n", message), file = stderr())
  quit(save = "no", status = 2L)
}

parse_args <- function(args) {
  values <- list(
    matrix = NULL,
    rows = NULL,
    columns = NULL,
    annotations = NULL,
    color_mode = NULL,
    color_center = NULL,
    title = "Supplied ordered matrix and modules",
    output_prefix = NULL,
    dpi = 320L
  )
  index <- 1L
  while (index <= length(args)) {
    key <- args[[index]]
    if (!startsWith(key, "--") || index == length(args)) fail(paste("invalid argument", key))
    name <- gsub("-", "_", substring(key, 3L), fixed = TRUE)
    if (!name %in% names(values)) fail(paste("unknown argument", key))
    values[[name]] <- args[[index + 1L]]
    index <- index + 2L
  }
  for (field in c("matrix", "rows", "columns", "color_mode", "output_prefix")) {
    if (is.null(values[[field]])) fail(paste0("--", gsub("_", "-", field), " is required"))
  }
  if (!values$color_mode %in% c("diverging", "sequential")) fail("--color-mode must be diverging or sequential")
  if (!is.null(values$color_center)) {
    values$color_center <- suppressWarnings(as.numeric(values$color_center))
    if (!is.finite(values$color_center)) fail("--color-center must be finite")
  }
  values$dpi <- suppressWarnings(as.integer(values$dpi))
  if (is.na(values$dpi) || values$dpi < 150L || values$dpi > 1200L) fail("--dpi must be between 150 and 1200")
  values
}

read_contract_csv <- function(path, required) {
  if (!file.exists(path)) fail(paste("input file not found:", path))
  data <- tryCatch(
    read.csv(path, stringsAsFactors = FALSE, check.names = FALSE, na.strings = c("NA")),
    error = function(error) fail(paste("could not read", basename(path), "-", conditionMessage(error)))
  )
  missing <- setdiff(required, names(data))
  if (length(missing)) fail(paste(basename(path), "is missing required column(s):", paste(missing, collapse = ", ")))
  if (!nrow(data)) fail(paste(basename(path), "contains no data rows"))
  data$.row_number <- seq_len(nrow(data)) + 1L
  data
}

trim_column <- function(values) {
  values[is.na(values)] <- ""
  trimws(as.character(values))
}

positive_integer <- function(values, field, row_numbers) {
  text <- trim_column(values)
  bad <- which(!grepl("^[1-9][0-9]*$", text))
  if (length(bad)) fail(sprintf("row %d: %s must be a positive integer", row_numbers[[bad[[1L]]]], field))
  as.integer(text)
}

finite_number <- function(values, field, row_numbers) {
  parsed <- suppressWarnings(as.numeric(trim_column(values)))
  bad <- which(!is.finite(parsed))
  if (length(bad)) fail(sprintf("row %d: %s must be finite", row_numbers[[bad[[1L]]]], field))
  parsed
}

exact_order <- function(values, field) {
  if (!identical(unname(sort(values)), seq_along(values))) {
    fail(sprintf("%s must contain each integer from 1 to %d exactly once", field, length(values)))
  }
}

validate_metadata <- function(row_data, column_data) {
  for (field in c("row_id", "row_label", "module", "module_label")) {
    row_data[[field]] <- trim_column(row_data[[field]])
    bad <- which(!nzchar(row_data[[field]]))
    if (length(bad)) fail(sprintf("row metadata row %d: %s must not be empty", row_data$.row_number[[bad[[1L]]]], field))
  }
  row_data$row_annotation <- if ("row_annotation" %in% names(row_data)) trim_column(row_data$row_annotation) else rep("", nrow(row_data))
  bad <- which(nchar(row_data$row_label, type = "width") > 60L)
  if (length(bad)) fail(sprintf("row metadata row %d: row_label exceeds 60 characters", row_data$.row_number[[bad[[1L]]]]))
  bad <- which(nchar(row_data$module_label, type = "width") > 50L)
  if (length(bad)) fail(sprintf("row metadata row %d: module_label exceeds 50 characters", row_data$.row_number[[bad[[1L]]]]))
  bad <- which(nchar(row_data$row_annotation, type = "width") > 90L)
  if (length(bad)) fail(sprintf("row metadata row %d: row_annotation exceeds 90 characters", row_data$.row_number[[bad[[1L]]]]))
  row_data$row_order <- positive_integer(row_data$row_order, "row_order", row_data$.row_number)
  row_data$module_order <- positive_integer(row_data$module_order, "module_order", row_data$.row_number)
  duplicate <- which(duplicated(row_data$row_id))
  if (length(duplicate)) fail(sprintf("row metadata: duplicate row_id '%s'", row_data$row_id[[duplicate[[1L]]]]))
  exact_order(row_data$row_order, "row_order")
  if (nrow(row_data) > 60L) fail(sprintf("found %d rows; the template limit is 60", nrow(row_data)))
  row_data <- row_data[order(row_data$row_order), , drop = FALSE]

  module_ids <- unique(row_data$module)
  module_rows <- vector("list", length(module_ids))
  names(module_rows) <- module_ids
  for (module in module_ids) {
    selected <- row_data[row_data$module == module, , drop = FALSE]
    labels <- unique(selected$module_label)
    orders <- unique(selected$module_order)
    if (length(labels) != 1L || length(orders) != 1L) fail(sprintf("module '%s' has inconsistent module_label or module_order", module))
    module_rows[[module]] <- list(module_label = labels[[1L]], module_order = orders[[1L]])
  }
  module_orders <- vapply(module_rows, function(item) item$module_order, integer(1))
  if (anyDuplicated(module_orders)) fail("module_order must be unique across modules")
  exact_order(module_orders, "module_order")
  if (length(module_rows) > 12L) fail(sprintf("found %d modules; the template limit is 12", length(module_rows)))
  observed_blocks <- row_data$module[c(TRUE, row_data$module[-1L] != row_data$module[-nrow(row_data)])]
  expected_blocks <- names(module_rows)[order(module_orders)]
  if (!identical(observed_blocks, expected_blocks)) {
    fail(sprintf(
      "modules must form contiguous row blocks ordered by module_order; observed [%s], expected [%s]",
      paste(observed_blocks, collapse = ", "), paste(expected_blocks, collapse = ", ")
    ))
  }

  for (field in c("column_id", "column_label")) {
    column_data[[field]] <- trim_column(column_data[[field]])
    bad <- which(!nzchar(column_data[[field]]))
    if (length(bad)) fail(sprintf("column metadata row %d: %s must not be empty", column_data$.row_number[[bad[[1L]]]], field))
  }
  bad <- which(nchar(column_data$column_label, type = "width") > 50L)
  if (length(bad)) fail(sprintf("column metadata row %d: column_label exceeds 50 characters", column_data$.row_number[[bad[[1L]]]]))
  column_data$column_order <- positive_integer(column_data$column_order, "column_order", column_data$.row_number)
  duplicate <- which(duplicated(column_data$column_id))
  if (length(duplicate)) fail(sprintf("column metadata: duplicate column_id '%s'", column_data$column_id[[duplicate[[1L]]]]))
  exact_order(column_data$column_order, "column_order")
  if (nrow(column_data) > 40L) fail(sprintf("found %d columns; the template limit is 40", nrow(column_data)))
  column_data <- column_data[order(column_data$column_order), , drop = FALSE]
  list(rows = row_data, columns = column_data, modules = module_rows)
}

validate_matrix <- function(data, metadata) {
  for (field in c("row_id", "column_id", "value_scale")) {
    data[[field]] <- trim_column(data[[field]])
    bad <- which(!nzchar(data[[field]]))
    if (length(bad)) fail(sprintf("matrix row %d: %s must not be empty", data$.row_number[[bad[[1L]]]], field))
  }
  data$value <- finite_number(data$value, "value", data$.row_number)
  unknown_row <- which(!data$row_id %in% metadata$rows$row_id)
  if (length(unknown_row)) fail(sprintf("matrix row %d: unknown row_id '%s'", data$.row_number[[unknown_row[[1L]]]], data$row_id[[unknown_row[[1L]]]]))
  unknown_column <- which(!data$column_id %in% metadata$columns$column_id)
  if (length(unknown_column)) fail(sprintf("matrix row %d: unknown column_id '%s'", data$.row_number[[unknown_column[[1L]]]], data$column_id[[unknown_column[[1L]]]]))
  keys <- paste(data$row_id, data$column_id, sep = "\034")
  duplicate <- which(duplicated(keys))
  if (length(duplicate)) {
    index <- duplicate[[1L]]
    fail(sprintf("duplicate matrix (row_id, column_id) key: ('%s', '%s')", data$row_id[[index]], data$column_id[[index]]))
  }
  scales <- unique(data$value_scale)
  if (length(scales) != 1L) fail(sprintf("value_scale must have one value across the matrix; found [%s]", paste(scales, collapse = ", ")))
  expected <- as.vector(outer(metadata$rows$row_id, metadata$columns$column_id, paste, sep = "\034"))
  missing <- setdiff(expected, keys)
  if (length(missing)) {
    parts <- strsplit(missing[[1L]], "\034", fixed = TRUE)[[1L]]
    fail(sprintf(
      "matrix is incomplete: missing %d of %d required cells; example missing key ('%s', '%s'). Missing cells are not imputed.",
      length(missing), length(expected), parts[[1L]], parts[[2L]]
    ))
  }
  if (nrow(data) != length(expected)) fail("matrix cell count does not match the declared row-by-column grid")
  matrix_values <- matrix(NA_real_, nrow = nrow(metadata$rows), ncol = nrow(metadata$columns))
  for (index in seq_len(nrow(data))) {
    row_index <- match(data$row_id[[index]], metadata$rows$row_id)
    column_index <- match(data$column_id[[index]], metadata$columns$column_id)
    matrix_values[row_index, column_index] <- data$value[[index]]
  }
  list(values = matrix_values, value_scale = scales[[1L]], data = data)
}

validate_annotations <- function(data, metadata) {
  for (field in c("module", "annotation", "annotation_value")) {
    data[[field]] <- trim_column(data[[field]])
    bad <- which(!nzchar(data[[field]]))
    if (length(bad)) fail(sprintf("annotation row %d: %s must not be empty", data$.row_number[[bad[[1L]]]], field))
  }
  unknown <- which(!data$module %in% names(metadata$modules))
  if (length(unknown)) fail(sprintf("annotation row %d: unknown module '%s'", data$.row_number[[unknown[[1L]]]], data$module[[unknown[[1L]]]]))
  bad <- which(nchar(data$annotation, type = "width") > 80L | nchar(data$annotation_value, type = "width") > 50L)
  if (length(bad)) fail(sprintf("annotation row %d: annotation or annotation_value is too long", data$.row_number[[bad[[1L]]]]))
  data$annotation_order <- positive_integer(data$annotation_order, "annotation_order", data$.row_number)
  if (nrow(data) > 30L) fail("the annotation file contains more than 30 supplied annotations")
  for (module in unique(data$module)) {
    indices <- which(data$module == module)
    if (length(indices) > 4L) fail(sprintf("module '%s' has more than 4 supplied annotations", module))
    exact_order(data$annotation_order[indices], sprintf("annotation_order within %s", module))
  }
  module_order <- vapply(metadata$modules, function(item) item$module_order, integer(1))
  data <- data[order(module_order[data$module], data$annotation_order), , drop = FALSE]
  data
}

color_contract <- function(values, mode, center) {
  minimum <- min(values)
  maximum <- max(values)
  if (minimum == maximum) fail("matrix values are constant; a color scale cannot encode variation")
  if (mode == "diverging") {
    if (is.null(center)) fail("--color-center is required for diverging mode")
    if (!(minimum < center && center < maximum)) {
      fail(sprintf("diverging center %g must lie strictly inside the data range [%g, %g]", center, minimum, maximum))
    }
    span <- max(abs(minimum - center), abs(maximum - center))
    limits <- c(center - span, center + span)
    colors <- colorRampPalette(c("#2B6CB0", "#F7F7F4", "#C4473D"))(255L)
  } else {
    if (!is.null(center)) fail("--color-center must not be supplied for sequential mode")
    limits <- c(minimum, maximum)
    colors <- colorRampPalette(c("#F5F5F1", "#9BC4D4", "#245A7A"))(255L)
  }
  list(colors = colors, breaks = seq(limits[[1L]], limits[[2L]], length.out = 256L), limits = limits)
}

wrap_text <- function(text, width) paste(strwrap(text, width = width), collapse = "\n")

module_blocks <- function(rows) {
  starts <- c(1L, which(rows$module[-1L] != rows$module[-nrow(rows)]) + 1L)
  ends <- c(starts[-1L] - 1L, nrow(rows))
  data.frame(module = rows$module[starts], start = starts, end = ends, stringsAsFactors = FALSE)
}

draw_figure <- function(bundle, annotations, color_info, title, output_path, type, dpi) {
  values <- bundle$matrix$values
  rows <- bundle$metadata$rows
  columns <- bundle$metadata$columns
  modules <- bundle$metadata$modules
  blocks <- module_blocks(rows)
  n_rows <- nrow(values)
  n_columns <- ncol(values)
  has_annotations <- nrow(annotations) > 0L
  max_row_chars <- max(nchar(rows$row_label, type = "width") + nchar(rows$row_annotation, type = "width"))
  label_width <- min(6.2, max(3.0, 1.9 + 0.045 * max_row_chars))
  heat_width <- min(11.0, max(4.5, 1.4 + 0.43 * n_columns))
  annotation_width <- if (has_annotations) 4.1 else 0
  figure_width <- min(19.0, label_width + heat_width + annotation_width + 1.0)
  figure_height <- min(21.5, max(7.0, 3.6 + n_rows * if (any(nzchar(rows$row_annotation))) 0.40 else 0.31))
  if (type == "png") {
    png(output_path, width = figure_width, height = figure_height, units = "in", res = dpi, bg = "white", type = "cairo")
  } else {
    svg(output_path, width = figure_width, height = figure_height, bg = "white", onefile = TRUE)
  }
  on.exit(dev.off(), add = TRUE)

  module_palette <- c("#3B6F8F", "#A85B4A", "#4E7D54", "#775A9B", "#A87922", "#347D80", "#92546C", "#626E7A", "#8A6A42", "#4D6BA8", "#7B7041", "#536D5A")
  module_order <- vapply(modules, function(item) item$module_order, integer(1))
  ordered_modules <- names(modules)[order(module_order)]
  module_colors <- setNames(module_palette[seq_along(ordered_modules)], ordered_modules)

  widths <- c(label_width, heat_width)
  if (has_annotations) widths <- c(widths, annotation_width)
  widths <- c(widths, 0.85)
  panel_count <- length(widths)
  layout_matrix <- rbind(seq_len(panel_count), rep(panel_count + 1L, panel_count))
  layout(layout_matrix, widths = widths, heights = c(1, 0.13))
  par(oma = c(3.0, 0.6, 4.3, 0.5), family = "sans")
  bottom_margin <- if (n_columns <= 16L) 6.8 else 8.0

  row_labels <- vapply(seq_len(nrow(rows)), function(index) {
    label <- wrap_text(rows$row_label[[index]], 26L)
    if (nzchar(rows$row_annotation[[index]])) paste(label, wrap_text(rows$row_annotation[[index]], 30L), sep = "\n") else label
  }, character(1))
  left_lines <- min(22, max(8.5, max(nchar(row_labels, type = "width")) * 0.48))
  par(mar = c(bottom_margin, left_lines, 2.8, 0.2))
  plot(NA, xlim = c(0, 1), ylim = c(n_rows + 0.5, 0.5), axes = FALSE, xlab = "", ylab = "", xaxs = "i", yaxs = "i")
  for (index in seq_len(nrow(blocks))) {
    module <- blocks$module[[index]]
    rect(0, blocks$start[[index]] - 0.5, 1, blocks$end[[index]] + 0.5, col = module_colors[[module]], border = "white", lwd = 1)
    text(0.5, mean(c(blocks$start[[index]], blocks$end[[index]])), labels = modules[[module]]$module_order, col = "white", font = 2, cex = 0.75)
  }
  axis(2, at = seq_len(n_rows), labels = row_labels, las = 2, tick = FALSE, line = -0.4, cex.axis = 0.62)
  title(main = "Module", cex.main = 0.82, line = 1.2)

  par(mar = c(bottom_margin, 0.25, 2.8, 0.2))
  image(
    seq_len(n_columns), seq_len(n_rows), t(values),
    xlim = c(0.5, n_columns + 0.5), ylim = c(n_rows + 0.5, 0.5),
    col = color_info$colors, breaks = color_info$breaks, axes = FALSE,
    xlab = "", ylab = "", useRaster = TRUE, xaxs = "i", yaxs = "i"
  )
  axis(1, at = seq_len(n_columns), labels = FALSE, tick = FALSE)
  y_bottom <- par("usr")[[3L]]
  text(
    seq_len(n_columns), rep(y_bottom + 0.22, n_columns),
    labels = vapply(columns$column_label, wrap_text, character(1), width = 16L),
    srt = if (max(nchar(columns$column_label, type = "width")) <= 18L) 45 else 60,
    adj = 1, xpd = NA, cex = 0.68
  )
  if (nrow(blocks) > 1L) abline(h = blocks$end[-nrow(blocks)] + 0.5, col = "white", lwd = 2)
  box(col = "#777777", lwd = 0.6)
  title(main = "Matrix in supplied order", cex.main = 0.86, line = 1.2)

  if (has_annotations) {
    par(mar = c(bottom_margin, 0.25, 2.8, 0.2))
    plot(NA, xlim = c(0, 1), ylim = c(n_rows + 0.5, 0.5), axes = FALSE, xlab = "", ylab = "", xaxs = "i", yaxs = "i")
    for (index in seq_len(nrow(blocks))) {
      module <- blocks$module[[index]]
      rect(0, blocks$start[[index]] - 0.5, 1, blocks$end[[index]] + 0.5, col = adjustcolor(module_colors[[module]], alpha.f = 0.075), border = "white")
      selected <- annotations[annotations$module == module, , drop = FALSE]
      if (nrow(selected)) {
        labels <- mapply(
          function(label, value) wrap_text(paste(label, value, sep = " · "), 42L),
          selected$annotation, selected$annotation_value,
          USE.NAMES = FALSE
        )
        text(0.035, mean(c(blocks$start[[index]], blocks$end[[index]])), paste(labels, collapse = "\n"), adj = c(0, 0.5), cex = max(0.58, min(0.72, 0.78 - 0.0025 * n_rows)), col = "#303030")
      }
    }
    if (nrow(blocks) > 1L) abline(h = blocks$end[-nrow(blocks)] + 0.5, col = "#B9B9B9", lwd = 0.8)
    title(main = "Supplied upstream annotations", cex.main = 0.86, line = 1.2)
  }

  par(mar = c(bottom_margin, 0.3, 2.8, 4.4))
  plot(NA, xlim = c(0, 1), ylim = color_info$limits, axes = FALSE, xlab = "", ylab = "", xaxs = "i", yaxs = "i")
  for (index in seq_len(length(color_info$colors))) {
    rect(0, color_info$breaks[[index]], 1, color_info$breaks[[index + 1L]], col = color_info$colors[[index]], border = NA)
  }
  axis(4, las = 1, cex.axis = 0.65)
  mtext(bundle$matrix$value_scale, side = 4, line = 2.8, cex = 0.72)
  box(col = "#777777", lwd = 0.6)

  par(mar = c(0, 0, 0, 0)); plot.new()
  legend_labels <- vapply(ordered_modules, function(module) sprintf("%d = %s", modules[[module]]$module_order, modules[[module]]$module_label), character(1))
  legend(
    "center", legend = legend_labels, fill = module_colors[ordered_modules], border = NA,
    ncol = min(4L, length(ordered_modules)), bty = "n", cex = 0.72,
    title = "Module key (number = module_order)", title.adj = 0.5
  )
  mtext(title, side = 3, outer = TRUE, line = 2.6, adj = 0.01, cex = 1.30, font = 2)
  mtext(
    "Rows, columns, modules, and annotation text are supplied upstream; no clustering or enrichment is run.",
    side = 3, outer = TRUE, line = 1.25, adj = 0.01, cex = 0.70, col = "#555555"
  )
  caption <- sprintf(
    "Matrix: %d rows x %d columns | value scale: %s | color domain: [%g, %g] | no clipping or imputation.",
    n_rows, n_columns, bundle$matrix$value_scale, color_info$limits[[1L]], color_info$limits[[2L]]
  )
  mtext(caption, side = 1, outer = TRUE, line = 1.6, adj = 0.01, cex = 0.68, col = "#555555")
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
row_data <- read_contract_csv(args$rows, c("row_id", "row_label", "row_order", "module", "module_label", "module_order"))
column_data <- read_contract_csv(args$columns, c("column_id", "column_label", "column_order"))
metadata <- validate_metadata(row_data, column_data)
matrix_data <- read_contract_csv(args$matrix, c("row_id", "column_id", "value", "value_scale"))
matrix_result <- validate_matrix(matrix_data, metadata)
annotations <- data.frame(module = character(), annotation = character(), annotation_value = character(), annotation_order = integer())
if (!is.null(args$annotations)) {
  annotation_data <- read_contract_csv(args$annotations, c("module", "annotation", "annotation_value", "annotation_order"))
  annotations <- validate_annotations(annotation_data, metadata)
}
color_info <- color_contract(matrix_result$values, args$color_mode, args$color_center)
bundle <- list(metadata = metadata, matrix = matrix_result)

output_dir <- dirname(args$output_prefix)
if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
png_path <- paste0(args$output_prefix, ".png")
svg_path <- paste0(args$output_prefix, ".svg")
draw_figure(bundle, annotations, color_info, args$title, png_path, "png", args$dpi)
draw_figure(bundle, annotations, color_info, args$title, svg_path, "svg", args$dpi)

cat(sprintf(
  "Loaded complete supplied matrix: %d cells, %d row(s), %d column(s), %d module(s); 0 cells excluded or imputed.\n",
  nrow(matrix_result$data), nrow(metadata$rows), nrow(metadata$columns), length(metadata$modules)
))
cat(sprintf(
  "value_scale=%s | color_mode=%s | color_center=%s | color_domain=[%g, %g] | clipping=false\n",
  matrix_result$value_scale, args$color_mode,
  if (is.null(args$color_center)) "none" else format(args$color_center, trim = TRUE),
  color_info$limits[[1L]], color_info$limits[[2L]]
))
cat("row_order=validated | column_order=validated | contiguous_module_blocks=validated | clustering_run=false\n")
cat(sprintf("supplied_annotations=%d | enrichment_run=false\n", nrow(annotations)))
cat(sprintf("Wrote %s\n", png_path))
cat(sprintf("Wrote %s\n", svg_path))
