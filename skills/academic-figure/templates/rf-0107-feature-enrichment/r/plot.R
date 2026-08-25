#!/usr/bin/env Rscript

# Visualize supplied feature statistics and precomputed enrichment outputs using base R.

all_args <- commandArgs(trailingOnly = FALSE)
file_arg <- sub("^--file=", "", all_args[grep("^--file=", all_args)])
script_dir <- if (length(file_arg)) dirname(normalizePath(file_arg[[1]], mustWork = TRUE)) else getwd()
template_dir <- dirname(script_dir)

defaults <- list(
  features = "", curve = "", hits = "", summary = "",
  effect_threshold = "", significance_threshold = "",
  output_prefix = file.path(getwd(), "feature_enrichment_r"),
  title = "Supplied feature and precomputed enrichment views", dpi = 320L
)
max_curves <- 8L

parse_args <- function(args) {
  result <- defaults
  aliases <- c(features = "features", curve = "curve", hits = "hits", summary = "summary", `effect-threshold` = "effect_threshold", `significance-threshold` = "significance_threshold", `output-prefix` = "output_prefix", title = "title", dpi = "dpi")
  index <- 1L
  while (index <= length(args)) {
    token <- args[[index]]
    if (!startsWith(token, "--")) stop(sprintf("Unknown argument: %s", token), call. = FALSE)
    stripped <- substring(token, 3L)
    if (grepl("=", stripped, fixed = TRUE)) {
      pieces <- strsplit(stripped, "=", fixed = TRUE)[[1]]
      key <- pieces[[1]]; value <- paste(pieces[-1], collapse = "=")
    } else {
      key <- stripped; index <- index + 1L
      if (index > length(args)) stop(sprintf("Missing value for --%s", key), call. = FALSE)
      value <- args[[index]]
    }
    if (!key %in% names(aliases)) stop(sprintf("Unknown option: --%s", key), call. = FALSE)
    result[[aliases[[key]]]] <- value
    index <- index + 1L
  }
  data_supplied <- any(nzchar(unlist(result[c("features", "curve", "hits", "summary")])))
  if (!data_supplied) {
    result$features <- file.path(template_dir, "demo", "demo_features_seed107.csv")
    result$curve <- file.path(template_dir, "demo", "demo_ranked_curves_seed107.csv")
    result$hits <- file.path(template_dir, "demo", "demo_hits_seed107.csv")
    result$summary <- file.path(template_dir, "demo", "demo_summary_seed107.csv")
  }
  if (nzchar(result$hits) && !nzchar(result$curve)) stop("--hits requires --curve.", call. = FALSE)
  if (nzchar(result$summary) && !nzchar(result$curve)) stop("--summary requires --curve.", call. = FALSE)
  if (!nzchar(result$features) && !nzchar(result$curve)) stop("Provide --features, --curve, or both.", call. = FALSE)
  if (xor(nzchar(result$effect_threshold), nzchar(result$significance_threshold))) stop("Provide both threshold options together.", call. = FALSE)
  if (nzchar(result$effect_threshold)) {
    result$effect_threshold <- suppressWarnings(as.numeric(result$effect_threshold))
    result$significance_threshold <- suppressWarnings(as.numeric(result$significance_threshold))
    if (!is.finite(result$effect_threshold) || result$effect_threshold <= 0) stop("--effect-threshold must be > 0.", call. = FALSE)
    if (!is.finite(result$significance_threshold) || result$significance_threshold <= 0 || result$significance_threshold > 1) stop("--significance-threshold must lie in (0, 1].", call. = FALSE)
  } else {
    result$effect_threshold <- NA_real_; result$significance_threshold <- NA_real_
  }
  result$dpi <- suppressWarnings(as.integer(result$dpi))
  if (is.na(result$dpi) || result$dpi < 150L) stop("--dpi must be at least 150.", call. = FALSE)
  result
}

stop_contract <- function(message) stop(sprintf("Input validation failed: %s", message), call. = FALSE)
ordered_unique <- function(values) values[!duplicated(values)]

