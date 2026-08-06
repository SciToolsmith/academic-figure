locate_script <- function() {
  arguments <- commandArgs(trailingOnly = FALSE)
  file_arguments <- arguments[grepl("^--file=", arguments)]
  if (length(file_arguments) > 0) {
    return(normalizePath(sub("^--file=", "", file_arguments[[1]]), winslash = "/", mustWork = TRUE))
  }
  frames <- sys.frames()
  if (length(frames) > 0) {
    for (index in rev(seq_along(frames))) {
      source_file <- frames[[index]]$ofile
      if (!is.null(source_file)) {
        return(normalizePath(source_file, winslash = "/", mustWork = TRUE))
      }
    }
  }
  stop("Unable to determine the script location")
}

script_directory <- dirname(locate_script())

locate_input <- function(name) {
  candidates <- c(file.path(script_directory, name), file.path(script_directory, "data", name))
  existing <- candidates[file.exists(candidates)]
  if (length(existing) == 0) {
    stop(paste("Required input not found:", name))
  }
  existing[[1]]
}

clamp <- function(value, lower = 0, upper = 1) {
  pmin(pmax(value, lower), upper)
}

blend <- function(color_start, color_end, value) {
  value <- clamp(value)
  start <- grDevices::col2rgb(color_start)[, 1]
  end <- grDevices::col2rgb(color_end)[, 1]
  mixed <- start + (end - start) * value
  grDevices::rgb(mixed[[1]], mixed[[2]], mixed[[3]], maxColorValue = 255)
}

contrast_text <- function(color) {
  rgb_values <- grDevices::col2rgb(color)[, 1] / 255
  luminance <- 0.2126 * rgb_values[[1]] + 0.7152 * rgb_values[[2]] + 0.0722 * rgb_values[[3]]
  if (luminance < 0.48) "#FFFFFF" else "#1C1F21"
}

draw_output_icon <- function(x, y, width, height, kind, color = "#1F2528", line_width = 0.75) {
  size <- min(width, height) * 0.64
  left <- x + (width - size) / 2
  bottom <- y + (height - size) / 2
  if (kind == "Features") {
    gap <- size * 0.08
    cell <- (size - 2 * gap) / 3
    for (row in 0:2) {
      for (column in 0:2) {
        graphics::rect(
          left + column * (cell + gap),
          bottom + row * (cell + gap),
          left + column * (cell + gap) + cell,
          bottom + row * (cell + gap) + cell,
          col = NA,
          border = color,
          lwd = line_width
        )
      }
    }
  } else if (kind == "Embedding") {
    points_matrix <- matrix(
      c(
        0.19, 0.20,
        0.30, 0.38,
        0.22, 0.59,
        0.45, 0.25,
        0.51, 0.49,
        0.43, 0.72,
        0.67, 0.34,
        0.73, 0.61,
        0.82, 0.77
      ),
      ncol = 2,
      byrow = TRUE
    )
    graphics::segments(
      c(left + 0.08 * size, left + 0.08 * size),
      c(bottom + 0.92 * size, bottom + 0.08 * size),
      c(left + 0.08 * size, left + 0.92 * size),
      c(bottom + 0.08 * size, bottom + 0.08 * size),
      col = color,
      lwd = line_width
    )
    graphics::symbols(
      left + points_matrix[, 1] * size,
      bottom + points_matrix[, 2] * size,
      circles = rep(size * 0.047, nrow(points_matrix)),
      inches = FALSE,
      add = TRUE,
      bg = color,
      fg = color
    )
  } else if (kind == "Graph") {
    points_matrix <- matrix(
      c(
        0.18, 0.20,
        0.17, 0.77,
        0.51, 0.48,
        0.82, 0.22,
        0.83, 0.78
      ),
      ncol = 2,
      byrow = TRUE
    )
    edges <- matrix(c(1, 2, 1, 3, 2, 3, 3, 4, 3, 5, 4, 5), ncol = 2, byrow = TRUE)
    for (edge_index in seq_len(nrow(edges))) {
      source <- edges[edge_index, 1]
      target <- edges[edge_index, 2]
      graphics::segments(
        left + points_matrix[source, 1] * size,
        bottom + points_matrix[source, 2] * size,
        left + points_matrix[target, 1] * size,
        bottom + points_matrix[target, 2] * size,
        col = color,
        lwd = line_width
      )
    }
    graphics::symbols(
      left + points_matrix[, 1] * size,
      bottom + points_matrix[, 2] * size,
      circles = rep(size * 0.068, nrow(points_matrix)),
      inches = FALSE,
      add = TRUE,
      bg = color,
      fg = color
    )
  }
}

