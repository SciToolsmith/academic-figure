#!/usr/bin/env Rscript

# Exact item-set intersections as an UpSet plot using base R.

all_args <- commandArgs(trailingOnly = FALSE)
file_arg <- sub("^--file=", "", all_args[grep("^--file=", all_args)])
script_dir <- if (length(file_arg)) dirname(normalizePath(file_arg[[1]], mustWork = TRUE)) else getwd()
template_dir <- dirname(script_dir)

defaults <- list(
  input = file.path(template_dir, "demo", "demo_membership_seed157.csv"),
  set_spec = file.path(template_dir, "demo", "demo_set_spec.csv"),
  output_prefix = file.path(getwd(), "upset_r"),
  title = "Exact set intersections",
  top = 12L,
  dpi = 320L
)
max_sets <- 16L
max_top <- 50L

parse_args <- function(args) {
  result <- defaults
  aliases <- c(input = "input", `set-spec` = "set_spec", `output-prefix` = "output_prefix", title = "title", top = "top", dpi = "dpi")
  index <- 1L
  while (index <= length(args)) {
    token <- args[[index]]
    if (!startsWith(token, "--")) stop(sprintf("Unknown argument: %s", token), call. = FALSE)
    stripped <- substring(token, 3L)
    if (grepl("=", stripped, fixed = TRUE)) {
      pieces <- strsplit(stripped, "=", fixed = TRUE)[[1]]
      key <- pieces[[1]]
      value <- paste(pieces[-1], collapse = "=")
    } else {
      key <- stripped
      index <- index + 1L
      if (index > length(args)) stop(sprintf("Missing value for --%s", key), call. = FALSE)
      value <- args[[index]]
    }
    if (!key %in% names(aliases)) stop(sprintf("Unknown option: --%s", key), call. = FALSE)
    result[[aliases[[key]]]] <- value
    index <- index + 1L
  }
  result$top <- suppressWarnings(as.integer(result$top))
  result$dpi <- suppressWarnings(as.integer(result$dpi))
  if (is.na(result$top) || result$top < 1L || result$top > max_top) stop(sprintf("--top must be between 1 and %d.", max_top), call. = FALSE)
  if (is.na(result$dpi) || result$dpi < 150L) stop("--dpi must be at least 150.", call. = FALSE)
  result
}

stop_contract <- function(message) stop(sprintf("Input validation failed: %s", message), call. = FALSE)
ordered_unique <- function(values) values[!duplicated(values)]

read_character_csv <- function(path, label) {
  if (!file.exists(path) || dir.exists(path)) stop_contract(sprintf("%s does not exist: %s", label, path))
  data <- tryCatch(
    utils::read.csv(path, stringsAsFactors = FALSE, check.names = FALSE, colClasses = "character", na.strings = character()),
    error = function(error) stop_contract(conditionMessage(error))
  )
  names(data) <- trimws(names(data))
  if (!ncol(data)) stop_contract(sprintf("%s has no header row.", label))
  if (any(!nzchar(names(data))) || anyDuplicated(names(data))) stop_contract(sprintf("%s headers must be nonblank and unique.", label))
  if (nrow(data)) {
    keep <- apply(data, 1L, function(row) any(nzchar(trimws(row))))
    data <- data[keep, , drop = FALSE]
  }
  data
}

read_set_spec <- function(path) {
  data <- read_character_csv(path, "Set spec")
  missing <- setdiff(c("set", "label"), names(data))
  if (length(missing)) stop_contract(sprintf("Set spec is missing columns: %s", paste(missing, collapse = ", ")))
  data$set <- trimws(data$set)
  data$label <- trimws(data$label)
  if (any(!nzchar(data$set)) || any(!nzchar(data$label))) stop_contract("Set IDs and labels must be nonblank.")
  if (anyDuplicated(data$set) || anyDuplicated(data$label)) stop_contract("Set IDs and display labels must each be unique.")
  if (nrow(data) < 2L) stop_contract("UpSet requires at least two declared sets.")
  if (nrow(data) > max_sets) stop_contract(sprintf("Set spec declares %d sets; readable limit is %d. Split into interpretable subsets.", nrow(data), max_sets))
  data
}

