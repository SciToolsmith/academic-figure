#!/usr/bin/env Rscript

MAX_VARIABLES <- 8L
MAX_GROUPS <- 12L

abort <- function(message) stop(message, call. = FALSE)

script_args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", script_args, value = TRUE)
if (length(file_arg) != 1L) abort("Cannot determine plot.R location")
script_dir <- dirname(normalizePath(sub("^--file=", "", file_arg), mustWork = TRUE))
demo_data <- file.path(dirname(script_dir), "data", "simulated_fixed_seed_relationships.csv")

parse_cli <- function(args) {
  options <- list(input = demo_data, variables = NULL, group_column = NULL,
                  correlation_method = NULL, missing_policy = NULL,
                  output_prefix = NULL, title = "Relationship matrix", dpi = "320")
  aliases <- c(input = "input", variables = "variables", `group-column` = "group_column",
               `correlation-method` = "correlation_method", `missing-policy` = "missing_policy",
               `output-prefix` = "output_prefix", title = "title", dpi = "dpi")
  index <- 1L
  while (index <= length(args)) {
    token <- args[[index]]
    if (token %in% c("--help", "-h")) {
      cat("Usage: Rscript r/plot.R --variables=a,b --correlation-method=pearson --missing-policy=pairwise --output-prefix=PATH [options]\n")
      quit(status = 0L)
    }
    if (!startsWith(token, "--")) abort(paste0("Unexpected argument: ", token))
    body <- substring(token, 3L)
    equals <- regexpr("=", body, fixed = TRUE)[1L]
    if (equals > 0L) {
      key <- substring(body, 1L, equals - 1L)
      value <- substring(body, equals + 1L)
    } else {
      key <- body
      index <- index + 1L
      if (index > length(args) || startsWith(args[[index]], "--")) abort(paste0("Missing value for --", key))
      value <- args[[index]]
    }
    if (!key %in% names(aliases)) abort(paste0("Unknown option --", key))
    if (!nzchar(value)) abort(paste0("Empty value for --", key))
    options[[aliases[[key]]]] <- value
    index <- index + 1L
  }
  required <- c("variables", "correlation_method", "missing_policy", "output_prefix")
  absent <- required[vapply(options[required], is.null, logical(1))]
  if (length(absent)) abort(paste0("Missing required options: --", paste(gsub("_", "-", absent), collapse = ", --")))
  if (!options$correlation_method %in% c("pearson", "spearman")) abort("--correlation-method must be pearson or spearman")
  if (!options$missing_policy %in% c("pairwise", "complete")) abort("--missing-policy must be pairwise or complete")
  if (grepl("\\.(png|svg|pdf)$", options$output_prefix, ignore.case = TRUE)) abort("--output-prefix must not include an extension")
  if (!grepl("^[0-9]+$", options$dpi)) abort("--dpi must be an integer from 300 to 1200")
  options$dpi <- as.integer(options$dpi)
  if (is.na(options$dpi) || options$dpi < 300L || options$dpi > 1200L) abort("--dpi must be an integer from 300 to 1200")
  options
}

read_input <- function(path) {
  if (!file.exists(path) || dir.exists(path)) abort(paste0("Input file not found: ", path))
  table <- tryCatch(
    read.csv(path, stringsAsFactors = FALSE, check.names = FALSE, colClasses = "character",
             na.strings = character(), strip.white = FALSE),
    error = function(error) abort(paste0("Cannot read input as CSV: ", conditionMessage(error)))
  )
  if (!nrow(table)) abort("Input must contain at least one data row")
  if (any(!nzchar(trimws(names(table))))) abort("Input contains an empty column name")
  if (anyDuplicated(names(table))) abort("Input contains duplicate column names")
  for (column in names(table)) table[[column]] <- trimws(table[[column]])
  table
}

check_provenance <- function(table) {
  has_status <- "data_status" %in% names(table)
  has_seed <- "simulation_seed" %in% names(table)
  if (xor(has_status, has_seed)) abort("data_status and simulation_seed must be supplied together")
  if (!has_status) return(invisible(NULL))
  if (any(!nzchar(table$data_status)) || any(!nzchar(table$simulation_seed))) abort("Simulation provenance values cannot be empty")
  if (length(unique(paste(table$data_status, table$simulation_seed, sep = "\r"))) != 1L) abort("Simulation provenance is inconsistent")
}

parse_variables <- function(raw) {
  variables <- trimws(strsplit(raw, ",", fixed = TRUE)[[1L]])
  if (any(!nzchar(variables))) abort("--variables contains an empty name")
  if (anyDuplicated(variables)) abort("--variables contains duplicate names")
  if (length(variables) < 2L) abort("Choose at least 2 continuous variables")
  if (length(variables) > MAX_VARIABLES) {
    abort(paste0("Relationship matrices are limited to ", MAX_VARIABLES, " variables; received ", length(variables),
                 ". Preselect variables from the scientific question."))
  }
  variables
}