read_character_csv <- function(path, required, label) {
  if (!file.exists(path) || dir.exists(path)) stop_contract(sprintf("%s does not exist: %s", label, path))
  data <- tryCatch(utils::read.csv(path, stringsAsFactors = FALSE, check.names = FALSE, colClasses = "character", na.strings = character()), error = function(error) stop_contract(conditionMessage(error)))
  names(data) <- trimws(names(data))
  if (any(!nzchar(names(data))) || anyDuplicated(names(data))) stop_contract(sprintf("%s headers must be nonblank and unique.", label))
  missing <- setdiff(required, names(data))
  if (length(missing)) stop_contract(sprintf("%s is missing columns: %s", label, paste(missing, collapse = ", ")))
  if (nrow(data)) data <- data[apply(data, 1L, function(row) any(nzchar(trimws(row)))), , drop = FALSE]
  if (!nrow(data)) stop_contract(sprintf("%s contains no data rows.", label))
  data
}

finite_number <- function(text, field, row_number, allow_blank = FALSE) {
  value <- trimws(text)
  if (!nzchar(value)) {
    if (allow_blank) return(NA_real_)
    stop_contract(sprintf("Row %d: '%s' must not be blank.", row_number, field))
  }
  number <- suppressWarnings(as.numeric(value))
  if (is.na(number) || !is.finite(number)) stop_contract(sprintf("Row %d: '%s' must be finite numeric.", row_number, field))
  number
}

positive_integer <- function(text, field, row_number, allow_blank = FALSE) {
  value <- trimws(text)
  if (!nzchar(value) && allow_blank) return(NA_integer_)
  number <- suppressWarnings(as.integer(value))
  if (is.na(number) || number <= 0L || as.character(number) != value) stop_contract(sprintf("Row %d: '%s' must be a positive integer.", row_number, field))
  number
}

add_metadata <- function(data) {
  data$status <- if ("data_status" %in% names(data)) toupper(trimws(data$data_status)) else rep("", nrow(data))
  data$seed <- if ("simulation_seed" %in% names(data)) trimws(data$simulation_seed) else rep("", nrow(data))
  data
}

read_features <- function(path, options) {
  if (!nzchar(path)) return(list(data = data.frame(), class_note = ""))
  data <- add_metadata(read_character_csv(path, c("feature", "effect", "significance"), "Feature CSV"))
  data$feature <- trimws(data$feature); data$effect_num <- NA_real_; data$significance_num <- NA_real_
  supplied_class <- if ("significance_class" %in% names(data)) trimws(data$significance_class) else rep("", nrow(data))
  has_classes <- any(nzchar(supplied_class))
  if (has_classes && any(!nzchar(supplied_class))) stop_contract("significance_class must be supplied for every feature row or none.")
  if (has_classes && is.finite(options$effect_threshold)) stop_contract("Do not combine supplied significance_class with threshold-derived classes.")
  for (index in seq_len(nrow(data))) {
    row_number <- index + 1L
    if (!nzchar(data$feature[[index]])) stop_contract(sprintf("Row %d: feature must not be blank.", row_number))
    data$effect_num[[index]] <- finite_number(data$effect[[index]], "effect", row_number)
    data$significance_num[[index]] <- finite_number(data$significance[[index]], "significance", row_number)
    if (data$significance_num[[index]] <= 0 || data$significance_num[[index]] > 1) stop_contract(sprintf("Row %d: significance must lie in (0, 1].", row_number))
  }
  if (anyDuplicated(data$feature)) stop_contract("Feature identifiers must be unique.")
  if (has_classes) {
    data$category <- supplied_class
    class_note <- "Feature classes are supplied upstream and plotted verbatim"
  } else if (is.finite(options$effect_threshold)) {
    data$category <- ifelse(
      data$significance_num <= options$significance_threshold & data$effect_num >= options$effect_threshold,
      "Threshold: positive",
      ifelse(
        data$significance_num <= options$significance_threshold & data$effect_num <= -options$effect_threshold,
        "Threshold: negative", "Threshold: other"
      )
    )
    class_note <- sprintf("Feature classes use explicit display thresholds: |effect| >= %g and significance <= %g", options$effect_threshold, options$significance_threshold)
  } else {
    data$category <- "Unclassified"
    class_note <- "No feature significance classes supplied; all points are unclassified"
  }
  if (length(unique(data$category)) > 12L) stop_contract("Feature classification has more than 12 categories; consolidate upstream.")
  list(data = data, class_note = class_note)
}