read_memberships <- function(path, spec) {
  data <- read_character_csv(path, "Membership CSV")
  missing <- setdiff(c("item", "set"), names(data))
  if (length(missing)) stop_contract(sprintf("Membership CSV is missing columns: %s", paste(missing, collapse = ", ")))
  if (!nrow(data)) stop_contract("Membership CSV contains no memberships.")
  data$item <- trimws(data$item)
  data$set <- trimws(data$set)
  if (any(!nzchar(data$item)) || any(!nzchar(data$set))) stop_contract("item and set must be nonblank; empty memberships are invalid.")
  unknown <- setdiff(unique(data$set), spec$set)
  if (length(unknown)) stop_contract(sprintf("Unknown set(s): %s", paste(unknown, collapse = ", ")))
  pair_keys <- paste(data$item, data$set, sep = "\r")
  if (anyDuplicated(pair_keys)) stop_contract("Duplicate item/set memberships are not allowed.")
  unused <- setdiff(spec$set, unique(data$set))
  if (length(unused)) stop_contract(sprintf("Declared sets must not be empty: %s", paste(unused, collapse = ", ")))
  status <- if ("data_status" %in% names(data)) toupper(trimws(data$data_status)) else rep("", nrow(data))
  seed <- if ("simulation_seed" %in% names(data)) trimws(data$simulation_seed) else rep("", nrow(data))
  statuses <- ordered_unique(status[nzchar(status)])
  seeds <- ordered_unique(seed[nzchar(seed)])
  if (length(statuses) > 1L || length(seeds) > 1L) stop_contract("data_status and simulation_seed must each be constant.")
  if (identical(statuses, "SIMULATED")) {
    if (any(status != "SIMULATED") || any(!nzchar(seed))) stop_contract("Every simulated row must declare SIMULATED and one fixed seed.")
    seed_number <- suppressWarnings(as.integer(seeds[[1]]))
    if (is.na(seed_number) || seed_number <= 0L || as.character(seed_number) != seeds[[1]]) stop_contract("simulation_seed must be a positive integer.")
    data_note <- sprintf("SIMULATED DEMONSTRATION DATA · fixed seed %d", seed_number)
  } else {
    if (length(seeds)) stop_contract("simulation_seed is only valid with SIMULATED data.")
    data_note <- "SOURCE-SUPPLIED DATA"
  }
  list(data = data, items = ordered_unique(data$item), data_note = data_note)
}

build_intersections <- function(validated, spec, top) {
  combo_keys <- character(length(validated$items))
  combos <- vector("list", length(validated$items))
  for (index in seq_along(validated$items)) {
    item <- validated$items[[index]]
    member_sets <- validated$data$set[validated$data$item == item]
    member_indices <- which(spec$set %in% member_sets)
    if (!length(member_indices)) stop_contract(sprintf("Item '%s' has no declared-set membership.", item))
    combos[[index]] <- member_indices
    combo_keys[[index]] <- paste(member_indices, collapse = ",")
  }
  counts_table <- table(combo_keys)
  keys <- names(counts_table)
  counts <- as.integer(counts_table)
  combo_indices <- lapply(keys, function(key) as.integer(strsplit(key, ",", fixed = TRUE)[[1]]))
  degree <- lengths(combo_indices)
  lexical_key <- vapply(combo_indices, function(indices) paste(sprintf("%02d", indices), collapse = "-"), character(1))
  order_indices <- order(-counts, -degree, lexical_key)
  keys <- keys[order_indices]
  counts <- counts[order_indices]
  combo_indices <- combo_indices[order_indices]
  displayed_count <- min(top, length(counts))
  list(
    combos = combo_indices[seq_len(displayed_count)],
    counts = counts[seq_len(displayed_count)],
    total_intersections = length(counts),
    hidden_count = length(counts) - displayed_count,
    set_sizes = vapply(spec$set, function(set_id) length(unique(validated$data$item[validated$data$set == set_id])), integer(1))
  )
}

