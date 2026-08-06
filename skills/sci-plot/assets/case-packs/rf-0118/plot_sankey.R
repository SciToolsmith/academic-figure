script_path <- local({
  frames <- sys.frames()
  paths <- vapply(frames, function(frame) if (is.null(frame$ofile)) "" else as.character(frame$ofile), character(1))
  paths <- paths[nzchar(paths)]
  if (length(paths)) return(normalizePath(tail(paths, 1), winslash = "/", mustWork = TRUE))
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- sub("^--file=", "", args[grepl("^--file=", args)])
  if (length(file_arg)) return(normalizePath(file_arg[[1]], winslash = "/", mustWork = TRUE))
  stop("Cannot determine the script path")
})
base_dir <- dirname(script_path)
if (!requireNamespace("readxl", quietly = TRUE)) stop("Package 'readxl' is required")
require_columns <- function(data, columns, source) {
  missing <- setdiff(columns, names(data))
  if (length(missing)) stop(sprintf("%s is missing required columns: %s", source, paste(missing, collapse = ", ")))
}
ordered_unique <- function(values) values[!duplicated(values)]
totals_by <- function(data, column) {
  result <- tapply(data$.weight, data[[column]], sum)
  result[order(result, decreasing = TRUE)]
}
make_palette <- function(size, start) {
  if (!size) return(character())
  grDevices::hcl(h = (start + (seq_len(size) - 1) * 222.492) %% 360, c = 55, l = 60)
}
adjust_positions <- function(values, minimum, lower = 0.025, upper = 0.975) {
  order_index <- order(values)
  placed <- pmin(pmax(values[order_index], lower), upper)
  if (length(placed) > 1) {
    for (i in 2:length(placed)) placed[i] <- max(placed[i], placed[i - 1] + minimum)
  }
  if (length(placed) && tail(placed, 1) > upper) {
    placed <- placed - (tail(placed, 1) - upper)
    if (length(placed) > 1) {
      for (i in seq(length(placed) - 1, 1)) placed[i] <- min(placed[i], placed[i + 1] - minimum)
    }
  }
  if (length(placed) && placed[1] < lower) placed <- placed + lower - placed[1]
  result <- numeric(length(values))
  result[order_index] <- placed
  result
}
build_flow <- function(data, stages, orders, weight_column = NULL) {
  data <- as.data.frame(data, stringsAsFactors = FALSE)
  for (column in stages) data[[column]] <- as.character(data[[column]])
  data$.weight <- if (is.null(weight_column)) rep(1, nrow(data)) else as.numeric(data[[weight_column]])
  if (any(!is.finite(data$.weight)) || any(data$.weight <= 0)) stop("All flow weights must be finite and positive")
  total <- sum(data$.weight)
  stage_orders <- vector("list", length(stages))
  for (i in seq_along(stages)) {
    observed <- ordered_unique(data[[stages[i]]])
    stage_orders[[i]] <- c(orders[[i]][orders[[i]] %in% observed], observed[!observed %in% orders[[i]]])
  }
  maximum_nodes <- max(lengths(stage_orders))
  gap <- if (maximum_nodes > 24) 0.006 else 0.012
  scale <- (0.88 - gap * (maximum_nodes - 1)) / total
  starts <- c(205, 11, 151, 277)
  nodes <- vector("list", length(stages))
  for (i in seq_along(stages)) {
    totals <- tapply(data$.weight, data[[stages[i]]], sum)
    order_values <- stage_orders[[i]]
    values <- as.numeric(totals[order_values])
    colors <- make_palette(length(order_values), starts[(i - 1) %% length(starts) + 1])
    occupied <- total * scale + gap * (length(order_values) - 1)
    cursor <- 0.5 + occupied / 2
    y1 <- numeric(length(order_values))
    y0 <- numeric(length(order_values))
    for (j in seq_along(order_values)) {
      y1[j] <- cursor
      y0[j] <- cursor - values[j] * scale
      cursor <- y0[j] - gap
    }
    nodes[[i]] <- data.frame(name = order_values, value = values, y1 = y1, y0 = y0, color = colors, stringsAsFactors = FALSE)
  }
  links_by_gap <- vector("list", length(stages) - 1)
  for (i in seq_len(length(stages) - 1)) {
    source_column <- stages[i]
    target_column <- stages[i + 1]
    links <- aggregate(data$.weight, by = list(source = data[[source_column]], target = data[[target_column]]), FUN = sum)
    names(links)[3] <- "weight"
    links$source_index <- match(links$source, nodes[[i]]$name)
    links$target_index <- match(links$target, nodes[[i + 1]]$name)
    links$sy1 <- links$sy0 <- links$ty1 <- links$ty0 <- NA_real_
    source_cursor <- stats::setNames(nodes[[i]]$y1, nodes[[i]]$name)
    for (row_index in order(links$source_index, links$target_index)) {
      source <- links$source[row_index]
      height <- links$weight[row_index] * scale
      links$sy1[row_index] <- source_cursor[[source]]
      links$sy0[row_index] <- source_cursor[[source]] - height
      source_cursor[[source]] <- source_cursor[[source]] - height
    }
    target_cursor <- stats::setNames(nodes[[i + 1]]$y1, nodes[[i + 1]]$name)
    for (row_index in order(links$target_index, links$source_index)) {
      target <- links$target[row_index]
      height <- links$weight[row_index] * scale
      links$ty1[row_index] <- target_cursor[[target]]
      links$ty0[row_index] <- target_cursor[[target]] - height
      target_cursor[[target]] <- target_cursor[[target]] - height
    }
    links_by_gap[[i]] <- links
  }
  list(stages = stages, nodes = nodes, links = links_by_gap, total = total)
}
draw_ribbon <- function(x0, x1, row, source_color, target_color, segments = 30) {
  t <- seq(0, 1, length.out = segments + 1)
  smooth <- t * t * (3 - 2 * t)
  x <- x0 + (x1 - x0) * t
  upper <- row$sy1 + (row$ty1 - row$sy1) * smooth
  lower <- row$sy0 + (row$ty0 - row$sy0) * smooth
  colors <- grDevices::colorRampPalette(c(source_color, target_color), space = "Lab")(segments)
  colors <- grDevices::adjustcolor(colors, alpha.f = 0.52)
  for (i in seq_len(segments)) {
    polygon(c(x[i], x[i + 1], x[i + 1], x[i]), c(upper[i], upper[i + 1], lower[i + 1], lower[i]), col = colors[i], border = NA)
  }
}
format_value <- function(value, integer) {
  if (integer) format(round(value), big.mark = ",", scientific = FALSE, trim = TRUE) else sprintf("%.1f", value)
}
draw_label <- function(x, y, label, align, cex) {
  width <- strwidth(label, cex = cex)
  height <- strheight(label, cex = cex)
  if (align == 0) {
    rect(x - 0.006, y - height * 0.62, x + width + 0.012, y + height * 0.62, col = grDevices::adjustcolor("#FFFFFF", alpha.f = 0.79), border = NA)
  } else {
    rect(x - width - 0.012, y - height * 0.62, x + 0.006, y + height * 0.62, col = grDevices::adjustcolor("#FFFFFF", alpha.f = 0.79), border = NA)
  }
  text(x, y, label, adj = c(align, 0.5), cex = cex, col = "#17222B")
}
draw_flow <- function(flow, headers, panel_title, subtitle, integer) {
  stage_count <- length(flow$stages)
  x_positions <- seq(0, stage_count - 1)
  node_width <- 0.055
  plot.new()
  plot.window(xlim = c(-0.48, stage_count - 1 + 0.82), ylim = c(-0.03, 1.055), xaxs = "i", yaxs = "i")
  rect(par("usr")[1], par("usr")[3], par("usr")[2], par("usr")[4], col = "#F8F7F3", border = NA)
  for (stage_index in seq_along(flow$links)) {
    links <- flow$links[[stage_index]]
    source_nodes <- flow$nodes[[stage_index]]
    target_nodes <- flow$nodes[[stage_index + 1]]
    for (row_index in order(links$weight, decreasing = TRUE)) {
      row <- links[row_index, , drop = FALSE]
      source_color <- source_nodes$color[match(row$source, source_nodes$name)]
      target_color <- target_nodes$color[match(row$target, target_nodes$name)]
      draw_ribbon(x_positions[stage_index] + node_width / 2, x_positions[stage_index + 1] - node_width / 2, row, source_color, target_color)
    }
  }
  for (stage_index in seq_along(flow$nodes)) {
    stage_nodes <- flow$nodes[[stage_index]]
    centers <- (stage_nodes$y0 + stage_nodes$y1) / 2
    minimum <- if (nrow(stage_nodes) > 20) 0.026 else 0.032
    label_positions <- adjust_positions(centers, minimum)
    for (i in seq_len(nrow(stage_nodes))) {
      height <- max(stage_nodes$y1[i] - stage_nodes$y0[i], 0.0011)
      center <- centers[i]
      rect(x_positions[stage_index] - node_width / 2, center - height / 2, x_positions[stage_index] + node_width / 2, center + height / 2, col = stage_nodes$color[i], border = "#FFFFFF", lwd = 0.45)
      label <- paste0(stage_nodes$name[i], "  ", format_value(stage_nodes$value[i], integer))
      if (stage_index == 1) {
        text_x <- x_positions[stage_index] - node_width / 2 - 0.025
        align <- 1
        anchor_x <- x_positions[stage_index] - node_width / 2
      } else {
        text_x <- x_positions[stage_index] + node_width / 2 + 0.025
        align <- 0
        anchor_x <- x_positions[stage_index] + node_width / 2
      }
      if (abs(label_positions[i] - center) > 0.004) segments(anchor_x, center, text_x, label_positions[i], col = "#8B959D", lwd = 0.38)
      draw_label(text_x, label_positions[i], label, align, if (nrow(stage_nodes) > 20) 0.48 else 0.58)
    }
    text(x_positions[stage_index], 1.016, toupper(headers[stage_index]), adj = c(0.5, 0), cex = 0.68, font = 2, col = "#52616B")
  }
  mtext(panel_title, side = 3, line = 2.5, adj = 0, cex = 1.04, font = 2, col = "#15252D")
  mtext(subtitle, side = 3, line = 1.25, adj = 0, cex = 0.69, col = "#53636C")
}
data1 <- as.data.frame(readxl::read_xlsx(file.path(base_dir, "data1.xlsx")), stringsAsFactors = FALSE)
data2 <- as.data.frame(readxl::read_xlsx(file.path(base_dir, "data2.xlsx")), stringsAsFactors = FALSE)
require_columns(data1, c("Timeline", "Lineages Distribution", "Geographic Location", "P.M.A.s"), "data1.xlsx")
require_columns(data2, c("cluster", "mRNA1", "mRNA2", "Freq"), "data2.xlsx")
if (anyNA(data1[c("Timeline", "Lineages Distribution", "Geographic Location")])) stop("data1.xlsx contains missing values in the first three stages")
data1$Timeline <- as.character(data1$Timeline)
data1$`Lineages Distribution` <- as.character(data1$`Lineages Distribution`)
data1$`Geographic Location` <- as.character(data1$`Geographic Location`)
data1$`P.M.A.s / status` <- ifelse(is.na(data1$P.M.A.s), "Outside China / not applicable", as.character(data1$P.M.A.s))
if (anyNA(data2[c("cluster", "mRNA1", "mRNA2", "Freq")])) stop("data2.xlsx contains missing flow values")
data2$cluster <- as.character(data2$cluster)
data2$mRNA1 <- as.character(data2$mRNA1)
data2$mRNA2 <- as.character(data2$mRNA2)
data1$.weight <- 1
timeline_order <- sort(unique(data1$Timeline))
lineage_order <- intersect(c("Paraphyletic cluster", "Sublineage 8.7"), unique(data1$`Lineages Distribution`))
geographic_totals <- totals_by(data1, "Geographic Location")
geographic_order <- c(setdiff(names(geographic_totals), "China"), intersect("China", names(geographic_totals)))
pma_totals <- totals_by(data1, "P.M.A.s / status")
pma_order <- c(intersect("Outside China / not applicable", names(pma_totals)), setdiff(names(pma_totals), "Outside China / not applicable"))
flow1 <- build_flow(data1, c("Timeline", "Lineages Distribution", "Geographic Location", "P.M.A.s / status"), list(timeline_order, lineage_order, geographic_order, pma_order))
data2$.weight <- as.numeric(data2$Freq)
cluster_order <- names(totals_by(data2, "cluster"))
mrna1_order <- names(totals_by(data2, "mRNA1"))
mrna2_order <- names(totals_by(data2, "mRNA2"))
flow2 <- build_flow(data2, c("cluster", "mRNA1", "mRNA2"), list(cluster_order, mrna1_order, mrna2_order), "Freq")
output <- file.path(base_dir, "case29_sankey_r.png")
if (requireNamespace("ragg", quietly = TRUE)) {
  ragg::agg_png(output, width = 19, height = 11.5, units = "in", res = 360, background = "#F8F7F3")
} else if (capabilities("cairo")) {
  grDevices::png(output, width = 19, height = 11.5, units = "in", res = 360, bg = "#F8F7F3", type = "cairo-png")
} else {
  grDevices::png(output, width = 19, height = 11.5, units = "in", res = 360, bg = "#F8F7F3")
}
layout(matrix(1:2, nrow = 1), widths = c(1.16, 0.84))
par(oma = c(2.6, 1.1, 5.2, 1.1), mar = c(0.2, 0.2, 4.1, 0.2), family = "sans")
draw_flow(flow1, c("Time window", "Lineage", "Country", "P.M.A.s / status"), "A  Isolate distribution across time, lineage and geography", sprintf("data1.xlsx · n = %s records · ribbon width = record count", format(nrow(data1), big.mark = ",")), TRUE)
draw_flow(flow2, c("Cluster", "mRNA 1", "mRNA 2"), "B  Weighted cluster–mRNA associations", sprintf("data2.xlsx · %s rows · Σ Freq = %.2f · ribbon width = Freq", nrow(data2), sum(data2$Freq)), FALSE)
mtext("Two independent alluvial datasets", side = 3, outer = TRUE, line = 3.45, adj = 0.015, cex = 1.52, font = 2, col = "#10242C")
mtext("Panels are intentionally separate: the workbooks contain no shared record-level key and use different flow measures.", side = 3, outer = TRUE, line = 1.85, adj = 0.015, cex = 0.82, col = "#53636C")
mtext(sprintf("Blank P.M.A.s values are retained as “Outside China / not applicable” (n = %s; every blank occurs outside China). Node values are totals within each stage.", format(sum(is.na(data1$P.M.A.s)), big.mark = ",")), side = 1, outer = TRUE, line = 0.75, adj = 0.015, cex = 0.68, col = "#5D6970")
invisible(dev.off())
cat(output, "\n")
