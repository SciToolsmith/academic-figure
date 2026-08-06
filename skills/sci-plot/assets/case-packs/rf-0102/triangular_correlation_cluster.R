resolve_script_dir <- function() {
  arguments <- commandArgs(trailingOnly = FALSE)
  file_argument <- grep("^--file=", arguments, value = TRUE)
  if (length(file_argument) > 0) {
    return(dirname(normalizePath(sub("^--file=", "", file_argument[[1]]), mustWork = TRUE)))
  }
  frames <- sys.frames()
  if (length(frames) > 0) {
    for (index in rev(seq_along(frames))) {
      source_file <- frames[[index]]$ofile
      if (!is.null(source_file)) {
        return(dirname(normalizePath(source_file, mustWork = TRUE)))
      }
    }
  }
  normalizePath(getwd(), mustWork = TRUE)
}

resolve_input <- function(script_dir, filename) {
  candidates <- c(
    file.path(script_dir, "data", filename),
    file.path(script_dir, filename)
  )
  existing <- candidates[file.exists(candidates)]
  if (length(existing) == 0) {
    stop(sprintf("Input file not found: %s", filename))
  }
  existing[[1]]
}

script_dir <- resolve_script_dir()
output_path <- file.path(script_dir, "triangular_correlation_cluster_r.png")
data_path <- resolve_input(script_dir, "data.csv")
group_path <- resolve_input(script_dir, "group.csv")

if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required")
}
if (!requireNamespace("patchwork", quietly = TRUE)) {
  stop("Package 'patchwork' is required")
}

data_frame <- read.csv(
  data_path,
  row.names = 1,
  check.names = FALSE,
  stringsAsFactors = FALSE
)
group_frame <- read.csv(
  group_path,
  check.names = FALSE,
  stringsAsFactors = FALSE,
  na.strings = character()
)

if (nrow(data_frame) < 3 || ncol(data_frame) < 2) {
  stop("data.csv must contain at least three observations and two variables")
}
if (anyDuplicated(rownames(data_frame)) || anyDuplicated(colnames(data_frame))) {
  stop("Observation identifiers and variable names must be unique")
}
if (!identical(names(group_frame), c("Bile acid", "order"))) {
  stop("group.csv must contain the columns 'Bile acid' and 'order'")
}
if (anyDuplicated(group_frame[["Bile acid"]])) {
  stop("Every variable must occur exactly once in group.csv")
}
if (!setequal(group_frame[["Bile acid"]], colnames(data_frame))) {
  missing_names <- setdiff(colnames(data_frame), group_frame[["Bile acid"]])
  extra_names <- setdiff(group_frame[["Bile acid"]], colnames(data_frame))
  stop(sprintf(
    "Variable/group mismatch; missing=%s; extra=%s",
    paste(missing_names, collapse = ", "),
    paste(extra_names, collapse = ", ")
  ))
}

numeric_data <- as.data.frame(
  lapply(data_frame, function(column) {
    converted <- suppressWarnings(as.numeric(column))
    if (any(is.na(converted) & !is.na(column))) {
      stop("data.csv contains non-numeric measurements")
    }
    converted
  }),
  check.names = FALSE
)
rownames(numeric_data) <- rownames(data_frame)
values <- as.matrix(numeric_data)
storage.mode(values) <- "double"

if (any(!is.finite(values))) {
  stop("data.csv contains non-finite values")
}
if (any(values < 0)) {
  stop("Log transformation requires non-negative measurements")
}

positive_values <- values[values > 0]
if (length(positive_values) == 0) {
  stop("At least one positive measurement is required")
}
minimum_positive <- min(positive_values)
pseudocount <- minimum_positive / 2
if (!isTRUE(all.equal(pseudocount, 0.005, tolerance = 1e-12))) {
  stop(sprintf(
    "Expected a minimum positive value of 0.01, observed %g",
    minimum_positive
  ))
}