read_curves <- function(path) {
  if (!nzchar(path)) return(list(data = data.frame(), curve_ids = character()))
  data <- add_metadata(read_character_csv(path, c("curve_id", "rank", "running_score"), "Ranked curve CSV"))
  data$curve_id <- trimws(data$curve_id); data$rank_num <- NA_integer_; data$score_num <- NA_real_
  for (index in seq_len(nrow(data))) {
    row_number <- index + 1L
    if (!nzchar(data$curve_id[[index]])) stop_contract(sprintf("Row %d: curve_id must not be blank.", row_number))
    data$rank_num[[index]] <- positive_integer(data$rank[[index]], "rank", row_number)
    data$score_num[[index]] <- finite_number(data$running_score[[index]], "running_score", row_number)
  }
  curve_ids <- ordered_unique(data$curve_id)
  if (length(curve_ids) > max_curves) stop_contract(sprintf("At most %d curves can share one panel; split the figure.", max_curves))
  for (curve in curve_ids) {
    subset <- data[data$curve_id == curve, , drop = FALSE]
    if (nrow(subset) < 2L) stop_contract(sprintf("Curve '%s' needs at least two coordinates.", curve))
    if (any(diff(subset$rank_num) <= 0)) stop_contract(sprintf("Curve '%s' ranks must appear in strictly increasing order.", curve))
  }
  list(data = data, curve_ids = curve_ids)
}

read_hits <- function(path, curves) {
  if (!nzchar(path)) return(data.frame())
  data <- add_metadata(read_character_csv(path, c("curve_id", "rank"), "Hit CSV"))
  data$curve_id <- trimws(data$curve_id); data$rank_num <- NA_integer_
  for (index in seq_len(nrow(data))) {
    row_number <- index + 1L; curve <- data$curve_id[[index]]
    if (!curve %in% curves$curve_ids) stop_contract(sprintf("Hit row %d: unknown curve_id.", row_number))
    data$rank_num[[index]] <- positive_integer(data$rank[[index]], "rank", row_number)
    if (!data$rank_num[[index]] %in% curves$data$rank_num[curves$data$curve_id == curve]) stop_contract(sprintf("Hit row %d: rank is not a supplied coordinate.", row_number))
  }
  if (anyDuplicated(paste(data$curve_id, data$rank_num, sep = "\r"))) stop_contract("Hit curve_id/rank pairs must be unique.")
  data
}

read_summary <- function(path, curves, hits) {
  if (!nzchar(path)) return(data.frame())
  data <- add_metadata(read_character_csv(path, c("curve_id", "enrichment_score"), "Summary CSV"))
  data$curve_id <- trimws(data$curve_id); data$score_num <- NA_real_; data$p_num <- NA_real_; data$adjusted_num <- NA_real_; data$hit_num <- NA_integer_
  for (index in seq_len(nrow(data))) {
    row_number <- index + 1L; curve <- data$curve_id[[index]]
    if (!curve %in% curves$curve_ids) stop_contract(sprintf("Summary row %d: unknown curve_id.", row_number))
    data$score_num[[index]] <- finite_number(data$enrichment_score[[index]], "enrichment_score", row_number)
    p_text <- if ("p_value" %in% names(data)) data$p_value[[index]] else ""
    adjusted_text <- if ("adjusted_p_value" %in% names(data)) data$adjusted_p_value[[index]] else ""
    hit_text <- if ("hit_count" %in% names(data)) data$hit_count[[index]] else ""
    data$p_num[[index]] <- finite_number(p_text, "p_value", row_number, TRUE)
    data$adjusted_num[[index]] <- finite_number(adjusted_text, "adjusted_p_value", row_number, TRUE)
    if (is.finite(data$p_num[[index]]) && (data$p_num[[index]] < 0 || data$p_num[[index]] > 1)) stop_contract(sprintf("Summary row %d: p_value must lie in [0, 1].", row_number))
    if (is.finite(data$adjusted_num[[index]]) && (data$adjusted_num[[index]] < 0 || data$adjusted_num[[index]] > 1)) stop_contract(sprintf("Summary row %d: adjusted_p_value must lie in [0, 1].", row_number))
    data$hit_num[[index]] <- positive_integer(hit_text, "hit_count", row_number, TRUE)
    if (is.finite(data$hit_num[[index]]) && nrow(hits)) {
      actual <- sum(hits$curve_id == curve)
      if (data$hit_num[[index]] != actual) stop_contract(sprintf("Summary row %d: hit_count does not match the hit file.", row_number))
    }
  }
  if (anyDuplicated(data$curve_id)) stop_contract("Summary curve_id rows must be unique.")
  missing <- setdiff(curves$curve_ids, data$curve_id)
  if (length(missing)) stop_contract(sprintf("Summary must contain one row per curve; missing: %s", paste(missing, collapse = ", ")))
  data
}

