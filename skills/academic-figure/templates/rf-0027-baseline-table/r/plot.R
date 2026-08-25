#!/usr/bin/env Rscript

MAX_GROUP_COLUMNS <- 6L
MAX_DISPLAY_ROWS <- 40L

fail <- function(text) stop(text, call. = FALSE)
ordered_unique <- function(values) values[!duplicated(values)]

parse_args <- function(args) {
  config <- list(
    input = NULL,
    schema = NULL,
    output_prefix = NULL,
    title = "Baseline characteristics",
    include_overall = "false"
  )
  index <- 1L
  while (index <= length(args)) {
    token <- args[[index]]
    if (!startsWith(token, "--")) fail(paste0("unexpected argument: ", token))
    body <- substring(token, 3L)
    if (grepl("=", body, fixed = TRUE)) {
      pieces <- strsplit(body, "=", fixed = TRUE)[[1L]]
      key <- pieces[[1L]]
      value <- paste(pieces[-1L], collapse = "=")
    } else {
      key <- body
      if (index == length(args)) fail(paste0("missing value for --", key))
      index <- index + 1L
      value <- args[[index]]
    }
    key <- gsub("-", "_", key, fixed = TRUE)
    if (!key %in% names(config)) fail(paste0("unknown option: --", body))
    config[[key]] <- value
    index <- index + 1L
  }
  for (required in c("input", "schema", "output_prefix")) {
    if (is.null(config[[required]]) || !nzchar(config[[required]])) fail(paste0("--", gsub("_", "-", required), " is required"))
  }
  if (grepl("\\.(png|svg)$", config$output_prefix, ignore.case = TRUE)) {
    fail("--output-prefix must not include .png or .svg")
  }
  if (!tolower(config$include_overall) %in% c("true", "false")) fail("--include-overall must be true or false")
  config$include_overall <- tolower(config$include_overall) == "true"
  config
}

read_schema <- function(path) {
  if (!file.exists(path)) fail(paste0("schema file does not exist: ", path))
  schema <- read.csv(
    path,
    header = TRUE,
    check.names = FALSE,
    stringsAsFactors = FALSE,
    colClasses = "character",
    na.strings = character(),
    fileEncoding = "UTF-8-BOM"
  )
  required <- c("variable", "label", "type", "levels", "summary", "decimals")
  if (!all(required %in% names(schema))) fail(paste0("schema must contain: ", paste(required, collapse = ", ")))
  if (anyDuplicated(names(schema))) fail("schema contains duplicate column names")
  if (!nrow(schema)) fail("schema contains no variables")
  for (field in required) schema[[field]] <- trimws(schema[[field]])
  if (any(!nzchar(schema$variable)) || any(!nzchar(schema$label))) fail("schema variable and label are required")
  if (any(schema$variable %in% c("id", "group"))) fail("schema uses reserved variable id or group")
  if (anyDuplicated(schema$variable)) fail("schema variable names must be unique")
  if (any(!schema$type %in% c("continuous", "categorical"))) fail("schema type must be continuous or categorical")
  decimals <- suppressWarnings(as.integer(schema$decimals))
  if (any(is.na(decimals)) || any(as.character(decimals) != schema$decimals) || any(decimals < 0L | decimals > 6L)) {
    fail("schema decimals must be integers between 0 and 6")
  }
  schema$decimals <- decimals
  schema$level_list <- lapply(schema$levels, function(text) {
    if (!nzchar(text)) return(character())
    values <- trimws(strsplit(text, "|", fixed = TRUE)[[1L]])
    values[nzchar(values)]
  })
  for (index in seq_len(nrow(schema))) {
    if (schema$type[[index]] == "continuous") {
      if (length(schema$level_list[[index]])) fail("continuous schema levels must be empty")
      if (!schema$summary[[index]] %in% c("mean_sd", "median_iqr")) fail("continuous summary must be mean_sd or median_iqr")
    } else {
      levels <- schema$level_list[[index]]
      if (!length(levels) || anyDuplicated(levels)) fail("categorical levels must be unique and pipe-delimited")
      if (schema$summary[[index]] != "n_percent_nonmissing") fail("categorical summary must be n_percent_nonmissing")
    }
  }
  schema
}