transformed <- log10(values + pseudocount)
standard_deviation <- apply(transformed, 2, stats::sd)
if (any(standard_deviation == 0)) {
  stop(sprintf(
    "Correlation is undefined for constant variables: %s",
    paste(colnames(values)[standard_deviation == 0], collapse = ", ")
  ))
}

correlation <- stats::cor(transformed, method = "pearson")
if (any(!is.finite(correlation))) {
  stop("Correlation matrix contains non-finite values")
}
if (!isTRUE(all.equal(correlation, t(correlation), tolerance = 1e-12))) {
  stop("Correlation matrix is not symmetric")
}

distance_component <- 1 - correlation
if (min(distance_component) < -1e-10 || max(distance_component) > 2 + 1e-10) {
  stop("Correlation-derived distance is outside its valid range")
}
distance_component[distance_component < 0] <- 0
chord_distance <- sqrt(2 * distance_component)
chord_distance <- (chord_distance + t(chord_distance)) / 2
diag(chord_distance) <- 0
hierarchy <- stats::hclust(stats::as.dist(chord_distance), method = "average")
minimum_leaf <- integer(ncol(values) - 1)
for (merge_index in seq_len(ncol(values) - 1)) {
  children <- hierarchy$merge[merge_index, ]
  child_minimum <- vapply(children, function(child) {
    if (child < 0) {
      return(-child)
    }
    minimum_leaf[[child]]
  }, integer(1))
  if (child_minimum[[1]] > child_minimum[[2]]) {
    hierarchy$merge[merge_index, ] <- rev(children)
    child_minimum <- rev(child_minimum)
  }
  minimum_leaf[[merge_index]] <- min(child_minimum)
}
canonical_order <- function(node) {
  if (node < 0) {
    return(-node)
  }
  c(
    canonical_order(hierarchy$merge[node, 1]),
    canonical_order(hierarchy$merge[node, 2])
  )
}
hierarchy$order <- canonical_order(ncol(values) - 1)
variable_order <- hierarchy$order
ordered_names <- colnames(values)[variable_order]
ordered_correlation <- correlation[variable_order, variable_order, drop = FALSE]

if (!isTRUE(all.equal(
  unname(diag(ordered_correlation)),
  rep(1, ncol(values)),
  tolerance = 1e-10
))) {
  stop("Correlation diagonal validation failed")
}

group_labels <- stats::setNames(
  c(
    "Primary conjugated",
    "Primary unconjugated",
    "Secondary conjugated",
    "Secondary unconjugated",
    "Unassigned"
  ),
  c("priConjSum", "primarySum", "secConjSum", "secondarySum", "")
)
group_colors <- c(
  "Primary conjugated" = "#2A9D8F",
  "Primary unconjugated" = "#E9C46A",
  "Secondary conjugated" = "#457B9D",
  "Secondary unconjugated" = "#E76F51",
  "Unassigned" = "#B5B7BA"
)
unknown_codes <- setdiff(unique(group_frame$order), names(group_labels))
if (length(unknown_codes) > 0) {
  stop(sprintf("Unknown group codes: %s", paste(unknown_codes, collapse = ", ")))
}

group_lookup <- stats::setNames(group_frame$order, group_frame[["Bile acid"]])
ordered_codes <- unname(group_lookup[ordered_names])
ordered_groups <- ifelse(
  ordered_codes == "",
  "Unassigned",
  unname(group_labels[ordered_codes])
)
n_variables <- length(ordered_names)

heat_rows <- which(lower.tri(ordered_correlation, diag = TRUE), arr.ind = TRUE)
heat_data <- data.frame(
  x = heat_rows[, "col"],
  y = heat_rows[, "row"],
  correlation = ordered_correlation[heat_rows]
)
group_data <- data.frame(
  x = seq_len(n_variables),
  y = 1,
  group = factor(ordered_groups, levels = names(group_colors))
)

leaf_positions <- numeric(n_variables)
leaf_positions[hierarchy$order] <- seq_len(n_variables)
node_x <- numeric(n_variables - 1)
segment_rows <- vector("list", (n_variables - 1) * 3)
segment_index <- 1

