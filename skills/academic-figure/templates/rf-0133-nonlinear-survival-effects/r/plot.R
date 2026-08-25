#!/usr/bin/env Rscript

fail <- function(message) {
  cat(sprintf("ERROR: %s\n", message), file = stderr())
  quit(save = "no", status = 2L)
}

parse_args <- function(args) {
  values <- list(
    input = NULL,
    annotations = NULL,
    output_prefix = NULL,
    title = "Upstream nonlinear effect curves",
    y_transform = "linear",
    reference_tolerance = 1e-6,
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
  if (is.null(values$input)) fail("--input is required")
  if (is.null(values$output_prefix)) fail("--output-prefix is required")
  values$reference_tolerance <- suppressWarnings(as.numeric(values$reference_tolerance))
  values$dpi <- suppressWarnings(as.integer(values$dpi))
  if (!values$y_transform %in% c("linear", "log")) fail("--y-transform must be linear or log")
  if (!is.finite(values$reference_tolerance) || values$reference_tolerance <= 0) {
    fail("--reference-tolerance must be a finite positive number")
  }
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

to_finite <- function(values, field, row_numbers) {
  parsed <- suppressWarnings(as.numeric(trim_column(values)))
  bad <- which(!is.finite(parsed))
  if (length(bad)) fail(sprintf("row %d: %s must be a finite number", row_numbers[[bad[[1L]]]], field))
  parsed
}

single_text <- function(values, field) {
  unique_values <- unique(trim_column(values))
  if (length(unique_values) != 1L || !nzchar(unique_values[[1L]])) {
    fail(paste(field, "must have one non-empty value across the full input"))
  }
  unique_values[[1L]]
}

close_enough <- function(a, b, tolerance) {
  abs(a - b) <= tolerance * max(1, abs(a), abs(b))
}

validate_curves <- function(data, tolerance, y_transform) {
  text_fields <- c("facet", "group", "exposure_label", "effect_measure", "effect_scale", "interval_type")
  for (field in text_fields) {
    data[[field]] <- trim_column(data[[field]])
    bad <- which(!nzchar(data[[field]]))
    if (length(bad)) fail(sprintf("row %d: %s must not be empty", data$.row_number[[bad[[1L]]]], field))
  }
  numeric_fields <- c("exposure", "effect", "ci_lower", "ci_upper", "reference_exposure", "reference_effect", "interval_level")
  for (field in numeric_fields) data[[field]] <- to_finite(data[[field]], field, data$.row_number)
  bad_interval <- which(data$ci_lower > data$effect | data$effect > data$ci_upper)
  if (length(bad_interval)) {
    index <- bad_interval[[1L]]
    fail(sprintf(
      "row %d: require ci_lower <= effect <= ci_upper, got %g, %g, %g",
      data$.row_number[[index]], data$ci_lower[[index]], data$effect[[index]], data$ci_upper[[index]]
    ))
  }
  bad_level <- which(data$interval_level <= 0 | data$interval_level >= 1)
  if (length(bad_level)) fail(sprintf("row %d: interval_level must be between 0 and 1", data$.row_number[[bad_level[[1L]]]]))

  effect_scale <- tolower(single_text(data$effect_scale, "effect_scale"))
  if (!effect_scale %in% c("ratio", "difference")) fail("effect_scale must be exactly 'ratio' or 'difference'")
  exposure_label <- single_text(data$exposure_label, "exposure_label")
  effect_measure <- single_text(data$effect_measure, "effect_measure")
  interval_type <- single_text(data$interval_type, "interval_type")
  if (diff(range(data$interval_level)) > 1e-12) fail("interval_level must have one numeric value across the full input")
  if (diff(range(data$reference_effect)) > tolerance * max(1, max(abs(data$reference_effect)))) {
    fail("reference_effect must have one value across the full input")
  }
  reference_effect <- data$reference_effect[[1L]]
  if (effect_scale == "ratio") {
    for (field in c("effect", "ci_lower", "ci_upper", "reference_effect")) {
      bad <- which(data[[field]] <= 0)
      if (length(bad)) fail(sprintf("row %d: %s must be > 0 for ratio scale", data$.row_number[[bad[[1L]]]], field))
    }
  }
  if (y_transform == "log" && effect_scale != "ratio") {
    fail("--y-transform log is allowed only when effect_scale=ratio")
  }

  facets <- unique(data$facet)
  groups <- unique(data$group)
  if (length(facets) > 9L) fail(sprintf("found %d facets; the template limit is 9", length(facets)))
  if (length(groups) > 8L) fail(sprintf("found %d groups; the template limit is 8", length(groups)))
  if (max(nchar(c(facets, groups), type = "width")) > 80L) fail("facet and group labels must be at most 80 characters")

  duplicate_key <- paste(data$facet, data$group, format(data$exposure, digits = 17), sep = "\034")
  duplicated_index <- which(duplicated(duplicate_key))
  if (length(duplicated_index)) {
    index <- duplicated_index[[1L]]
    fail(sprintf(
      "duplicate (facet, group, exposure) key: ('%s', '%s', %g)",
      data$facet[[index]], data$group[[index]], data$exposure[[index]]
    ))
  }

  curve_keys <- unique(paste(data$facet, data$group, sep = "\034"))
  curves <- vector("list", length(curve_keys))
  names(curves) <- curve_keys
  for (key in curve_keys) {
    parts <- strsplit(key, "\034", fixed = TRUE)[[1L]]
    indices <- which(data$facet == parts[[1L]] & data$group == parts[[2L]])
    curve <- data[indices[order(data$exposure[indices])], , drop = FALSE]
    if (nrow(curve) < 3L) fail(sprintf("curve ('%s', '%s') has %d points; at least 3 are required", parts[[1L]], parts[[2L]], nrow(curve)))
    if (nrow(curve) > 500L) fail(sprintf("curve ('%s', '%s') has %d points; the limit is 500", parts[[1L]], parts[[2L]], nrow(curve)))
    if (diff(range(curve$reference_exposure)) > tolerance * max(1, max(abs(curve$reference_exposure)))) {
      fail(sprintf("curve ('%s', '%s') has inconsistent reference_exposure values", parts[[1L]], parts[[2L]]))
    }
    reference_x <- curve$reference_exposure[[1L]]
    matches <- which(vapply(curve$exposure, function(value) close_enough(value, reference_x, tolerance), logical(1)))
    if (length(matches) != 1L) {
      fail(sprintf(
        "curve ('%s', '%s') reference_exposure=%g must match exactly one supplied grid point",
        parts[[1L]], parts[[2L]], reference_x
      ))
    }
    if (!close_enough(curve$effect[[matches]], reference_effect, tolerance)) {
      fail(sprintf(
        "curve ('%s', '%s') effect at reference exposure is %g, not reference_effect=%g within tolerance",
        parts[[1L]], parts[[2L]], curve$effect[[matches]], reference_effect
      ))
    }
    curves[[key]] <- curve
  }
  list(
    data = data,
    facets = facets,
    groups = groups,
    curves = curves,
    effect_scale = effect_scale,
    exposure_label = exposure_label,
    effect_measure = effect_measure,
    interval_type = interval_type,
    interval_level = data$interval_level[[1L]],
    reference_effect = reference_effect
  )
}

validate_annotations <- function(data, curves, y_transform) {
  data$facet <- trim_column(data$facet)
  data$group <- trim_column(data$group)
  data$label <- trim_column(data$label)
  bad <- which(!nzchar(data$facet) | !nzchar(data$label))
  if (length(bad)) fail(sprintf("annotation row %d: facet and label must not be empty", data$.row_number[[bad[[1L]]]]))
  data$x <- to_finite(data$x, "x", data$.row_number)
  data$y <- to_finite(data$y, "y", data$.row_number)
  for (index in seq_len(nrow(data))) {
    facet <- data$facet[[index]]
    group <- data$group[[index]]
    selected <- curves$data[curves$data$facet == facet, , drop = FALSE]
    if (!nrow(selected)) fail(sprintf("annotation row %d: unknown facet '%s'", data$.row_number[[index]], facet))
    if (nzchar(group) && !group %in% selected$group) {
      fail(sprintf("annotation row %d: group '%s' does not occur in facet '%s'", data$.row_number[[index]], group, facet))
    }
    if (nchar(data$label[[index]], type = "width") > 90L) fail(sprintf("annotation row %d: label exceeds 90 characters", data$.row_number[[index]]))
    if (data$x[[index]] < min(selected$exposure) || data$x[[index]] > max(selected$exposure)) {
      fail(sprintf("annotation row %d: x=%g is outside supplied facet range", data$.row_number[[index]], data$x[[index]]))
    }
    if (data$y[[index]] < min(selected$ci_lower) || data$y[[index]] > max(selected$ci_upper)) {
      fail(sprintf("annotation row %d: y=%g is outside supplied facet interval range", data$.row_number[[index]], data$y[[index]]))
    }
    if (y_transform == "log" && data$y[[index]] <= 0) fail(sprintf("annotation row %d: y must be > 0 on a log axis", data$.row_number[[index]]))
  }
  facet_counts <- table(factor(data$facet, levels = curves$facets))
  if (any(facet_counts > 12L)) fail(sprintf("facet '%s' has more than 12 supplied annotations", names(facet_counts)[which(facet_counts > 12L)[[1L]]]))
  data
}

wrap_text <- function(text, width = 32L) paste(strwrap(text, width = width), collapse = "\n")

draw_figure <- function(curves, annotations, title, y_transform, output_path, type, dpi) {
  facets <- curves$facets
  groups <- curves$groups
  n_facets <- length(facets)
  n_cols <- if (n_facets == 1L) 1L else if (n_facets <= 4L) 2L else 3L
  n_rows <- ceiling(n_facets / n_cols)
  width <- min(16.5, 5.2 * n_cols)
  height <- 3.65 * n_rows + 1.7
  if (type == "png") {
    png(output_path, width = width, height = height, units = "in", res = dpi, bg = "white", type = "cairo")
  } else {
    svg(output_path, width = width, height = height, bg = "white", onefile = TRUE)
  }
  on.exit(dev.off(), add = TRUE)

  grid_count <- n_rows * n_cols
  layout_matrix <- rbind(matrix(seq_len(grid_count), nrow = n_rows, byrow = TRUE), rep(grid_count + 1L, n_cols))
  layout(layout_matrix, heights = c(rep(1, n_rows), 0.18))
  par(oma = c(3.4, 2.0, 4.0, 0.8), family = "sans")
  palette <- c("#2C6E9B", "#C05A47", "#4E8B57", "#8A63A8", "#C28B2C", "#3C8D91", "#9B5D73", "#6E6E6E")
  colors <- setNames(palette[seq_along(groups)], groups)
  line_types <- setNames(rep(c(1, 2, 3, 4), length.out = length(groups)), groups)
  global_y <- range(c(curves$data$ci_lower, curves$data$ci_upper))
  if (y_transform == "linear") {
    padding <- diff(global_y) * 0.09
    if (padding == 0) padding <- max(1, abs(global_y[[1L]])) * 0.09
    global_y <- global_y + c(-padding, padding)
  } else {
    log_range <- log(global_y)
    padding <- diff(log_range) * 0.09
    global_y <- exp(log_range + c(-padding, padding))
  }

  for (panel_index in seq_len(grid_count)) {
    if (panel_index > n_facets) {
      par(mar = c(0, 0, 0, 0)); plot.new(); next
    }
    facet <- facets[[panel_index]]
    selected <- curves$data[curves$data$facet == facet, , drop = FALSE]
    x_range <- range(selected$exposure)
    x_padding <- diff(x_range) * 0.04
    if (x_padding == 0) x_padding <- 0.5
    par(mar = c(4.1, if ((panel_index - 1L) %% n_cols == 0L) 4.7 else 3.2, 3.0, 0.8))
    plot(
      NA,
      xlim = x_range + c(-x_padding, x_padding),
      ylim = global_y,
      log = if (y_transform == "log") "y" else "",
      xlab = curves$exposure_label,
      ylab = if ((panel_index - 1L) %% n_cols == 0L) paste(curves$effect_measure, sprintf("(%s scale)", curves$effect_scale)) else "",
      main = wrap_text(facet, 42L),
      bty = "l",
      las = 1,
      cex.axis = 0.82,
      cex.lab = 0.9,
      cex.main = 1.0,
      font.main = 2
    )
    abline(h = pretty(global_y), col = "#E0E0E0", lwd = 0.7)
    abline(h = curves$reference_effect, col = "#3F3F3F", lwd = 1.0, lty = 3)
    reference_positions <- numeric()
    for (group in groups) {
      key <- paste(facet, group, sep = "\034")
      if (!key %in% names(curves$curves)) next
      curve <- curves$curves[[key]]
      polygon(
        c(curve$exposure, rev(curve$exposure)),
        c(curve$ci_lower, rev(curve$ci_upper)),
        col = adjustcolor(colors[[group]], alpha.f = 0.16),
        border = NA
      )
      lines(curve$exposure, curve$effect, col = colors[[group]], lty = line_types[[group]], lwd = 2.0)
      reference_x <- curve$reference_exposure[[1L]]
      reference_positions <- c(reference_positions, reference_x)
      reference_index <- which.min(abs(curve$exposure - reference_x))
      points(reference_x, curve$effect[[reference_index]], pch = 23, bg = colors[[group]], col = "white", cex = 1.05, lwd = 0.8)
    }
    unique_refs <- unique(reference_positions)
    for (reference_x in unique_refs) abline(v = reference_x, col = "#777777", lwd = 0.8, lty = 3)
    if (nrow(annotations)) {
      panel_annotations <- annotations[annotations$facet == facet, , drop = FALSE]
      for (index in seq_len(nrow(panel_annotations))) {
        group <- panel_annotations$group[[index]]
        text_color <- if (nzchar(group)) colors[[group]] else "#303030"
        text(
          panel_annotations$x[[index]], panel_annotations$y[[index]],
          labels = wrap_text(panel_annotations$label[[index]], 28L),
          col = text_color, cex = 0.68, adj = c(0, 0.5), xpd = NA
        )
      }
    }
  }

  par(mar = c(0, 0, 0, 0)); plot.new()
  legend(
    "center", legend = groups, col = colors[groups], lty = line_types[groups], lwd = 2.0,
    ncol = min(4L, length(groups)), bty = "n", cex = 0.82, title = "Group"
  )
  mtext(title, side = 3, outer = TRUE, line = 2.1, adj = 0.02, cex = 1.35, font = 2)
  caption <- sprintf(
    "Supplied %g%% %s intervals; adjacent supplied grid points are connected. Diamonds and dotted vertical lines mark supplied reference exposures. No fitting, smoothing, P values, or interval extrapolation.",
    100 * curves$interval_level, curves$interval_type
  )
  wrapped_caption <- strwrap(caption, width = max(95L, floor(width * 12)))
  for (line_index in seq_along(wrapped_caption)) {
    mtext(wrapped_caption[[line_index]], side = 1, outer = TRUE, line = 1.1 + 0.9 * (line_index - 1L), adj = 0.02, cex = 0.67, col = "#555555")
  }
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
curve_fields <- c(
  "facet", "group", "exposure", "effect", "ci_lower", "ci_upper", "reference_exposure", "reference_effect",
  "exposure_label", "effect_measure", "effect_scale", "interval_level", "interval_type"
)
curve_data <- read_contract_csv(args$input, curve_fields)
curves <- validate_curves(curve_data, args$reference_tolerance, args$y_transform)
annotations <- data.frame(facet = character(), group = character(), x = numeric(), y = numeric(), label = character())
if (!is.null(args$annotations)) {
  annotation_data <- read_contract_csv(args$annotations, c("facet", "group", "x", "y", "label"))
  annotations <- validate_annotations(annotation_data, curves, args$y_transform)
}

output_dir <- dirname(args$output_prefix)
if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
png_path <- paste0(args$output_prefix, ".png")
svg_path <- paste0(args$output_prefix, ".svg")
draw_figure(curves, annotations, args$title, args$y_transform, png_path, "png", args$dpi)
draw_figure(curves, annotations, args$title, args$y_transform, svg_path, "svg", args$dpi)

cat(sprintf(
  "Loaded %d supplied grid rows: %d curve(s), %d facet(s), %d group(s); 0 rows excluded.\n",
  nrow(curves$data), length(curves$curves), length(curves$facets), length(curves$groups)
))
cat(sprintf(
  "effect_measure=%s | effect_scale=%s | reference_effect=%g | interval=%g%% %s | y_transform=%s\n",
  curves$effect_measure, curves$effect_scale, curves$reference_effect,
  100 * curves$interval_level, curves$interval_type, args$y_transform
))
for (key in names(curves$curves)) {
  curve <- curves$curves[[key]]
  cat(sprintf(
    "facet=%s | group=%s | supplied_points=%d | exposure_range=[%g, %g] | reference_exposure=%g verified_on_grid=true\n",
    curve$facet[[1L]], curve$group[[1L]], nrow(curve), min(curve$exposure), max(curve$exposure), curve$reference_exposure[[1L]]
  ))
}
cat(sprintf("supplied_annotations=%d\n", nrow(annotations)))
cat(sprintf("Wrote %s\n", png_path))
cat(sprintf("Wrote %s\n", svg_path))