summary_data <- utils::read.csv(
  locate_input("scib_summary.csv"),
  stringsAsFactors = FALSE,
  check.names = FALSE
)
column_info <- utils::read.csv(
  locate_input("column_info.csv"),
  stringsAsFactors = FALSE,
  check.names = FALSE,
  na.strings = character()
)
column_groups <- utils::read.csv(
  locate_input("column_group.csv"),
  stringsAsFactors = FALSE,
  check.names = FALSE,
  na.strings = character()
)

required_summary <- c("method", "output", "features", "scaling", "avg_rank")
missing_summary <- setdiff(required_summary, names(summary_data))
if (length(missing_summary) > 0) {
  stop(paste("Missing summary columns:", paste(missing_summary, collapse = ", ")))
}

metric_info <- column_info[column_info$geom == "bar", c("id", "id_color", "name", "group"), drop = FALSE]
if (
  nrow(metric_info) == 0 ||
  any(metric_info$id == "") ||
  any(metric_info$id_color == "") ||
  any(metric_info$group == "")
) {
  stop("column_info.csv contains an incomplete metric definition")
}

missing_metrics <- setdiff(unique(c(metric_info$id, metric_info$id_color)), names(summary_data))
if (length(missing_metrics) > 0) {
  stop(paste("Missing metric columns:", paste(missing_metrics, collapse = ", ")))
}
score_values <- as.matrix(summary_data[, metric_info$id, drop = FALSE])
if (any((score_values < 0 | score_values > 1) & !is.na(score_values))) {
  stop("Score values must lie within 0 and 1")
}

group_order <- column_groups$group[
  column_groups$group != "Method" & column_groups$group %in% unique(metric_info$group)
]
if (!setequal(group_order, unique(metric_info$group))) {
  stop("Metric groups do not match column_group.csv")
}

summary_data$source_order <- seq_len(nrow(summary_data))
summary_data <- summary_data[
  order(summary_data$avg_rank, summary_data$source_order, na.last = TRUE),
  ,
  drop = FALSE
]
row.names(summary_data) <- NULL
summary_data$display_rank <- seq_len(nrow(summary_data))
summary_data$feature_label <- unname(c(HVG = "HVG", Full = "FULL")[summary_data$features])
summary_data$scaling_label <- unname(c(Scaled = "+", Unscaled = "-")[summary_data$scaling])

if (any(is.na(summary_data$feature_label)) || any(is.na(summary_data$scaling_label))) {
  stop("Unexpected features or scaling value")
}
if (!all(summary_data$output %in% c("Features", "Embedding", "Graph"))) {
  stop("Unexpected output value")
}

for (rank_column in metric_info$id_color) {
  summary_data[[paste0("_top_", rank_column)]] <- rank(
    summary_data[[rank_column]],
    ties.method = "min",
    na.last = "keep"
  )
}

group_colors <- list(
  RNA = c(strong = "#1D4E89", pale = "#E8F0F6", header = "#DCE9F2"),
  Simulations = c(strong = "#176B3A", pale = "#E7F3E9", header = "#DDEEE2"),
  Usability = c(strong = "#B45309", pale = "#FCECD3", header = "#F7E4C7"),
  Scalability = c(strong = "#3F454B", pale = "#ECEDEF", header = "#E2E4E6")
)
fallback_colors <- c(strong = "#365F74", pale = "#E8EFF2", header = "#E2EAED")

colors_for_group <- function(group) {
  if (group %in% names(group_colors)) group_colors[[group]] else fallback_colors
}

rank_bounds <- list()
for (group in group_order) {
  group_metric_info <- metric_info[metric_info$group == group, , drop = FALSE]
  rank_values <- unlist(
    lapply(group_metric_info$id_color, function(column) summary_data[[column]]),
    use.names = FALSE
  )
  rank_bounds[[group]] <- c(minimum = 1, maximum = max(rank_values, na.rm = TRUE))
}

