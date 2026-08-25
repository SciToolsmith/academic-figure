#!/usr/bin/env Rscript

# Render a generic multi-stage weighted Sankey diagram from CSV data.

config <- list(
  background = "#FBFAF7",
  ink = "#20272D",
  muted = "#637079",
  node_width = 0.055,
  png_dpi = 360,
  palette = c(
    "#287D78", "#C84A5B", "#4C78A8", "#C6923B", "#7A6A9D",
    "#5E8C61", "#B06C49", "#587D8D", "#A15D79", "#82734F",
    "#6C7E9B", "#8B6F63", "#4F8A83", "#9B7158"
  )
)

args <- commandArgs(trailingOnly = TRUE)
get_arg <- function(name, default = NULL) {
  prefix <- paste0("--", name, "=")
  hits <- args[startsWith(args, prefix)]
  if (!length(hits)) return(default)
  sub(prefix, "", tail(hits, 1), fixed = TRUE)
}

input_path <- get_arg("input")
output_dir <- get_arg("output-dir")
if (is.null(input_path) || is.null(output_dir)) {
  stop("Required arguments: --input=<csv> --output-dir=<directory>", call. = FALSE)
}
title_text <- get_arg("title", "Multi-stage flow overview")
subtitle_text <- get_arg("subtitle")
weight_column <- get_arg("weight")
order_mode <- get_arg("order-mode", "total")
if (!order_mode %in% c("total", "observed", "alphabetical")) {
  stop("--order-mode must be total, observed, or alphabetical", call. = FALSE)
}
if (!file.exists(input_path)) stop("Input file not found: ", input_path, call. = FALSE)

data <- read.csv(input_path, stringsAsFactors = FALSE, check.names = FALSE, fileEncoding = "UTF-8-BOM")
if (!nrow(data)) stop("Input CSV has no data rows", call. = FALSE)
if (!length(names(data)) || any(!nzchar(trimws(names(data)))) || anyDuplicated(names(data))) {
  stop("CSV must have non-empty, unique column names", call. = FALSE)
}

stages_arg <- get_arg("stages")
stages <- if (!is.null(stages_arg)) trimws(strsplit(stages_arg, ",", fixed = TRUE)[[1]]) else grep("^stage_", names(data), value = TRUE)
if (length(stages) < 2) stop("Specify at least two stage columns with --stages", call. = FALSE)
if (anyDuplicated(stages)) stop("Stage columns must be unique", call. = FALSE)
missing_stages <- setdiff(stages, names(data))
if (length(missing_stages)) stop("Missing stage columns: ", paste(missing_stages, collapse = ", "), call. = FALSE)

for (stage in stages) {
  values <- trimws(as.character(data[[stage]]))
  if (anyNA(values) || any(!nzchar(values))) stop("Stage '", stage, "' contains missing values", call. = FALSE)
  data[[stage]] <- values
}
if (!is.null(weight_column)) {
  if (!weight_column %in% names(data)) stop("Missing weight column: ", weight_column, call. = FALSE)
  data$.weight <- suppressWarnings(as.numeric(data[[weight_column]]))
} else {
  data$.weight <- 1
}
if (any(!is.finite(data$.weight)) || any(data$.weight <= 0)) {
  stop("All weights must be finite and positive", call. = FALSE)
}

ordered_unique <- function(values) values[!duplicated(values)]
totals_by <- function(frame, stage) {
  values <- tapply(frame$.weight, frame[[stage]], sum)
  values[!is.na(values)]
}
ordered_nodes <- function(frame, stage, mode) {
  totals <- totals_by(frame, stage)
  if (mode == "total") return(names(totals)[order(-as.numeric(totals), tolower(names(totals)))])
  if (mode == "alphabetical") return(sort(names(totals)))
  ordered_unique(frame[[stage]])
}

all_names <- sort(unique(unlist(data[stages], use.names = FALSE)))
node_colours <- setNames(rep(config$palette, length.out = length(all_names)), all_names)