read_data <- function(path, schema) {
  if (!file.exists(path)) fail(paste0("input file does not exist: ", path))
  data <- read.csv(
    path,
    header = TRUE,
    check.names = FALSE,
    stringsAsFactors = FALSE,
    colClasses = "character",
    na.strings = character(),
    fileEncoding = "UTF-8-BOM"
  )
  if (anyDuplicated(names(data))) fail("input contains duplicate column names")
  required <- c("id", "group", schema$variable)
  missing <- setdiff(required, names(data))
  if (length(missing)) fail(paste0("input is missing schema field(s): ", paste(missing, collapse = ", ")))
  if (!nrow(data)) fail("input contains no subjects")
  data$id <- trimws(data$id)
  data$group <- trimws(data$group)
  if (any(!nzchar(data$id)) || any(!nzchar(data$group))) fail("id and group must be non-empty")
  if (anyDuplicated(data$id)) fail("id must be unique: one input row per subject")
  for (index in seq_len(nrow(schema))) {
    variable <- schema$variable[[index]]
    text <- trimws(data[[variable]])
    missing_value <- !nzchar(text)
    if (schema$type[[index]] == "continuous") {
      value <- suppressWarnings(as.numeric(text))
      bad <- !missing_value & (is.na(value) | !is.finite(value))
      if (any(bad)) fail(paste0(variable, " must contain finite numeric values or blanks"))
      value[missing_value] <- NA_real_
      data[[variable]] <- value
    } else {
      bad <- !missing_value & !text %in% schema$level_list[[index]]
      if (any(bad)) fail(paste0(variable, " contains a category not declared in schema levels"))
      text[missing_value] <- NA_character_
      data[[variable]] <- text
    }
  }
  data
}

make_columns <- function(data, include_overall) {
  group_order <- ordered_unique(data$group)
  columns <- lapply(group_order, function(group_name) data[data$group == group_name, , drop = FALSE])
  names(columns) <- group_order
  if (include_overall) {
    if ("Overall" %in% group_order) fail("group label 'Overall' conflicts with --include-overall true")
    columns[["Overall"]] <- data
  }
  if (length(columns) > MAX_GROUP_COLUMNS) {
    fail(paste0(
      "table would have ", length(columns), " group columns; maximum is ", MAX_GROUP_COLUMNS,
      ". Split the table using a scientifically defined grouping."
    ))
  }
  columns
}

format_number <- function(value, decimals) sprintf(paste0("%.", decimals, "f"), value)