metadata_note <- function(data_frames) {
  statuses <- unlist(lapply(data_frames, function(data) if (nrow(data)) data$status else character()))
  seeds <- unlist(lapply(data_frames, function(data) if (nrow(data)) data$seed else character()))
  unique_statuses <- ordered_unique(statuses[nzchar(statuses)]); unique_seeds <- ordered_unique(seeds[nzchar(seeds)])
  if (length(unique_statuses) > 1L || length(unique_seeds) > 1L) stop_contract("data_status and simulation_seed must be constant across all files.")
  if (identical(unique_statuses, "SIMULATED")) {
    if (any(statuses != "SIMULATED") || any(!nzchar(seeds))) stop_contract("Every simulated row must declare the same fixed seed.")
    seed <- suppressWarnings(as.integer(unique_seeds[[1]]))
    if (is.na(seed) || seed <= 0L || as.character(seed) != unique_seeds[[1]]) stop_contract("simulation_seed must be a positive integer.")
    return(sprintf("SIMULATED DEMONSTRATION DATA · fixed seed %d", seed))
  }
  if (length(unique_seeds)) stop_contract("simulation_seed is only valid with SIMULATED data.")
  "SOURCE-SUPPLIED / PRECOMPUTED DATA"
}

summary_label <- function(row) {
  parts <- sprintf("score=%g", row$score_num)
  if (is.finite(row$p_num)) parts <- c(parts, sprintf("p=%g", row$p_num))
  if (is.finite(row$adjusted_num)) parts <- c(parts, sprintf("adjusted=%g", row$adjusted_num))
  if (is.finite(row$hit_num)) parts <- c(parts, sprintf("hits=%d", row$hit_num))
  paste0(row$curve_id, ": ", paste(parts, collapse = ", "))
}

draw_figure <- function(features, curves, hits, summary, note, options) {
  background <- "#FBFAF7"; ink <- "#20282C"; muted <- "#647078"; grid_color <- "#E5E2DC"
  palette <- c("#287D9B", "#D96B35", "#4F8A5B", "#8D65A8", "#B68A1F", "#5875B5", "#B64E68")
  panel_count <- as.integer(nrow(features$data) > 0L) + as.integer(nrow(curves$data) > 0L)
  graphics::par(mfrow = c(1, panel_count), mar = c(5.5, 4.6, 3.8, 1.0), oma = c(2.7, 0.5, 4.7, 0.5), bg = background, fg = ink, family = "sans")
  if (nrow(features$data)) {
    categories <- ordered_unique(features$data$category)
    colors <- stats::setNames(rep(palette, length.out = length(categories)), categories)
    x <- features$data$effect_num; y <- -log10(features$data$significance_num)
    graphics::plot(x, y, type = "n", xlab = "Supplied feature effect", ylab = "-log10(supplied significance)", main = "Feature-level supplied statistics", bty = "l")
    graphics::grid(col = grid_color, lwd = 0.65); graphics::abline(v = 0, col = "#657177", lwd = 0.8)
    for (category in categories) {
      keep <- features$data$category == category
      graphics::points(x[keep], y[keep], pch = 21, bg = grDevices::adjustcolor(colors[[category]], alpha.f = 0.72), col = "white", cex = 0.78, lwd = 0.35)
    }
    if (is.finite(options$effect_threshold)) {
      graphics::abline(v = c(-options$effect_threshold, options$effect_threshold), h = -log10(options$significance_threshold), lty = 2, col = "#747D80", lwd = 0.8)
    }
    graphics::legend("topright", legend = categories, pt.bg = unname(colors[categories]), pch = 21, col = "white", bty = "n", cex = 0.70)
    graphics::mtext(features$class_note, side = 3, line = 0.45, adj = 0, cex = 0.66, col = muted)
  }
  if (nrow(curves$data)) {
    curve_colors <- stats::setNames(rep(palette, length.out = length(curves$curve_ids)), curves$curve_ids)
    x_limits <- range(curves$data$rank_num); y_limits <- range(curves$data$score_num)
    padding <- max(0.08 * diff(y_limits), 0.03); y_limits <- y_limits + c(-padding, padding)
    graphics::plot.new(); graphics::plot.window(xlim = x_limits, ylim = y_limits)
    graphics::grid(col = grid_color, lwd = 0.65); graphics::abline(h = 0, col = "#657177", lwd = 0.8)
    for (curve in curves$curve_ids) {
      subset <- curves$data[curves$data$curve_id == curve, , drop = FALSE]
      graphics::lines(subset$rank_num, subset$score_num, col = curve_colors[[curve]], lwd = 1.8)
    }
    if (nrow(hits)) {
      rug_base <- y_limits[[1]] + 0.025 * diff(y_limits)
      rug_step <- 0.025 * diff(y_limits)
      for (index in seq_along(curves$curve_ids)) {
        curve <- curves$curve_ids[[index]]; ranks <- hits$rank_num[hits$curve_id == curve]
        if (length(ranks)) graphics::segments(ranks, rug_base + (index - 1) * rug_step, ranks, rug_base + (index - 0.35) * rug_step, col = curve_colors[[curve]], lwd = 0.75)
      }
    }
    graphics::axis(1, cex.axis = 0.78); graphics::axis(2, las = 1, cex.axis = 0.78); graphics::box(bty = "l")
    graphics::mtext("Supplied rank position", side = 1, line = 2.6, cex = 0.86)
    graphics::mtext("Precomputed running enrichment score", side = 2, line = 3.0, cex = 0.86)
    graphics::title("Precomputed ranked enrichment curves", adj = 0, cex.main = 1.05)
    graphics::mtext("Curves and hits are supplied/precomputed; no enrichment algorithm is run", side = 3, line = 0.45, adj = 0, cex = 0.66, col = muted)
    graphics::legend("topright", legend = curves$curve_ids, col = unname(curve_colors[curves$curve_ids]), lty = 1, lwd = 1.7, bty = "n", cex = 0.72)
    if (nrow(summary)) {
      summary_text <- paste(vapply(seq_len(nrow(summary)), function(index) summary_label(summary[index, ]), character(1)), collapse = " | ")
      graphics::mtext(paste("SUPPLIED SUMMARY:", summary_text), side = 1, line = 4.2, cex = 0.59, col = muted)
    }
  }
  graphics::mtext(options$title, side = 3, outer = TRUE, line = 3.0, adj = 0.02, cex = 1.7, font = 2)
  graphics::mtext(note, side = 3, outer = TRUE, line = 1.55, adj = 0.02, cex = 0.85, col = muted)
  graphics::mtext("All feature statistics/classes and ranked curves/hits/summaries are supplied or explicitly threshold-derived display fields; no GSEA or pathway query is performed.", side = 3, outer = TRUE, line = 0.35, adj = 0.02, cex = 0.69, col = muted)
  graphics::mtext("The plot does not validate pathway provenance, multiple testing, ranking construction, or significance. Interpretation remains upstream.", side = 1, outer = TRUE, line = 1.35, adj = 0.02, cex = 0.67, col = muted)
}