build_flow <- function(frame, stage_names, mode) {
  total <- sum(frame$.weight)
  orders <- lapply(stage_names, function(stage) ordered_nodes(frame, stage, mode))
  maximum_nodes <- max(lengths(orders))
  gap <- min(0.014, 0.18 / max(maximum_nodes - 1, 1))
  scale <- (0.86 - gap * (maximum_nodes - 1)) / total
  if (scale <= 0) stop("Too many nodes for a readable layout; aggregate explicitly before plotting", call. = FALSE)

  nodes <- vector("list", length(stage_names))
  for (stage_index in seq_along(stage_names)) {
    stage <- stage_names[stage_index]
    order_values <- orders[[stage_index]]
    totals <- totals_by(frame, stage)
    occupied <- total * scale + gap * (length(order_values) - 1)
    cursor <- 0.5 + occupied / 2
    y1 <- y0 <- numeric(length(order_values))
    for (index in seq_along(order_values)) {
      y1[index] <- cursor
      y0[index] <- cursor - as.numeric(totals[order_values[index]]) * scale
      cursor <- y0[index] - gap
    }
    nodes[[stage_index]] <- data.frame(
      name = order_values,
      value = as.numeric(totals[order_values]),
      y1 = y1,
      y0 = y0,
      colour = unname(node_colours[order_values]),
      stringsAsFactors = FALSE
    )
  }

  links_by_gap <- vector("list", length(stage_names) - 1)
  for (stage_index in seq_len(length(stage_names) - 1)) {
    source_stage <- stage_names[stage_index]
    target_stage <- stage_names[stage_index + 1]
    links <- aggregate(frame$.weight, by = list(source = frame[[source_stage]], target = frame[[target_stage]]), FUN = sum)
    names(links)[3] <- "weight"
    links$source_index <- match(links$source, nodes[[stage_index]]$name)
    links$target_index <- match(links$target, nodes[[stage_index + 1]]$name)
    links$sy1 <- links$sy0 <- links$ty1 <- links$ty0 <- NA_real_

    source_cursor <- setNames(nodes[[stage_index]]$y1, nodes[[stage_index]]$name)
    for (row_index in order(links$source_index, links$target_index)) {
      source <- links$source[row_index]
      height <- links$weight[row_index] * scale
      links$sy1[row_index] <- source_cursor[[source]]
      links$sy0[row_index] <- source_cursor[[source]] - height
      source_cursor[[source]] <- source_cursor[[source]] - height
    }
    target_cursor <- setNames(nodes[[stage_index + 1]]$y1, nodes[[stage_index + 1]]$name)
    for (row_index in order(links$target_index, links$source_index)) {
      target <- links$target[row_index]
      height <- links$weight[row_index] * scale
      links$ty1[row_index] <- target_cursor[[target]]
      links$ty0[row_index] <- target_cursor[[target]] - height
      target_cursor[[target]] <- target_cursor[[target]] - height
    }
    links_by_gap[[stage_index]] <- links
  }
  list(stages = stage_names, nodes = nodes, links = links_by_gap, total = total)
}

adjust_positions <- function(values, minimum, lower = 0.03, upper = 0.97) {
  order_index <- order(values)
  if (length(values) > 1 && minimum * (length(values) - 1) > upper - lower) {
    placed <- seq(lower, upper, length.out = length(values))
  } else {
    placed <- pmin(pmax(values[order_index], lower), upper)
    if (length(placed) > 1) for (index in 2:length(placed)) placed[index] <- max(placed[index], placed[index - 1] + minimum)
    if (length(placed) && tail(placed, 1) > upper) placed <- placed - (tail(placed, 1) - upper)
    if (length(placed) && placed[1] < lower) placed <- placed + lower - placed[1]
  }
  result <- numeric(length(values))
  result[order_index] <- placed
  result
}

draw_ribbon <- function(x0, x1, row, colour, segments = 40) {
  t <- seq(0, 1, length.out = segments + 1)
  smooth <- t * t * (3 - 2 * t)
  x <- x0 + (x1 - x0) * t
  upper <- row$sy1 + (row$ty1 - row$sy1) * smooth
  lower <- row$sy0 + (row$ty0 - row$sy0) * smooth
  polygon(c(x, rev(x)), c(upper, rev(lower)), col = grDevices::adjustcolor(colour, alpha.f = 0.30), border = NA)
}

integer_weights <- all(abs(data$.weight - round(data$.weight)) < 1e-10)
format_value <- function(value) {
  if (integer_weights) format(round(value), big.mark = ",", scientific = FALSE, trim = TRUE) else sub("\\.?0+$", "", format(round(value, 2), nsmall = 2, trim = TRUE))
}

draw_label <- function(x, y, label, align, cex) {
  width <- strwidth(label, cex = cex)
  height <- strheight(label, cex = cex)
  if (align == 0) {
    rect(x - 0.006, y - height * 0.65, x + width + 0.012, y + height * 0.65, col = grDevices::adjustcolor("#FFFFFF", alpha.f = 0.82), border = NA)
  } else {
    rect(x - width - 0.012, y - height * 0.65, x + 0.006, y + height * 0.65, col = grDevices::adjustcolor("#FFFFFF", alpha.f = 0.82), border = NA)
  }
  text(x, y, label, adj = c(align, 0.5), cex = cex, col = config$ink)
}