draw_figure <- function(intersections, validated, spec, options) {
  background <- "#FBFAF7"
  ink <- "#20282C"
  muted <- "#647078"
  accent <- "#287D87"
  inactive <- "#D8D9D5"
  grid_color <- "#E5E2DC"
  shown <- length(intersections$counts)
  set_count <- nrow(spec)
  graphics::layout(
    matrix(c(1, 2, 3, 4), nrow = 2, byrow = TRUE),
    widths = c(2.0, max(4.5, 0.52 * shown)),
    heights = c(2.25, max(2.3, 0.38 * set_count))
  )
  graphics::par(oma = c(3.1, 0.5, 4.4, 0.5), bg = background, fg = ink, family = "sans")

  graphics::par(mar = c(0.8, 0.8, 2.2, 0.8))
  graphics::plot.new()
  graphics::text(0, 0.92, "Exact-membership summary", adj = c(0, 1), cex = 1.02, font = 2)
  summary_text <- sprintf(
    "%d unique items\n%d declared sets\n%d nonzero exact intersections\n%d displayed · %d not displayed",
    length(validated$items), set_count, intersections$total_intersections,
    shown, intersections$hidden_count
  )
  graphics::text(0, 0.72, summary_text, adj = c(0, 1), cex = 0.84, col = muted)

  graphics::par(mar = c(0.8, 4.0, 2.6, 1.0))
  graphics::plot.new()
  maximum <- max(intersections$counts)
  graphics::plot.window(xlim = c(0.5, shown + 0.5), ylim = c(0, maximum * 1.23), xaxs = "i", yaxs = "i")
  y_ticks <- graphics::axTicks(2)
  graphics::abline(h = y_ticks, col = grid_color, lwd = 0.65)
  for (index in seq_len(shown)) {
    graphics::rect(index - 0.36, 0, index + 0.36, intersections$counts[[index]], col = accent, border = "white", lwd = 0.6)
    graphics::text(index, intersections$counts[[index]] + maximum * 0.03, intersections$counts[[index]], cex = max(0.58, 0.78 - 0.006 * max(0, shown - 18)))
  }
  graphics::axis(2, las = 1, cex.axis = 0.78, col = "#6D7A80")
  graphics::box(bty = "l", col = "#6D7A80")
  graphics::mtext("Exact intersection size", side = 2, line = 2.7, cex = 0.86)
  graphics::mtext("Top exact intersections", side = 3, line = 1.0, adj = 0, cex = 1.08, font = 2)

  graphics::par(mar = c(3.2, 7.0 + 0.15 * max(nchar(spec$label)), 2.1, 0.8))
  graphics::plot.new()
  maximum_set <- max(intersections$set_sizes)
  graphics::plot.window(xlim = c(0, maximum_set * 1.25), ylim = c(set_count + 0.5, 0.5), xaxs = "i", yaxs = "i")
  x_ticks <- graphics::axTicks(1)
  graphics::abline(v = x_ticks, col = grid_color, lwd = 0.65)
  for (index in seq_len(set_count)) {
    graphics::rect(0, index - 0.29, intersections$set_sizes[[index]], index + 0.29, col = "#81979A", border = "white", lwd = 0.5)
    graphics::text(intersections$set_sizes[[index]] + maximum_set * 0.025, index, intersections$set_sizes[[index]], adj = c(0, 0.5), cex = 0.72)
  }
  graphics::axis(1, cex.axis = 0.76, col = "#6D7A80")
  graphics::axis(2, at = seq_len(set_count), labels = spec$label, las = 1, tick = FALSE, cex.axis = max(0.66, 0.84 - 0.012 * max(0, set_count - 10)))
  graphics::box(bty = "l", col = "#6D7A80")
  graphics::mtext("Set size", side = 1, line = 2.2, cex = 0.84)
  graphics::mtext("Set sizes", side = 3, line = 0.9, adj = 0, cex = 1.0, font = 2)

  graphics::par(mar = c(3.2, 0.8, 2.1, 1.0))
  graphics::plot.new()
  graphics::plot.window(xlim = c(0.5, shown + 0.5), ylim = c(set_count + 0.5, 0.5), xaxs = "i", yaxs = "i")
  for (row_index in seq_len(set_count)) {
    if (row_index %% 2L == 1L) graphics::rect(0.5, row_index - 0.5, shown + 0.5, row_index + 0.5, col = "#F2F0EA", border = NA)
  }
  for (column_index in seq_len(shown)) {
    graphics::points(rep(column_index, set_count), seq_len(set_count), pch = 16, cex = 0.72, col = inactive)
    active <- intersections$combos[[column_index]]
    if (length(active) > 1L) graphics::segments(column_index, min(active), column_index, max(active), col = ink, lwd = 1.5)
    graphics::points(rep(column_index, length(active)), active, pch = 21, cex = 0.92, bg = ink, col = "white", lwd = 0.45)
  }
  graphics::axis(1, at = seq_len(shown), labels = seq_len(shown), cex.axis = max(0.56, 0.74 - 0.006 * max(0, shown - 18)), col = "#6D7A80")
  graphics::box(bty = "l", col = "#6D7A80")
  graphics::mtext("Displayed intersection rank", side = 1, line = 2.2, cex = 0.84)

  graphics::mtext(options$title, side = 3, outer = TRUE, line = 2.6, adj = 0.02, cex = 1.75, font = 2)
  graphics::mtext(validated$data_note, side = 3, outer = TRUE, line = 1.2, adj = 0.02, cex = 0.86, col = muted)
  graphics::mtext("Each item contributes once to exactly one membership combination; bars are not inclusive overlaps.", side = 3, outer = TRUE, line = 0.15, adj = 0.02, cex = 0.74, col = muted)
  graphics::mtext(sprintf("Selection: size descending, degree descending, declared-set index tuple ascending. Displayed %d of %d; %d not displayed.", shown, intersections$total_intersections, intersections$hidden_count), side = 1, outer = TRUE, line = 1.4, adj = 0.02, cex = 0.70, col = muted)
}