options <- parse_args(commandArgs(trailingOnly = TRUE))
features <- read_features(options$features, options)
curves <- read_curves(options$curve)
hits <- read_hits(options$hits, curves)
summary <- read_summary(options$summary, curves, hits)
note <- metadata_note(list(features$data, curves$data, hits, summary))
panel_count <- as.integer(nrow(features$data) > 0L) + as.integer(nrow(curves$data) > 0L)
width <- if (panel_count == 1L) 8.4 else 14.8; height <- 6.3
prefix <- file.path(dirname(options$output_prefix), tools::file_path_sans_ext(basename(options$output_prefix)))
dir.create(dirname(prefix), recursive = TRUE, showWarnings = FALSE)
png_path <- paste0(prefix, ".png"); pdf_path <- paste0(prefix, ".pdf")
grDevices::png(png_path, width = width, height = height, units = "in", res = options$dpi, bg = "#FBFAF7")
draw_figure(features, curves, hits, summary, note, options); grDevices::dev.off()
grDevices::pdf(pdf_path, width = width, height = height, bg = "#FBFAF7", onefile = TRUE)
draw_figure(features, curves, hits, summary, note, options); grDevices::dev.off()
panels <- character()
if (nrow(features$data)) panels <- c(panels, sprintf("feature panel=%d rows", nrow(features$data)))
if (nrow(curves$data)) panels <- c(panels, sprintf("enrichment panel=%d coordinates, %d hits, %d summaries", nrow(curves$data), nrow(hits), nrow(summary)))
message(sprintf("Validated %s", paste(panels, collapse = "; ")))
message(sprintf("Data status: %s", note))
message(sprintf("PNG: %s", normalizePath(png_path, mustWork = TRUE)))
message(sprintf("PDF: %s", normalizePath(pdf_path, mustWork = TRUE)))