flow <- build_flow(data, stages, order_mode)
maximum_nodes <- max(vapply(flow$nodes, nrow, integer(1)))
stage_count <- length(stages)
figure_width <- max(9.0, 2.35 * stage_count + 1.4)
figure_height <- min(13.0, max(5.8, 4.2 + 0.25 * maximum_nodes))
if (maximum_nodes > 24) warning("More than 24 nodes in one stage; inspect labels at final size", call. = FALSE)

if (is.null(subtitle_text)) {
  subtitle_text <- sprintf(
    "%s input paths · %s stages · total weight = %s",
    format(nrow(data), big.mark = ","), length(stages), format_value(flow$total)
  )
}

draw_flow <- function() {
  x_positions <- seq(0, stage_count - 1)
  node_width <- config$node_width
  plot.new()
  plot.window(xlim = c(-0.58, stage_count - 1 + 0.58), ylim = c(-0.035, 1.055), xaxs = "i", yaxs = "i")
  rect(par("usr")[1], par("usr")[3], par("usr")[2], par("usr")[4], col = config$background, border = NA)

  for (stage_index in seq_along(flow$links)) {
    links <- flow$links[[stage_index]]
    source_nodes <- flow$nodes[[stage_index]]
    for (row_index in order(links$weight, decreasing = TRUE)) {
      row <- links[row_index, , drop = FALSE]
      colour <- source_nodes$colour[match(row$source, source_nodes$name)]
      draw_ribbon(x_positions[stage_index] + node_width / 2, x_positions[stage_index + 1] - node_width / 2, row, colour)
    }
  }

  for (stage_index in seq_along(flow$nodes)) {
    stage_nodes <- flow$nodes[[stage_index]]
    centers <- (stage_nodes$y0 + stage_nodes$y1) / 2
    label_positions <- adjust_positions(centers, if (nrow(stage_nodes) <= 20) 0.032 else 0.025)
    for (index in seq_len(nrow(stage_nodes))) {
      height <- max(stage_nodes$y1[index] - stage_nodes$y0[index], 0.0012)
      center <- centers[index]
      rect(
        x_positions[stage_index] - node_width / 2, center - height / 2,
        x_positions[stage_index] + node_width / 2, center + height / 2,
        col = stage_nodes$colour[index], border = "#FFFFFF", lwd = 0.5
      )
      put_left <- stage_index == 1 || (stage_index != stage_count && stage_index %% 2 == 0)
      direction <- if (put_left) -1 else 1
      anchor_x <- x_positions[stage_index] + direction * node_width / 2
      text_x <- anchor_x + direction * 0.028
      if (abs(label_positions[index] - center) > 0.004) segments(anchor_x, center, text_x, label_positions[index], col = "#8B959D", lwd = 0.4)
      label <- paste0(stage_nodes$name[index], "  ", format_value(stage_nodes$value[index]))
      draw_label(text_x, label_positions[index], label, if (put_left) 1 else 0, if (nrow(stage_nodes) > 20) 0.48 else 0.58)
    }
    text(x_positions[stage_index], 1.015, toupper(gsub("_", " ", stages[stage_index], fixed = TRUE)), adj = c(0.5, 0), cex = 0.68, font = 2, col = config$muted)
  }

  mtext(title_text, side = 3, line = 3.5, adj = 0, cex = 1.45, font = 2, col = config$ink)
  mtext(subtitle_text, side = 3, line = 2.0, adj = 0, cex = 0.78, col = config$muted)
  mtext("Ribbon width is proportional to the supplied positive weight; node values are stage totals.", side = 1, line = 1.1, adj = 0, cex = 0.63, col = config$muted)
}

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
png_path <- file.path(output_dir, "sankey_r.png")
svg_path <- file.path(output_dir, "sankey_r.svg")

if (requireNamespace("ragg", quietly = TRUE)) {
  ragg::agg_png(png_path, width = figure_width, height = figure_height, units = "in", res = config$png_dpi, background = config$background)
} else if (capabilities("cairo")) {
  grDevices::png(png_path, width = figure_width, height = figure_height, units = "in", res = config$png_dpi, bg = config$background, type = "cairo-png")
} else {
  grDevices::png(png_path, width = figure_width, height = figure_height, units = "in", res = config$png_dpi, bg = config$background)
}
par(mar = c(3.3, 3.1, 5.7, 3.1), family = "sans", bg = config$background, xpd = NA)
draw_flow()
invisible(dev.off())

grDevices::svg(svg_path, width = figure_width, height = figure_height, bg = config$background, pointsize = 10)
par(mar = c(3.3, 3.1, 5.7, 3.1), family = "sans", bg = config$background, xpd = NA)
draw_flow()
invisible(dev.off())

cat(png_path, "\n", svg_path, "\n", sep = "")