left_labels <- c("Rank", "Method", "Output", "Features", "Scaling")
left_widths <- c(0.58, 2.18, 0.72, 0.86, 0.72)
metric_widths <- ifelse(grepl("human/mouse", metric_info$name, ignore.case = TRUE), 1.22, 0.96)
widths <- c(left_widths, metric_widths)
x_edges <- c(0, cumsum(widths))
total_width <- tail(x_edges, 1)
row_height <- 0.49
legend_height <- 1.95
label_height <- 0.78
group_height <- 0.40
title_height <- 0.88
data_height <- nrow(summary_data) * row_height
table_bottom <- legend_height
header_bottom <- table_bottom + data_height
group_bottom <- header_bottom + label_height
title_bottom <- group_bottom + group_height
total_height <- title_bottom + title_height
method_span_end <- x_edges[length(left_labels) + 1]
group_spans <- list(Method = c(start = 0, end = method_span_end))

for (group in group_order) {
  indices <- which(metric_info$group == group)
  first_index <- min(indices)
  last_index <- max(indices)
  group_spans[[group]] <- c(
    start = x_edges[length(left_labels) + first_index],
    end = x_edges[length(left_labels) + last_index + 1]
  )
}

output_path <- file.path(script_directory, "single_cell_benchmark_table_heatmap_r.png")
if (requireNamespace("ragg", quietly = TRUE)) {
  ragg::agg_png(
    output_path,
    width = total_width * 0.92,
    height = total_height * 0.92,
    units = "in",
    res = 360,
    background = "#FCFCFA"
  )
} else {
  grDevices::png(
    output_path,
    width = total_width * 0.92,
    height = total_height * 0.92,
    units = "in",
    res = 360,
    type = if (capabilities("cairo")) "cairo-png" else getOption("bitmapType"),
    bg = "#FCFCFA"
  )
}
graphics::par(mar = c(0, 0, 0, 0), xaxs = "i", yaxs = "i", family = "sans")
graphics::plot.new()
graphics::plot.window(xlim = c(0, total_width), ylim = c(0, total_height))

graphics::text(
  0,
  title_bottom + 0.62,
  "Benchmark summary of single-cell data integration methods",
  adj = c(0, 0.5),
  cex = 1.52,
  font = 2,
  col = "#1C2224"
)
graphics::text(
  0,
  title_bottom + 0.25,
  "Twenty configurations ordered by average rank; visual encodings retain the source scores, ranks and missing values.",
  adj = c(0, 0.5),
  cex = 0.77,
  col = "#596166"
)

group_header_colors <- list(Method = "#D9DAD7")
for (group in group_order) {
  group_header_colors[[group]] <- colors_for_group(group)[["header"]]
}

for (group in names(group_spans)) {
  span <- group_spans[[group]]
  graphics::rect(
    span[["start"]],
    group_bottom,
    span[["end"]],
    group_bottom + group_height,
    col = group_header_colors[[group]],
    border = "#FFFFFF",
    lwd = 1
  )
  graphics::text(
    mean(span),
    group_bottom + group_height / 2,
    group,
    cex = 0.82,
    font = 2,
    col = "#24292B"
  )
}

metric_header_labels <- gsub(
  "Immune \\(human/mouse\\)",
  "Immune\n(human /\nmouse)",
  metric_info$name
)
metric_header_labels <- gsub("Immune \\(human\\)", "Immune\n(human)", metric_header_labels)
metric_header_labels <- gsub("Mouse brain", "Mouse\nbrain", metric_header_labels)
header_labels <- c(left_labels, metric_header_labels)

for (column_index in seq_along(header_labels)) {
  x_start <- x_edges[column_index]
  width <- widths[column_index]
  graphics::rect(
    x_start,
    header_bottom,
    x_start + width,
    header_bottom + label_height,
    col = "#F6F6F3",
    border = "#FFFFFF",
    lwd = 0.8
  )
  graphics::text(
    x_start + width / 2,
    header_bottom + label_height / 2,
    header_labels[[column_index]],
    cex = 0.68,
    font = 2,
    col = "#343A3D"
  )
}