parse_numeric_column <- function(values, name) {
  missing <- is.na(values) | values %in% c("", "NA")
  parsed <- suppressWarnings(as.numeric(values))
  bad <- !missing & (is.na(parsed) | !is.finite(parsed))
  if (any(bad)) abort(paste0("Column ", name, " contains non-finite/non-numeric values at CSV lines: ", paste(which(bad) + 1L, collapse = ", ")))
  parsed[missing] <- NA_real_
  parsed
}

prepare_data <- function(table, variables, group_column, policy) {
  required <- c("sample_id", variables, if (!is.null(group_column)) group_column else character())
  missing <- setdiff(required, names(table))
  if (length(missing)) abort(paste0("Input is missing required columns: ", paste(missing, collapse = ", ")))
  if ("sample_id" %in% variables || (!is.null(group_column) && group_column %in% variables)) abort("ID/group columns cannot also be continuous variables")
  if (any(!nzchar(table$sample_id))) abort("sample_id cannot be empty")
  if (anyDuplicated(table$sample_id)) abort("sample_id values must be unique")
  groups <- NULL
  if (!is.null(group_column)) {
    groups <- table[[group_column]]
    if (any(!nzchar(groups))) abort("The selected group column cannot contain missing/empty values")
    if (length(unique(groups)) > MAX_GROUPS) abort(paste0("The group column exceeds ", MAX_GROUPS, " levels"))
  }
  matrix <- vapply(variables, function(variable) parse_numeric_column(table[[variable]], variable), numeric(nrow(table)))
  if (!is.matrix(matrix)) matrix <- matrix(matrix, ncol = length(variables))
  colnames(matrix) <- variables
  missing_cells <- sum(!is.finite(matrix))
  if (policy == "complete") {
    keep <- complete.cases(matrix)
    matrix <- matrix[keep, , drop = FALSE]
    if (!is.null(groups)) groups <- groups[keep]
    if (nrow(matrix) < 3L) abort("complete policy leaves fewer than 3 rows")
  }
  for (index in seq_along(variables)) {
    values <- matrix[, index]
    values <- values[is.finite(values)]
    if (length(values) < 3L) abort(paste0("Variable ", variables[index], " has fewer than 3 usable observations"))
    if (diff(range(values)) == 0) abort(paste0("Variable ", variables[index], " has no variation"))
  }
  pair_counts <- integer()
  for (row in seq_along(variables)) {
    if (row == 1L) next
    for (column in seq_len(row - 1L)) {
      ok <- is.finite(matrix[, row]) & is.finite(matrix[, column])
      count <- sum(ok)
      if (count < 3L) abort(paste0("Variable pair ", variables[column], " / ", variables[row], " has fewer than 3 usable observations"))
      if (diff(range(matrix[ok, row])) == 0 || diff(range(matrix[ok, column])) == 0) abort("A variable pair has zero variance")
      pair_counts <- c(pair_counts, count)
    }
  }
  if (!is.null(groups)) {
    for (level in unique(groups)) {
      selected <- groups == level
      if (sum(selected) < 2L) abort(paste0("Group '", level, "' has fewer than 2 usable rows"))
      for (index in seq_along(variables)) {
        if (sum(selected & is.finite(matrix[, index])) < 2L) abort(paste0("Group '", level, "' has fewer than 2 usable values for ", variables[index]))
      }
    }
  }
  list(matrix = matrix, groups = groups, missing_cells = missing_cells, pair_counts = pair_counts)
}

