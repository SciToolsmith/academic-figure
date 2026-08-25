#!/usr/bin/env Rscript

INCREASE_COLOR <- "#147D78"
DECREASE_COLOR <- "#C46B2D"
STABLE_COLOR <- "#6B7280"

fail <- function(text) stop(text, call. = FALSE)
ordered_unique <- function(values) values[!duplicated(values)]

usage <- function() {
  paste(
    "Usage: Rscript r/plot.R --input FILE --output-prefix PREFIX",
    "[--condition-order A,B] [--incomplete-policy error|drop]",
    "[--change-tolerance NUMBER] [--title TEXT] [--y-label TEXT]",
    sep = "\n"
  )
}

parse_args <- function(args) {
  config <- list(
    input = NULL,
    output_prefix = NULL,
    title = "Paired change across conditions",
    y_label = "Value",
    condition_order = NULL,
    incomplete_policy = "error",
    change_tolerance = "0"
  )
  index <- 1L
  while (index <= length(args)) {
    token <- args[[index]]
    if (token %in% c("--help", "-h")) {
      cat(usage(), "\n")
      quit(save = "no", status = 0L)
    }
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
  if (is.null(config$input) || !nzchar(config$input)) fail(paste0("--input is required\n", usage()))
  if (is.null(config$output_prefix) || !nzchar(config$output_prefix)) fail("--output-prefix is required")
  if (grepl("\\.(png|svg)$", config$output_prefix, ignore.case = TRUE)) {
    fail("--output-prefix must not include .png or .svg")
  }
  if (!config$incomplete_policy %in% c("error", "drop")) {
    fail("--incomplete-policy must be error or drop")
  }
  tolerance <- suppressWarnings(as.numeric(config$change_tolerance))
  if (length(tolerance) != 1L || !is.finite(tolerance) || tolerance < 0) {
    fail("--change-tolerance must be a finite non-negative number")
  }
  config$change_tolerance <- tolerance
  config
}

parse_condition_order <- function(text) {
  if (is.null(text)) return(NULL)
  values <- trimws(strsplit(text, ",", fixed = TRUE)[[1L]])
  if (any(!nzchar(values))) fail("--condition-order contains an empty label")
  if (anyDuplicated(values)) fail("--condition-order contains duplicate labels")
  values
}

read_input <- function(path, requested_order, incomplete_policy) {
  if (!file.exists(path)) fail(paste0("input file does not exist: ", path))
  data <- tryCatch(
    read.csv(
      path,
      header = TRUE,
      check.names = FALSE,
      stringsAsFactors = FALSE,
      colClasses = "character",
      na.strings = character(),
      fileEncoding = "UTF-8-BOM"
    ),
    error = function(error) fail(paste0("could not read CSV: ", conditionMessage(error)))
  )
  if (anyDuplicated(names(data))) fail("input contains duplicate column names")
  missing_columns <- setdiff(c("id", "condition", "value"), names(data))
  if (length(missing_columns)) {
    fail(paste0("missing required column(s): ", paste(missing_columns, collapse = ", ")))
  }
  if (!nrow(data)) fail("input contains no observations")

  has_group <- "group" %in% names(data)
  data$id <- trimws(data$id)
  data$condition <- trimws(data$condition)
  data$group <- if (has_group) trimws(data$group) else rep("All subjects", nrow(data))
  value_text <- trimws(data$value)
  invalid_identity <- which(!nzchar(data$id) | !nzchar(data$condition) | !nzchar(data$group))
  if (length(invalid_identity)) {
    fail(paste0("id, condition and group must be non-empty; first invalid row: ", invalid_identity[[1L]] + 1L))
  }
  numeric_value <- suppressWarnings(as.numeric(value_text))
  bad_value <- which(nzchar(value_text) & (is.na(numeric_value) | !is.finite(numeric_value)))
  if (length(bad_value)) {
    fail(paste0("value must be finite numeric when supplied; first invalid row: ", bad_value[[1L]] + 1L))
  }
  numeric_value[!nzchar(value_text)] <- NA_real_
  data$value <- numeric_value
  data$source_row <- seq_len(nrow(data)) + 1L

  key <- paste(data$group, data$id, data$condition, sep = "\034")
  duplicate_rows <- which(duplicated(key) | duplicated(key, fromLast = TRUE))
  if (length(duplicate_rows)) {
    fail(paste0("each (group, id, condition) must occur exactly once; first duplicate row: ", duplicate_rows[[1L]] + 1L))
  }
  groups_per_id <- tapply(data$group, data$id, function(values) length(unique(values)))
  if (any(groups_per_id > 1L)) {
    bad_ids <- names(groups_per_id)[groups_per_id > 1L]
    fail(paste0("each id must belong to one group; namespace reused IDs if needed: ", paste(head(bad_ids, 10L), collapse = ", ")))
  }

  observed_conditions <- ordered_unique(data$condition)
  if (length(observed_conditions) < 2L) fail("paired plotting requires at least two conditions")
  condition_order <- if (is.null(requested_order)) observed_conditions else requested_order
  if (length(condition_order) != length(observed_conditions) || !setequal(condition_order, observed_conditions)) {
    fail(paste0(
      "--condition-order must contain every observed condition exactly once; observed: ",
      paste(observed_conditions, collapse = ", ")
    ))
  }

  subject_table <- unique(data[c("group", "id")])
  complete_key <- character()
  incomplete_details <- character()
  for (index in seq_len(nrow(subject_table))) {
    group_name <- subject_table$group[[index]]
    subject_id <- subject_table$id[[index]]
    rows <- data$group == group_name & data$id == subject_id
    selected <- data[rows, , drop = FALSE]
    absent <- setdiff(condition_order, selected$condition)
    missing_value <- selected$condition[is.na(selected$value)]
    pair_key <- paste(group_name, subject_id, sep = "\034")
    if (length(absent) || length(missing_value)) {
      pieces <- c(
        if (length(absent)) paste0("absent=", paste(absent, collapse = ",")),
        if (length(missing_value)) paste0("missing value=", paste(missing_value, collapse = ","))
      )
      incomplete_details <- c(incomplete_details, paste0(group_name, " / ", subject_id, ": ", paste(pieces, collapse = "; ")))
    } else {
      complete_key <- c(complete_key, pair_key)
    }
  }
  if (length(incomplete_details) && identical(incomplete_policy, "error")) {
    fail(paste0(
      "found ", length(incomplete_details), " incomplete subject(s); default policy is error:\n  - ",
      paste(head(incomplete_details, 10L), collapse = "\n  - "),
      "\nUse --incomplete-policy drop only after justifying complete-case exclusion."
    ))
  }

  row_pair_key <- paste(data$group, data$id, sep = "\034")
  kept <- data[row_pair_key %in% complete_key & !is.na(data$value), , drop = FALSE]
  if (!nrow(kept)) fail("no complete subjects remain")
  group_order <- ordered_unique(data$group)
  empty_groups <- group_order[!group_order %in% kept$group]
  if (length(empty_groups)) fail(paste0("group has no complete subjects: ", empty_groups[[1L]]))

  list(
    data = kept,
    group_order = group_order,
    condition_order = condition_order,
    has_group = has_group,
    raw_rows = nrow(data),
    complete_subjects = length(complete_key),
    incomplete_subjects = length(incomplete_details),
    excluded_rows = nrow(data) - nrow(kept)
  )
}

group_subjects <- function(input_data, group_name) {
  ordered_unique(input_data$data$id[input_data$data$group == group_name])
}

lookup_value <- function(input_data, group_name, subject_id, condition_name) {
  input_data$data$value[
    input_data$data$group == group_name &
      input_data$data$id == subject_id &
      input_data$data$condition == condition_name
  ][[1L]]
}

direction <- function(delta, tolerance) {
  if (delta > tolerance) "increase" else if (delta < -tolerance) "decrease" else "stable"
}

transition_counts <- function(input_data, group_name, tolerance) {
  subjects <- group_subjects(input_data, group_name)
  results <- vector("list", length(input_data$condition_order) - 1L)
  for (index in seq_len(length(input_data$condition_order) - 1L)) {
    first <- input_data$condition_order[[index]]
    second <- input_data$condition_order[[index + 1L]]
    classes <- vapply(subjects, function(subject_id) {
      delta <- lookup_value(input_data, group_name, subject_id, second) -
        lookup_value(input_data, group_name, subject_id, first)
      direction(delta, tolerance)
    }, character(1L))
    results[[index]] <- list(
      first = first,
      second = second,
      increase = sum(classes == "increase"),
      decrease = sum(classes == "decrease"),
      stable = sum(classes == "stable")
    )
  }
  results
}

geometry <- function(input_data) {
  group_count <- length(input_data$group_order)
  columns <- if (group_count == 1L) {
    1L
  } else if (group_count %in% c(2L, 3L)) {
    group_count
  } else if (group_count == 4L) {
    2L
  } else {
    min(3L, group_count)
  }
  rows <- ceiling(group_count / columns)
  max_label <- max(nchar(c(input_data$condition_order, input_data$group_order), type = "width"))
  proposed_width <- 3.3 + 0.92 * length(input_data$condition_order) + 0.04 * max_label
  panel_width <- if (group_count == 1L) {
    min(12, max(6.6, proposed_width))
  } else {
    min(8.4, max(5.6, proposed_width))
  }
  list(rows = rows, columns = columns, width = panel_width * columns, height = 5 * rows)
}

wrap_label <- function(text, width = 15L) paste(strwrap(text, width = width), collapse = "\n")

draw_box <- function(values, position, color) {
  boxplot(
    values,
    at = position,
    add = TRUE,
    axes = FALSE,
    outline = FALSE,
    boxwex = 0.48,
    col = adjustcolor(color, alpha.f = 0.16),
    border = "#59636C",
    boxlwd = 1,
    medcol = "#20262C",
    medlwd = 1.5,
    whiskcol = "#7B858E",
    whisklwd = 0.9,
    staplecol = "#7B858E",
    staplelwd = 0.9
  )
}

draw_figure <- function(input_data, title_text, y_label, tolerance, layout_info, colors) {
  all_values <- input_data$data$value
  data_min <- min(all_values)
  data_max <- max(all_values)
  span <- max(data_max - data_min, max(abs(c(data_min, data_max)), 1) * 0.2)
  y_limits <- c(data_min - 0.10 * span, data_max + 0.27 * span)
  annotation_y <- data_max + 0.13 * span
  positions <- seq_along(input_data$condition_order)

  par(
    mfrow = c(layout_info$rows, layout_info$columns),
    mar = c(5.2, 4.2, if (input_data$has_group) 2.4 else 1.2, 0.8),
    oma = c(4.5, 1.2, 3.4, 0.5),
    mgp = c(2.5, 0.65, 0),
    tcl = -0.24,
    family = "sans",
    bg = "white"
  )

  for (group_name in input_data$group_order) {
    subjects <- group_subjects(input_data, group_name)
    offsets <- if (length(subjects) > 1L) seq(-0.12, 0.12, length.out = length(subjects)) else 0
    names(offsets) <- sort(subjects)
    plot.new()
    plot.window(xlim = c(0.45, length(positions) + 0.55), ylim = y_limits, xaxs = "i", yaxs = "i")
    abline(h = pretty(range(all_values), n = 6), col = "#E5E9ED", lwd = 0.65)

    arrays <- lapply(input_data$condition_order, function(condition_name) {
      vapply(subjects, function(subject_id) lookup_value(input_data, group_name, subject_id, condition_name), numeric(1L))
    })
    for (index in seq_along(arrays)) draw_box(arrays[[index]], positions[[index]], colors[[index]])

    for (subject_id in subjects) {
      values <- vapply(
        input_data$condition_order,
        function(condition_name) lookup_value(input_data, group_name, subject_id, condition_name),
        numeric(1L)
      )
      x_values <- positions + offsets[[subject_id]]
      for (index in seq_len(length(positions) - 1L)) {
        status <- direction(values[[index + 1L]] - values[[index]], tolerance)
        line_color <- c(increase = INCREASE_COLOR, decrease = DECREASE_COLOR, stable = STABLE_COLOR)[[status]]
        segments(
          x_values[[index]], values[[index]], x_values[[index + 1L]], values[[index + 1L]],
          col = adjustcolor(line_color, alpha.f = if (length(subjects) <= 150L) 0.46 else 0.25),
          lwd = if (length(subjects) <= 150L) 0.75 else 0.45
        )
      }
      points(
        x_values,
        values,
        pch = 21,
        bg = colors,
        col = "white",
        lwd = 0.35,
        cex = if (length(subjects) <= 150L) 0.75 else 0.48
      )
    }

    if (length(input_data$condition_order) <= 6L) {
      counts <- transition_counts(input_data, group_name, tolerance)
      for (index in seq_along(counts)) {
        item <- counts[[index]]
        text(
          index + 0.5,
          annotation_y,
          sprintf("↑%d  ↓%d  =%d", item$increase, item$decrease, item$stable),
          cex = 0.68,
          col = "#4C5560"
        )
      }
    }

    labels <- vapply(
      input_data$condition_order,
      function(condition_name) paste0(wrap_label(condition_name), "\n(n=", length(subjects), ")"),
      character(1L)
    )
    axis(1, at = positions, labels = labels, tick = FALSE, cex.axis = 0.75, padj = 0.4)
    axis(2, las = 1, cex.axis = 0.76, col = "#77818A", col.axis = "#4A525B")
    box(bty = "l", col = "#77818A", lwd = 0.8)
    if (input_data$has_group) {
      mtext(
        paste0(group_name, " · n=", length(subjects), " complete subjects"),
        side = 3,
        line = 0.65,
        adj = 0,
        cex = 0.90,
        font = 2,
        col = "#20262C"
      )
    }
  }

  unused <- layout_info$rows * layout_info$columns - length(input_data$group_order)
  if (unused > 0L) for (index in seq_len(unused)) plot.new()
  subtitle <- sprintf(
    "%d complete subjects · %d ordered conditions · %d group%s",
    input_data$complete_subjects,
    length(input_data$condition_order),
    length(input_data$group_order),
    if (length(input_data$group_order) == 1L) "" else "s"
  )
  if (input_data$incomplete_subjects) {
    subtitle <- paste0(subtitle, " · dropped ", input_data$incomplete_subjects, " incomplete subjects")
  }
  mtext(title_text, side = 3, outer = TRUE, line = 1.35, adj = 0, cex = 1.35, font = 2, col = "#20262C")
  mtext(subtitle, side = 3, outer = TRUE, line = 0.10, adj = 0, cex = 0.82, col = "#59616B")
  mtext(y_label, side = 2, outer = TRUE, line = 0.1, cex = 0.95, col = "#20262C")
  mtext(
    sprintf(
      "Lines join the same ID. Segment direction: teal ↑, orange ↓, gray within ±%g. Boxes show Q1–Q3, median and 1.5×IQR whiskers; no inferential test is performed.",
      tolerance
    ),
    side = 1,
    outer = TRUE,
    line = 3.3,
    adj = 0,
    cex = 0.65,
    col = "#66707A"
  )
}

report_data <- function(input_data, tolerance) {
  cat(sprintf(
    "Loaded %d rows: %d complete subject(s), %d incomplete subject(s), %d row(s) excluded; %d condition(s), %d group(s).\n",
    input_data$raw_rows,
    input_data$complete_subjects,
    input_data$incomplete_subjects,
    input_data$excluded_rows,
    length(input_data$condition_order),
    length(input_data$group_order)
  ))
  for (group_name in input_data$group_order) {
    subjects <- group_subjects(input_data, group_name)
    cat(sprintf("group=%s | complete subjects=%d\n", group_name, length(subjects)))
    for (condition_name in input_data$condition_order) {
      values <- vapply(subjects, function(subject_id) {
        lookup_value(input_data, group_name, subject_id, condition_name)
      }, numeric(1L))
      quartiles <- quantile(values, c(0.25, 0.5, 0.75), type = 7, names = FALSE)
      cat(sprintf(
        "  condition=%s | n=%d | q1=%s | median=%s | q3=%s\n",
        condition_name,
        length(values),
        format(quartiles[[1L]], digits = 6),
        format(quartiles[[2L]], digits = 6),
        format(quartiles[[3L]], digits = 6)
      ))
    }
    for (item in transition_counts(input_data, group_name, tolerance)) {
      cat(sprintf(
        "  transition=%s -> %s | increase=%d | decrease=%d | within_tolerance=%d\n",
        item$first, item$second, item$increase, item$decrease, item$stable
      ))
    }
  }
}

render_output <- function(kind, path, layout_info, callback) {
  if (identical(kind, "png")) {
    png(
      path,
      width = layout_info$width,
      height = layout_info$height,
      units = "in",
      res = 320,
      type = if (capabilities("cairo")) "cairo" else getOption("bitmapType")
    )
  } else {
    svg(path, width = layout_info$width, height = layout_info$height, onefile = TRUE, bg = "white", family = "sans")
  }
  device_id <- dev.cur()
  on.exit(if (dev.cur() == device_id) dev.off(), add = FALSE)
  callback()
  dev.off()
  on.exit(NULL, add = FALSE)
}

main <- function() {
  config <- parse_args(commandArgs(trailingOnly = TRUE))
  requested_order <- parse_condition_order(config$condition_order)
  input_data <- read_input(config$input, requested_order, config$incomplete_policy)
  layout_info <- geometry(input_data)
  colors <- hcl.colors(length(input_data$condition_order), palette = "Dark 3")
  output_directory <- dirname(config$output_prefix)
  if (!dir.exists(output_directory)) dir.create(output_directory, recursive = TRUE, showWarnings = FALSE)
  if (!dir.exists(output_directory)) fail(paste0("could not create output directory: ", output_directory))
  callback <- function() draw_figure(input_data, config$title, config$y_label, config$change_tolerance, layout_info, colors)
  png_path <- paste0(config$output_prefix, ".png")
  svg_path <- paste0(config$output_prefix, ".svg")
  render_output("png", png_path, layout_info, callback)
  render_output("svg", svg_path, layout_info, callback)
  report_data(input_data, config$change_tolerance)
  cat("Wrote ", png_path, "\n", sep = "")
  cat("Wrote ", svg_path, "\n", sep = "")
}

status <- tryCatch({
  main()
  0L
}, error = function(error) {
  message("ERROR: ", conditionMessage(error))
  2L
})
quit(save = "no", status = status)