for (row_index in seq_len(nrow(summary_data))) {
  row_data <- summary_data[row_index, , drop = FALSE]
  y_start <- table_bottom + (nrow(summary_data) - row_index) * row_height
  row_color <- if (row_index %% 2 == 1) "#F1F2F0" else "#FCFCFA"
  graphics::rect(
    0,
    y_start,
    total_width,
    y_start + row_height,
    col = row_color,
    border = NA
  )
  graphics::text(
    x_edges[1] + widths[1] / 2,
    y_start + row_height / 2,
    row_data$display_rank,
    cex = 0.73,
    col = "#202527"
  )
  graphics::text(
    x_edges[2] + 0.10,
    y_start + row_height / 2,
    row_data$method,
    adj = c(0, 0.5),
    cex = 0.74,
    font = if (row_index <= 3) 2 else 1,
    col = "#1B2022"
  )
  draw_output_icon(
    x_edges[3],
    y_start,
    widths[3],
    row_height,
    row_data$output
  )
  feature_color <- if (row_data$feature_label == "HVG") "#176B3A" else "#63686B"
  graphics::text(
    x_edges[4] + widths[4] / 2,
    y_start + row_height / 2,
    row_data$feature_label,
    cex = 0.70,
    font = 2,
    col = feature_color
  )
  graphics::text(
    x_edges[5] + widths[5] / 2,
    y_start + row_height / 2,
    row_data$scaling_label,
    cex = 0.88,
    font = 2,
    col = "#202527"
  )
  for (metric_offset in seq_len(nrow(metric_info))) {
    metric <- metric_info[metric_offset, , drop = FALSE]
    column_index <- length(left_labels) + metric_offset
    x_start <- x_edges[column_index]
    width <- widths[column_index]
    score <- row_data[[metric$id]]
    rank_value <- row_data[[metric$id_color]]
    inset_x <- 0.07
    inset_y <- 0.075
    cell_width <- width - 2 * inset_x
    cell_height <- row_height - 2 * inset_y
    graphics::rect(
      x_start + inset_x,
      y_start + inset_y,
      x_start + inset_x + cell_width,
      y_start + inset_y + cell_height,
      col = "#F5F5F2",
      border = "#B8BCBC",
      lwd = 0.38
    )
    if (is.na(score) || is.na(rank_value)) {
      graphics::segments(
        x_start + inset_x + 0.05,
        y_start + inset_y + 0.05,
        x_start + inset_x + cell_width - 0.05,
        y_start + inset_y + cell_height - 0.05,
        col = "#A9ADAD",
        lwd = 0.55
      )
      graphics::text(
        x_start + width / 2,
        y_start + row_height / 2,
        "NA",
        cex = 0.55,
        col = "#777D7F"
      )
    } else {
      bounds <- rank_bounds[[metric$group]]
      normalized_rank <- if (bounds[["maximum"]] > bounds[["minimum"]]) {
        (rank_value - bounds[["minimum"]]) / (bounds[["maximum"]] - bounds[["minimum"]])
      } else {
        0
      }
      colors <- colors_for_group(metric$group)
      fill <- blend(colors[["strong"]], colors[["pale"]], normalized_rank)
      bar_width <- cell_width * score
      graphics::rect(
        x_start + inset_x,
        y_start + inset_y,
        x_start + inset_x + bar_width,
        y_start + inset_y + cell_height,
        col = fill,
        border = NA
      )
      display_position <- row_data[[paste0("_top_", metric$id_color)]]
      if (!is.na(display_position) && display_position <= 3) {
        label_x <- x_start + inset_x + max(min(bar_width / 2, cell_width - 0.10), 0.10)
        graphics::text(
          label_x,
          y_start + row_height / 2,
          as.integer(display_position),
          cex = 0.68,
          font = 2,
          col = contrast_text(fill)
        )
      }
    }
  }
}

for (x_position in x_edges) {
  graphics::segments(
    x_position,
    table_bottom,
    x_position,
    group_bottom + group_height,
    col = "#FFFFFF",
    lwd = 0.42
  )
}

for (group in names(group_spans)) {
  span <- group_spans[[group]]
  graphics::segments(
    span[["start"]],
    table_bottom,
    span[["start"]],
    group_bottom + group_height,
    col = "#B8BCBC",
    lwd = 0.65
  )
}