build_rows <- function(schema, columns) {
  rows <- list()
  for (index in seq_len(nrow(schema))) {
    variable <- schema$variable[[index]]
    kind <- schema$type[[index]]
    availability <- vapply(columns, function(frame) {
      available <- sum(!is.na(frame[[variable]]))
      sprintf("available %d/%d; missing %d", available, nrow(frame), nrow(frame) - available)
    }, character(1L))
    rows[[length(rows) + 1L]] <- list(kind = "section", label = schema$label[[index]], cells = availability)
    if (kind == "continuous") {
      label <- if (schema$summary[[index]] == "mean_sd") "Mean (SD)" else "Median [Q1, Q3]"
      cells <- vapply(columns, function(frame) {
        values <- frame[[variable]][!is.na(frame[[variable]])]
        if (!length(values)) return("NA")
        if (schema$summary[[index]] == "mean_sd") {
          sd_text <- if (length(values) > 1L) format_number(sd(values), schema$decimals[[index]]) else "NA"
          paste0(format_number(mean(values), schema$decimals[[index]]), " (", sd_text, ")")
        } else {
          quartiles <- quantile(values, c(0.25, 0.5, 0.75), type = 7, names = FALSE)
          paste0(
            format_number(quartiles[[2L]], schema$decimals[[index]]), " [",
            format_number(quartiles[[1L]], schema$decimals[[index]]), ", ",
            format_number(quartiles[[3L]], schema$decimals[[index]]), "]"
          )
        }
      }, character(1L))
      rows[[length(rows) + 1L]] <- list(kind = "data", label = label, cells = cells)
    } else {
      for (level in schema$level_list[[index]]) {
        cells <- vapply(columns, function(frame) {
          values <- frame[[variable]][!is.na(frame[[variable]])]
          count <- sum(values == level)
          if (length(values)) sprintf("%d/%d (%.1f%%)", count, length(values), 100 * count / length(values)) else "0/0 (NA)"
        }, character(1L))
        rows[[length(rows) + 1L]] <- list(kind = "data", label = level, cells = cells)
      }
    }
  }
  if (length(rows) > MAX_DISPLAY_ROWS) {
    fail(paste0(
      "schema expands to ", length(rows), " display rows; maximum is ", MAX_DISPLAY_ROWS,
      ". Split variables into themed tables rather than shrinking text."
    ))
  }
  rows
}

geometry <- function(rows, columns) {
  maximum_label <- max(nchar(vapply(rows, function(row) row$label, character(1L)), type = "width"))
  list(
    width = min(20, max(8.5, 4.6 + 2.1 * length(columns) + 0.045 * maximum_label)),
    height = max(5, 2.4 + 0.42 * (length(rows) + 1L)),
    maximum_label = maximum_label
  )
}

draw_table <- function(data, title_text, columns, rows, size_info) {
  par(mar = c(0, 0, 0, 0), family = "sans", bg = "white")
  plot.new()
  plot.window(xlim = c(0, 1), ylim = c(0, 1), xaxs = "i", yaxs = "i")
  colors <- c(ink = "#17212B", muted = "#617080", header = "#17354D", section = "#EAF3F2", stripe = "#F7F9FA", line = "#D8E0E5", white = "#FFFFFF")
  left <- 0.035
  right <- 0.975
  top <- 0.865
  bottom <- 0.105
  label_fraction <- min(0.44, max(0.30, 0.28 + 0.004 * size_info$maximum_label))
  label_right <- left + (right - left) * label_fraction
  data_width <- (right - label_right) / length(columns)
  edges <- c(left, label_right, label_right + data_width * seq_len(length(columns)))
  weights <- c(1.28, vapply(rows, function(row) if (row$kind == "section") 1.05 else 1, numeric(1L)))
  unit_height <- (top - bottom) / sum(weights)

  text(left, 0.962, title_text, adj = c(0, 1), cex = 1.55, font = 2, col = colors["ink"])
  text(
    left, 0.920,
    sprintf("%d subject rows · %d displayed group columns · descriptive summaries only", nrow(data), length(columns)),
    adj = c(0, 1), cex = 0.82, col = colors["muted"]
  )
  y <- top
  header_height <- weights[[1L]] * unit_height
  rect(left, y - header_height, right, y, col = colors["header"], border = NA)
  text(left + 0.012, y - header_height / 2, "Variable / summary", adj = c(0, 0.5), cex = 0.86, font = 2, col = "white")
  for (index in seq_along(columns)) {
    center <- mean(edges[c(index + 1L, index + 2L)])
    text(center, y - header_height / 2, paste0(names(columns)[[index]], "\nN=", nrow(columns[[index]])), cex = 0.80, font = 2, col = "white")
  }
  y <- y - header_height
  data_index <- 0L
  for (index in seq_along(rows)) {
    row <- rows[[index]]
    row_height <- weights[[index + 1L]] * unit_height
    fill <- if (row$kind == "section") colors["section"] else if (data_index %% 2L) colors["stripe"] else colors["white"]
    rect(left, y - row_height, right, y, col = fill, border = NA)
    segments(left, y - row_height, right, y - row_height, col = colors["line"], lwd = 0.65)
    text(
      left + if (row$kind == "section") 0.012 else 0.022,
      y - row_height / 2,
      row$label,
      adj = c(0, 0.5),
      cex = 0.79,
      font = if (row$kind == "section") 2 else 1,
      col = colors["ink"]
    )
    for (column_index in seq_along(row$cells)) {
      center <- mean(edges[c(column_index + 1L, column_index + 2L)])
      text(
        center, y - row_height / 2, row$cells[[column_index]],
        cex = if (row$kind == "section") 0.64 else 0.75,
        col = if (row$kind == "section") colors["muted"] else colors["ink"]
      )
    }
    if (row$kind == "data") data_index <- data_index + 1L
    y <- y - row_height
  }
  rect(left, bottom, right, top, border = colors["header"], lwd = 1)
  text(
    left, 0.060,
    "Categorical percentages use each variable's non-missing denominator. Continuous summaries exclude missing values. SD is sample SD; quartiles use type 7. No P values or SMD are computed.",
    adj = c(0, 1), cex = 0.67, col = colors["muted"]
  )
}