for (merge_index in seq_len(n_variables - 1)) {
  children <- hierarchy$merge[merge_index, ]
  child_x <- numeric(2)
  child_height <- numeric(2)
  for (side in 1:2) {
    child <- children[[side]]
    if (child < 0) {
      child_x[[side]] <- leaf_positions[[-child]]
      child_height[[side]] <- 0
    } else {
      child_x[[side]] <- node_x[[child]]
      child_height[[side]] <- hierarchy$height[[child]]
    }
  }
  parent_height <- hierarchy$height[[merge_index]]
  node_x[[merge_index]] <- mean(child_x)
  segment_rows[[segment_index]] <- data.frame(
    x = child_x[[1]],
    xend = child_x[[1]],
    y = child_height[[1]],
    yend = parent_height
  )
  segment_rows[[segment_index + 1]] <- data.frame(
    x = child_x[[1]],
    xend = child_x[[2]],
    y = parent_height,
    yend = parent_height
  )
  segment_rows[[segment_index + 2]] <- data.frame(
    x = child_x[[2]],
    xend = child_x[[2]],
    y = child_height[[2]],
    yend = parent_height
  )
  segment_index <- segment_index + 3
}

dendrogram_data <- do.call(rbind, segment_rows)
palette <- c("#254E70", "#79A9C7", "#F7F5F0", "#E49773", "#9D2A32")

dendrogram_plot <- ggplot2::ggplot(dendrogram_data) +
  ggplot2::geom_segment(
    ggplot2::aes(x = x, xend = xend, y = y, yend = yend),
    linewidth = 0.28,
    color = "#344E41",
    lineend = "round"
  ) +
  ggplot2::scale_x_continuous(limits = c(0.5, n_variables + 0.5), expand = c(0, 0)) +
  ggplot2::scale_y_continuous(expand = ggplot2::expansion(mult = c(0, 0.06))) +
  ggplot2::labs(y = "Chord distance") +
  ggplot2::theme_minimal(base_family = "sans", base_size = 8) +
  ggplot2::theme(
    panel.grid = ggplot2::element_blank(),
    axis.title.x = ggplot2::element_blank(),
    axis.text.x = ggplot2::element_blank(),
    axis.ticks.x = ggplot2::element_blank(),
    axis.text.y = ggplot2::element_text(size = 6.5, color = "#52625B"),
    axis.title.y = ggplot2::element_text(size = 7.5, color = "#33413B"),
    plot.margin = ggplot2::margin(2, 76, 0, 0)
  )

group_plot <- ggplot2::ggplot(group_data, ggplot2::aes(x = x, y = y, fill = group)) +
  ggplot2::geom_tile(width = 1, height = 1) +
  ggplot2::scale_fill_manual(values = group_colors, drop = FALSE) +
  ggplot2::scale_x_continuous(limits = c(0.5, n_variables + 0.5), expand = c(0, 0)) +
  ggplot2::scale_y_continuous(limits = c(0.5, 1.5), expand = c(0, 0)) +
  ggplot2::guides(
    fill = ggplot2::guide_legend(
      title = "Bile acid class",
      ncol = 1,
      override.aes = list(width = 0.8, height = 0.8)
    )
  ) +
  ggplot2::theme_void(base_family = "sans") +
  ggplot2::theme(
    legend.position = "right",
    legend.title = ggplot2::element_text(size = 7.5),
    legend.text = ggplot2::element_text(size = 6.8),
    legend.key.height = grid::unit(3.2, "mm"),
    legend.margin = ggplot2::margin(0, 0, 0, 5),
    plot.margin = ggplot2::margin(0, 0, 0, 0)
  )