options <- parse_args(commandArgs(trailingOnly = TRUE))
spec <- read_set_spec(options$set_spec)
validated <- read_memberships(options$input, spec)
intersections <- build_intersections(validated, spec, options$top)
shown <- length(intersections$counts)
device_width <- min(23, max(10, 4.3 + 0.58 * shown))
device_height <- max(6.3, 3.6 + 0.38 * nrow(spec))
prefix <- file.path(dirname(options$output_prefix), tools::file_path_sans_ext(basename(options$output_prefix)))
dir.create(dirname(prefix), recursive = TRUE, showWarnings = FALSE)
png_path <- paste0(prefix, ".png")
pdf_path <- paste0(prefix, ".pdf")

grDevices::png(png_path, width = device_width, height = device_height, units = "in", res = options$dpi, bg = "#FBFAF7")
draw_figure(intersections, validated, spec, options)
grDevices::dev.off()
grDevices::pdf(pdf_path, width = device_width, height = device_height, bg = "#FBFAF7", onefile = TRUE)
draw_figure(intersections, validated, spec, options)
grDevices::dev.off()

message(sprintf("Validated %d unique memberships: %d items × %d sets; %d nonzero exact intersections; %d displayed; %d not displayed", nrow(validated$data), length(validated$items), nrow(spec), intersections$total_intersections, shown, intersections$hidden_count))
message(sprintf("Data status: %s", validated$data_note))
message(sprintf("PNG: %s", normalizePath(png_path, mustWork = TRUE)))
message(sprintf("PDF: %s", normalizePath(pdf_path, mustWork = TRUE)))
