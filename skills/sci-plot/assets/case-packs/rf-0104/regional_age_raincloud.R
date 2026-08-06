resolve_script_dir <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args, value = TRUE)
  if (length(file_arg) > 0) {
    return(dirname(normalizePath(sub("^--file=", "", file_arg[[1]]), winslash = "/", mustWork = TRUE)))
  }
  source_paths <- vapply(
    sys.frames(),
    function(frame) {
      if (!is.null(frame$ofile) && length(frame$ofile) > 0) as.character(frame$ofile[[1]]) else ""
    },
    character(1)
  )
  source_paths <- source_paths[nzchar(source_paths)]
  if (length(source_paths) > 0) {
    return(dirname(normalizePath(source_paths[[length(source_paths)]], winslash = "/", mustWork = TRUE)))
  }
  if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
    context_path <- rstudioapi::getSourceEditorContext()$path
    if (nzchar(context_path)) {
      return(dirname(normalizePath(context_path, winslash = "/", mustWork = TRUE)))
    }
  }
  normalizePath(getwd(), winslash = "/", mustWork = TRUE)
}

required_packages <- c("readxl", "ggplot2", "ragg")
missing_packages <- required_packages[!vapply(required_packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing_packages) > 0) {
  stop(sprintf("Missing required packages: %s", paste(missing_packages, collapse = ", ")), call. = FALSE)
}

script_dir <- resolve_script_dir()
input_path <- file.path(script_dir, "data.xlsx")
output_path <- file.path(script_dir, "regional_age_raincloud_r.png")
region_order <- c(
  "WesternEurope",
  "CentralEasternEurope",
  "SouthernEurope",
  "NorthernEurope",
  "CentralWesternAsia"
)
region_labels <- c(
  WesternEurope = "Western Europe",
  CentralEasternEurope = "Central/Eastern Europe",
  SouthernEurope = "Southern Europe",
  NorthernEurope = "Northern Europe",
  CentralWesternAsia = "Central/Western Asia"
)
colors <- c(
  WesternEurope = "#8FC4DD",
  CentralEasternEurope = "#C5B783",
  SouthernEurope = "#18A98B",
  NorthernEurope = "#E44D55",
  CentralWesternAsia = "#36413E"
)

data <- as.data.frame(readxl::read_xlsx(input_path, sheet = "Sheet1"))
required <- c("Individual ID", "Region", "Age average")
if (!identical(names(data), required)) {
  stop("Workbook columns do not match the expected schema", call. = FALSE)
}
if (anyNA(data[required])) {
  stop("Required fields contain missing values", call. = FALSE)
}
if (anyDuplicated(data[["Individual ID"]])) {
  stop("Individual identifiers must be unique", call. = FALSE)
}
if (!setequal(unique(data$Region), region_order)) {
  stop("Workbook regions do not match the expected categories", call. = FALSE)
}
data[["Age average"]] <- as.numeric(data[["Age average"]])
if (any(!is.finite(data[["Age average"]])) || any(data[["Age average"]] <= 0)) {
  stop("Age values must be finite and positive", call. = FALSE)
}
data$age_kyr <- data[["Age average"]] / 1000
data$Region <- factor(data$Region, levels = region_order)
axis_max <- ceiling(max(data$age_kyr) / 5) * 5
row_gap <- 1.30
base_map <- stats::setNames(rev(seq(0, by = row_gap, length.out = length(region_order))), region_order)
data$base_y <- unname(base_map[as.character(data$Region)])

density_data <- do.call(
  rbind,
  lapply(region_order, function(region) {
    values <- data$age_kyr[data$Region == region]
    bandwidth <- stats::sd(values) * length(values)^(-1 / 5)
    estimate <- stats::density(values, from = 0, to = axis_max, n = 900, bw = bandwidth, kernel = "gaussian")
    data.frame(
      Region = region,
      x = estimate$x,
      base = base_map[[region]],
      y = base_map[[region]] + estimate$y / max(estimate$y) * 0.42,
      stringsAsFactors = FALSE
    )
  })
)
density_data$Region <- factor(density_data$Region, levels = region_order)

summary_data <- do.call(
  rbind,
  lapply(region_order, function(region) {
    values <- data$age_kyr[data$Region == region]
    bandwidth <- stats::sd(values) * length(values)^(-1 / 5)
    quartiles <- stats::quantile(values, c(0.25, 0.5, 0.75), names = FALSE)
    iqr <- quartiles[[3]] - quartiles[[1]]
    lower <- min(values[values >= quartiles[[1]] - 1.5 * iqr])
    upper <- max(values[values <= quartiles[[3]] + 1.5 * iqr])
    cat(sprintf(
      "%s | n=%d | min=%.4g | median=%.4g | max=%.4g kyr BP | Scott bandwidth=%.4g kyr\n",
      region,
      length(values),
      min(values),
      quartiles[[2]],
      max(values),
      bandwidth
    ))
    data.frame(
      Region = region,
      base = base_map[[region]],
      q1 = quartiles[[1]],
      median = quartiles[[2]],
      q3 = quartiles[[3]],
      lower = lower,
      upper = upper,
      n = length(values),
      stringsAsFactors = FALSE
    )
  })
)
summary_data$Region <- factor(summary_data$Region, levels = region_order)

point_data <- do.call(
  rbind,
  lapply(region_order, function(region) {
    subset <- data[data$Region == region, , drop = FALSE]
    subset <- subset[order(subset$age_kyr, method = "radix"), , drop = FALSE]
    sequence <- seq.int(0, nrow(subset) - 1L)
    subset$point_x <- subset$age_kyr + 0.055 * sin(sequence * 2.399963)
    subset$point_y <- base_map[[region]] - 0.39 - 0.22 * ((sequence * 0.61803398875) %% 1)
    subset
  })
)