last_span <- group_spans[[tail(names(group_spans), 1)]]
graphics::segments(
  last_span[["end"]],
  table_bottom,
  last_span[["end"]],
  group_bottom + group_height,
  col = "#B8BCBC",
  lwd = 0.65
)
graphics::segments(0, table_bottom, total_width, table_bottom, col = "#9EA3A3", lwd = 0.65)

legend_title_y <- 1.58
legend_bar_y <- 1.14
legend_bar_height <- 0.20
graphics::text(
  0,
  legend_title_y,
  "Configuration",
  adj = c(0, 0.5),
  cex = 0.74,
  font = 2,
  col = "#2A3032"
)

legend_cursor <- 0.95
output_legend <- list(
  c(kind = "Features", label = "Features"),
  c(kind = "Embedding", label = "Embedding"),
  c(kind = "Graph", label = "Graph")
)

for (legend_item in output_legend) {
  draw_output_icon(
    legend_cursor,
    1.03,
    0.40,
    0.40,
    legend_item[["kind"]],
    line_width = 0.68
  )
  graphics::text(
    legend_cursor + 0.44,
    1.23,
    legend_item[["label"]],
    adj = c(0, 0.5),
    cex = 0.59,
    col = "#4B5255"
  )
  legend_cursor <- legend_cursor + 1.22
}

graphics::text(0, 0.80, "Features", adj = c(0, 0.5), cex = 0.60, font = 2, col = "#4B5255")
graphics::text(0.75, 0.80, "HVG", adj = c(0, 0.5), cex = 0.60, col = "#176B3A")
graphics::text(1.25, 0.80, "FULL", adj = c(0, 0.5), cex = 0.60, col = "#63686B")
graphics::text(2.05, 0.80, "Scaling", adj = c(0, 0.5), cex = 0.60, font = 2, col = "#4B5255")
graphics::text(2.75, 0.80, "+ scaled", adj = c(0, 0.5), cex = 0.60, col = "#4B5255")
graphics::text(3.65, 0.80, "- unscaled", adj = c(0, 0.5), cex = 0.60, col = "#4B5255")

for (group in group_order) {
  span <- group_spans[[group]]
  gradient_start <- span[["start"]] + 0.08
  gradient_end <- span[["end"]] - 0.08
  colors <- colors_for_group(group)
  graphics::text(
    span[["start"]],
    legend_title_y,
    paste(group, "rank"),
    adj = c(0, 0.5),
    cex = 0.74,
    font = 2,
    col = "#2A3032"
  )
  segments_count <- 40
  bar_width <- (gradient_end - gradient_start) / segments_count
  for (segment_index in 0:(segments_count - 1)) {
    value <- segment_index / (segments_count - 1)
    graphics::rect(
      gradient_start + segment_index * bar_width,
      legend_bar_y,
      gradient_start + (segment_index + 1) * bar_width + 0.002,
      legend_bar_y + legend_bar_height,
      col = blend(colors[["strong"]], colors[["pale"]], value),
      border = NA
    )
  }
  graphics::rect(
    gradient_start,
    legend_bar_y,
    gradient_end,
    legend_bar_y + legend_bar_height,
    col = NA,
    border = "#6E7476",
    lwd = 0.4
  )
  bounds <- rank_bounds[[group]]
  graphics::text(
    gradient_start,
    0.94,
    paste0(as.integer(bounds[["minimum"]]), " best"),
    adj = c(0, 0.5),
    cex = 0.54,
    col = "#596166"
  )
  graphics::text(
    gradient_end,
    0.94,
    paste0(format(bounds[["maximum"]], trim = TRUE), " lower"),
    adj = c(1, 0.5),
    cex = 0.54,
    col = "#596166"
  )
}

graphics::text(
  0,
  0.34,
  "Bar length = score (0-1). Fill = source rank on a shared scale within each group. Numerals = top-three position among the displayed configurations; ties share a position. NA = not available.",
  adj = c(0, 0.5),
  cex = 0.58,
  col = "#5C6366"
)
graphics::text(
  0,
  0.10,
  "Data source: bundled scib_summary.csv. The unrelated local PDF was not used.",
  adj = c(0, 0.5),
  cex = 0.53,
  col = "#7A8082"
)

grDevices::dev.off()