heatmap_plot <- ggplot2::ggplot(
  heat_data,
  ggplot2::aes(x = x, y = y, fill = correlation)
) +
  ggplot2::geom_tile(width = 1, height = 1) +
  ggplot2::geom_abline(
    intercept = 0,
    slope = 1,
    linewidth = 0.18,
    color = "#FFFFFF",
    alpha = 0.8
  ) +
  ggplot2::scale_fill_gradientn(
    colors = palette,
    values = scales::rescale(c(-1, -0.5, 0, 0.5, 1)),
    limits = c(-1, 1),
    breaks = c(-1, -0.5, 0, 0.5, 1),
    name = "Pearson correlation (r)"
  ) +
  ggplot2::scale_x_continuous(
    limits = c(0.5, n_variables + 0.5),
    breaks = seq_len(n_variables),
    labels = ordered_names,
    expand = c(0, 0)
  ) +
  ggplot2::scale_y_reverse(
    limits = c(n_variables + 0.5, 0.5),
    breaks = seq_len(n_variables),
    labels = ordered_names,
    expand = c(0, 0)
  ) +
  ggplot2::coord_fixed(clip = "off") +
  ggplot2::theme_minimal(base_family = "sans", base_size = 8) +
  ggplot2::theme(
    panel.grid = ggplot2::element_blank(),
    axis.title = ggplot2::element_blank(),
    axis.text.x = ggplot2::element_text(
      angle = 58,
      hjust = 1,
      vjust = 1,
      size = 5.6,
      color = "#26332D"
    ),
    axis.text.y = ggplot2::element_text(size = 5.6, color = "#26332D"),
    axis.ticks = ggplot2::element_line(linewidth = 0.25, color = "#89958F"),
    axis.ticks.length = grid::unit(1.2, "mm"),
    legend.title = ggplot2::element_text(size = 7.5),
    legend.text = ggplot2::element_text(size = 6.8),
    legend.key.height = grid::unit(25, "mm"),
    plot.margin = ggplot2::margin(0, 0, 0, 0)
  )

subtitle <- sprintf(
  "n = %d observations · Pearson r on log10(x + %.3f) · chord distance √[2(1 − r)] · average linkage",
  nrow(values),
  pseudocount
)
caption <- paste(
  "The 0.005 pseudocount equals half the smallest positive observation (0.01).",
  "The colored strip reports the supplied group annotation.",
  "Variables without a supplied class are shown as Unassigned."
)

combined <- (
  dendrogram_plot /
    group_plot /
    heatmap_plot +
    patchwork::plot_layout(heights = c(2.0, 0.30, 8.5), guides = "collect")
) +
  patchwork::plot_annotation(
    title = "Bile acid correlation structure",
    subtitle = paste(
      "Lower-triangular correlation matrix with hierarchical clustering",
      subtitle,
      sep = "\n"
    ),
    caption = caption,
    theme = ggplot2::theme(
      plot.title = ggplot2::element_text(
        family = "sans",
        size = 22,
        face = "bold",
        color = "#17251F",
        hjust = 0
      ),
      plot.subtitle = ggplot2::element_text(
        family = "sans",
        size = 8.5,
        color = "#52625B",
        lineheight = 1.45,
        hjust = 0
      ),
      plot.caption = ggplot2::element_text(
        family = "sans",
        size = 7.5,
        color = "#68766F",
        hjust = 0
      ),
      plot.margin = ggplot2::margin(16, 18, 16, 18)
    )
  ) &
  ggplot2::theme(
    legend.position = "right",
    legend.box = "vertical",
    legend.margin = ggplot2::margin(0, 0, 0, 6)
  )

ggplot2::ggsave(
  filename = output_path,
  plot = combined,
  width = 16,
  height = 14,
  units = "in",
  dpi = 300,
  bg = "white"
)

if (!file.exists(output_path) || file.info(output_path)$size <= 0) {
  stop(sprintf("Figure was not written: %s", output_path))
}

unassigned <- sum(group_frame$order == "")
cat(sprintf(
  paste0(
    "Saved: %s\n",
    "Observations: %d; variables: %d; unassigned groups: %d; ",
    "pseudocount: %.3f; correlation range: [%.3f, %.3f]\n"
  ),
  normalizePath(output_path, mustWork = TRUE),
  nrow(values),
  ncol(values),
  unassigned,
  pseudocount,
  min(correlation),
  max(correlation)
))