y_breaks <- unname(base_map[region_order])
y_labels <- vapply(
  region_order,
  function(region) sprintf(
    "atop('%s', italic(n)==%s)",
    region_labels[[region]],
    summary_data$n[summary_data$Region == region]
  ),
  character(1)
)

plot <- ggplot2::ggplot() +
  ggplot2::geom_ribbon(
    data = density_data,
    ggplot2::aes(x = x, ymin = base, ymax = y, fill = Region, group = Region),
    alpha = 0.92,
    color = NA
  ) +
  ggplot2::geom_line(
    data = density_data,
    ggplot2::aes(x = x, y = y, color = Region, group = Region),
    linewidth = 0.55
  ) +
  ggplot2::geom_segment(
    data = summary_data,
    ggplot2::aes(x = 0, xend = axis_max, y = base, yend = base, color = Region),
    linewidth = 0.35,
    alpha = 0.75
  ) +
  ggplot2::geom_segment(
    data = summary_data,
    ggplot2::aes(x = lower, xend = upper, y = base - 0.17, yend = base - 0.17),
    color = "#3F4845",
    linewidth = 0.55
  ) +
  ggplot2::geom_segment(
    data = summary_data,
    ggplot2::aes(x = lower, xend = lower, y = base - 0.225, yend = base - 0.115),
    color = "#3F4845",
    linewidth = 0.5
  ) +
  ggplot2::geom_segment(
    data = summary_data,
    ggplot2::aes(x = upper, xend = upper, y = base - 0.225, yend = base - 0.115),
    color = "#3F4845",
    linewidth = 0.5
  ) +
  ggplot2::geom_rect(
    data = summary_data,
    ggplot2::aes(xmin = q1, xmax = q3, ymin = base - 0.245, ymax = base - 0.095, fill = Region),
    color = "#3F4845",
    linewidth = 0.5,
    alpha = 0.55
  ) +
  ggplot2::geom_segment(
    data = summary_data,
    ggplot2::aes(x = median, xend = median, y = base - 0.245, yend = base - 0.095),
    color = "#FCFCFA",
    linewidth = 1.0
  ) +
  ggplot2::geom_point(
    data = point_data,
    ggplot2::aes(x = point_x, y = point_y),
    shape = 16,
    size = 0.75,
    color = "#6A716E",
    alpha = 0.46
  ) +
  ggplot2::scale_fill_manual(values = colors, guide = "none") +
  ggplot2::scale_color_manual(values = colors, guide = "none") +
  ggplot2::scale_x_reverse(
    limits = c(axis_max, 0),
    breaks = seq(axis_max, 0, by = -5),
    expand = c(0, 0)
  ) +
  ggplot2::scale_y_continuous(
    breaks = y_breaks,
    labels = parse(text = y_labels),
    limits = c(min(y_breaks) - 0.78, max(y_breaks) + 0.72),
    expand = c(0, 0)
  ) +
  ggplot2::labs(
    title = "Regional age distributions",
    subtitle = sprintf(
      "%s individuals \u00b7 source ages converted from years to kyr BP \u00b7 full %.2f\u2013%.2f kyr range shown",
      format(nrow(data), big.mark = ","),
      min(data$age_kyr),
      max(data$age_kyr)
    ),
    x = "Age (kyr BP)",
    y = NULL,
    caption = "Half-violin: Gaussian KDE (Scott bandwidth; each region normalized) \u00b7 box: median, IQR and 1.5\u00d7IQR whiskers \u00b7 dots: individuals"
  ) +
  ggplot2::theme_classic(base_size = 10) +
  ggplot2::theme(
    text = ggplot2::element_text(family = "sans", color = "#1D2723"),
    plot.background = ggplot2::element_rect(fill = "#FCFCFA", color = NA),
    panel.background = ggplot2::element_rect(fill = "#FCFCFA", color = NA),
    panel.grid.major.x = ggplot2::element_line(color = "#DDE2DF", linewidth = 0.35),
    panel.grid.minor = ggplot2::element_blank(),
    axis.line.y = ggplot2::element_blank(),
    axis.ticks.y = ggplot2::element_blank(),
    axis.text.y = ggplot2::element_text(size = 9.5, color = "#1D2723", hjust = 1, lineheight = 1.05, margin = ggplot2::margin(r = 10)),
    axis.text.x = ggplot2::element_text(color = "#41504A"),
    axis.title.x = ggplot2::element_text(color = "#1D2723", margin = ggplot2::margin(t = 8)),
    plot.title = ggplot2::element_text(size = 18, face = "bold", color = "#17231F", margin = ggplot2::margin(b = 4)),
    plot.subtitle = ggplot2::element_text(size = 9.3, color = "#52605A", margin = ggplot2::margin(b = 14)),
    plot.caption = ggplot2::element_text(size = 8.7, color = "#52605A", hjust = 0, margin = ggplot2::margin(t = 10)),
    plot.margin = ggplot2::margin(18, 18, 14, 24)
  )

ggplot2::ggsave(
  filename = output_path,
  plot = plot,
  width = 10,
  height = 7.6,
  units = "in",
  dpi = 400,
  device = ragg::agg_png,
  bg = "#FCFCFA"
)
if (!file.exists(output_path) || file.info(output_path)$size <= 0) {
  stop(sprintf("Failed to create output: %s", output_path), call. = FALSE)
}
cat(sprintf("Saved: %s\n", normalizePath(output_path, winslash = "/", mustWork = TRUE)))