render_output <- function(kind, path, data, title_text, columns, rows, size_info) {
  if (kind == "png") {
    png(path, width = size_info$width, height = size_info$height, units = "in", res = 320, type = if (capabilities("cairo")) "cairo" else getOption("bitmapType"), bg = "white")
  } else {
    svg(path, width = size_info$width, height = size_info$height, onefile = TRUE, bg = "white", family = "sans")
  }
  device_id <- dev.cur()
  on.exit(if (dev.cur() == device_id) dev.off(), add = FALSE)
  draw_table(data, title_text, columns, rows, size_info)
  dev.off()
  on.exit(NULL, add = FALSE)
}

report_data <- function(data, schema, columns) {
  missing_cells <- sum(vapply(schema$variable, function(variable) sum(is.na(data[[variable]])), integer(1L)))
  cat(sprintf(
    "Loaded %d unique subject rows: %d displayed group column(s), %d typed variable(s), %d missing value cell(s); 0 subject rows excluded.\n",
    nrow(data), length(columns), nrow(schema), missing_cells
  ))
  for (index in seq_len(nrow(schema))) {
    variable <- schema$variable[[index]]
    cat(sprintf("variable=%s | type=%s | summary=%s\n", variable, schema$type[[index]], schema$summary[[index]]))
    for (group_name in names(columns)) {
      frame <- columns[[group_name]]
      available <- sum(!is.na(frame[[variable]]))
      cat(sprintf("  group=%s | N=%d | available=%d | missing=%d\n", group_name, nrow(frame), available, nrow(frame) - available))
    }
  }
}

main <- function() {
  config <- parse_args(commandArgs(trailingOnly = TRUE))
  schema <- read_schema(config$schema)
  data <- read_data(config$input, schema)
  columns <- make_columns(data, config$include_overall)
  rows <- build_rows(schema, columns)
  size_info <- geometry(rows, columns)
  output_directory <- dirname(config$output_prefix)
  if (!dir.exists(output_directory)) dir.create(output_directory, recursive = TRUE, showWarnings = FALSE)
  png_path <- paste0(config$output_prefix, ".png")
  svg_path <- paste0(config$output_prefix, ".svg")
  render_output("png", png_path, data, config$title, columns, rows, size_info)
  render_output("svg", svg_path, data, config$title, columns, rows, size_info)
  report_data(data, schema, columns)
  cat("Wrote ", png_path, "\n", sep = "")
  cat("Wrote ", svg_path, "\n", sep = "")
}

status <- tryCatch({main(); 0L}, error = function(error) {message("ERROR: ", conditionMessage(error)); 2L})
quit(save = "no", status = status)