draw_matrix <- function(values, groups, method, policy, title) {
  variables <- colnames(values)
  levels <- if (is.null(groups)) "All samples" else unique(groups)
  colors <- setNames(grDevices::hcl.colors(length(levels), "Dark 3"), levels)
  point_colors <- if (is.null(groups)) rep(colors[[1L]], nrow(values)) else unname(colors[groups])
  correlation_palette <- grDevices::colorRampPalette(c("#2166AC", "#F7F7F7", "#B2182B"))(201)
  diagonal_index <- 0L
  lower_panel <- function(x, y, ...) {
    ok <- is.finite(x) & is.finite(y)
    points(x[ok], y[ok], pch = 21, bg = grDevices::adjustcolor(point_colors[ok], alpha.f = 0.76),
           col = "white", cex = 0.65, lwd = 0.35)
  }
  upper_panel <- function(x, y, ...) {
    ok <- is.finite(x) & is.finite(y)
    value <- cor(x[ok], y[ok], method = method)
    old <- par("usr")
    on.exit(par(usr = old), add = TRUE)
    par(usr = c(0, 1, 0, 1))
    color_index <- max(1L, min(201L, round((value + 1) * 100) + 1L))
    rect(0, 0, 1, 1, col = correlation_palette[color_index], border = NA)
    symbol <- if (method == "pearson") "r" else "rho"
    text(0.5, 0.58, sprintf("%s = %.2f", symbol, value), font = 2, cex = 1.0)
    text(0.5, 0.35, paste0("n = ", sum(ok)), cex = 0.78, col = "#374151")
  }
  diagonal_panel <- function(x, ...) {
    diagonal_index <<- diagonal_index + 1L
    old <- par("usr")
    on.exit(par(usr = old), add = TRUE)
    valid <- x[is.finite(x)]
    histogram <- hist(valid, plot = FALSE, breaks = "FD")
    heights <- histogram$counts / max(histogram$counts)
    par(usr = c(old[1:2], 0, 1.18))
    rect(histogram$breaks[-length(histogram$breaks)], 0, histogram$breaks[-1L], heights,
         col = "#D1D5DB", border = "white")
    if (!is.null(groups)) {
      for (level in levels) {
        selected <- groups == level & is.finite(x)
        if (sum(selected) >= 2L && diff(range(x[selected])) > 0) {
          curve <- density(x[selected], na.rm = TRUE)
          lines(curve$x, curve$y / max(curve$y), col = colors[[level]], lwd = 1.2)
        }
      }
      if (diagonal_index == 1L) {
        legend("top", legend = levels, col = colors, lty = 1, lwd = 1.4,
               horiz = TRUE, bty = "n", cex = 0.48, xpd = NA)
      }
    }
  }
  par(mar = c(1.5, 1.5, 1.5, 0.7), oma = c(6.5, 4.0, 10.0, 2.0))
  pairs(values, lower.panel = lower_panel, upper.panel = upper_panel, diag.panel = diagonal_panel,
        gap = 0.4, cex.labels = 0.9,
        oma = c(6.5, 4.0, 10.0, 2.0), mar = c(1.5, 1.5, 1.5, 0.7))
  mtext(title, side = 3, outer = TRUE, line = 7.3, cex = 1.28, font = 2)
  mtext(paste0("Descriptive ", tools::toTitleCase(method), " correlations; missing policy: ", policy),
        side = 3, outer = TRUE, line = 5.1, cex = 0.82, col = "#374151")
  mtext("Exploratory description only; no P values, multiplicity tests, or causal claims.",
        side = 1, outer = TRUE, line = 4.0, cex = 0.72, col = "#4B5563")
}

main <- function() {
  options <- parse_cli(commandArgs(trailingOnly = TRUE))
  variables <- parse_variables(options$variables)
  table <- read_input(options$input)
  check_provenance(table)
  prepared <- prepare_data(table, variables, options$group_column, options$missing_policy)
  width <- max(7, 1.9 * length(variables) + 0.035 * max(nchar(variables, type = "width")))
  height <- max(7, 1.9 * length(variables) + if (is.null(prepared$groups)) 0.35 else 0.8)
  parent <- dirname(options$output_prefix)
  if (!dir.exists(parent) && !dir.create(parent, recursive = TRUE, showWarnings = FALSE)) abort(paste0("Cannot create output directory: ", parent))
  png_path <- paste0(options$output_prefix, ".png")
  pdf_path <- paste0(options$output_prefix, ".pdf")
  png(png_path, width = width, height = height, units = "in", res = options$dpi, bg = "white")
  tryCatch(draw_matrix(prepared$matrix, prepared$groups, options$correlation_method, options$missing_policy, options$title), finally = dev.off())
  cairo_pdf(pdf_path, width = width, height = height, bg = "white", onefile = TRUE)
  tryCatch(draw_matrix(prepared$matrix, prepared$groups, options$correlation_method, options$missing_policy, options$title), finally = dev.off())
  row_report <- if (options$missing_policy == "complete") paste0(nrow(prepared$matrix), " complete rows retained") else paste0(nrow(prepared$matrix), " input rows retained with pair-specific availability")
  cat(sprintf("Validated %d input rows and %d variables; missing cells: %d; excluded invalid rows: 0.\n", nrow(table), length(variables), prepared$missing_cells))
  cat(sprintf("Method: %s (descriptive only); missing policy: %s; %s.\n", options$correlation_method, options$missing_policy, row_report))
  cat(sprintf("Pairwise n range: %d-%d; group levels: %d.\n", min(prepared$pair_counts), max(prepared$pair_counts), if (is.null(prepared$groups)) 0L else length(unique(prepared$groups))))
  cat("No P values, multiplicity adjustments, or causal conclusions were computed.\n")
  cat("Wrote ", png_path, "\n", sep = "")
  cat("Wrote ", pdf_path, "\n", sep = "")
}

tryCatch(main(), error = function(error) {
  message("ERROR: ", conditionMessage(error))
  quit(status = 2L)
})
