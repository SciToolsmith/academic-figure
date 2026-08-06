script_path <- function() {
  frames <- sys.frames()
  files <- vapply(
    frames,
    function(frame) {
      value <- frame$ofile
      if (is.null(value)) "" else as.character(value)
    },
    character(1)
  )
  files <- files[nzchar(files)]
  if (length(files) > 0) {
    return(normalizePath(tail(files, 1), winslash = "/", mustWork = TRUE))
  }
  arguments <- commandArgs(trailingOnly = FALSE)
  matches <- grep("^--file=", arguments, value = TRUE)
  if (length(matches) > 0) {
    return(normalizePath(sub("^--file=", "", tail(matches, 1)), winslash = "/", mustWork = TRUE))
  }
  stop("Unable to resolve script path")
}

base_dir <- dirname(script_path())
groups_a <- c("intra-primary", "intra-met", "inter-met", "primary-met")
labels_a <- c("Intra-primary", "Intra-met", "Inter-met", "Primary-met")
colors_a <- c("#355C7D", "#12664F", "#2A9D62", "#209DB5")
comparisons_a <- list(
  c("intra-primary", "intra-met"),
  c("intra-met", "inter-met"),
  c("intra-primary", "inter-met"),
  c("inter-met", "primary-met"),
  c("intra-primary", "primary-met")
)
types_b <- c(
  "Plasma",
  "CD27+ effector B",
  "CD27- effector B",
  "CD95 memory B",
  "Core memory B",
  "Type 2 polarized memory B"
)
ages_b <- c("Young", "Older")
days_b <- c("Day 0", "Day 7")
colors_b <- c(Young = "#228C82", Older = "#C98324")

format_probability <- function(value) {
  if (value < 0.001) {
    formatC(value, format = "e", digits = 2)
  } else {
    formatC(value, format = "f", digits = 4)
  }
}

draw_box <- function(values, position, color, width = 0.54) {
  boxplot(
    values,
    at = position,
    add = TRUE,
    axes = FALSE,
    outline = FALSE,
    boxwex = width,
    col = adjustcolor(color, alpha.f = 0.18),
    border = "#66737A",
    boxlwd = 1.2,
    medcol = "#1C2930",
    medlwd = 1.8,
    whiskcol = "#849097",
    whisklwd = 1,
    staplecol = "#849097",
    staplelwd = 1,
    staplewex = 0.5
  )
}

data_a <- read.csv(
  file.path(base_dir, "data1.csv"),
  stringsAsFactors = FALSE,
  check.names = FALSE,
  na.strings = c("", "NA")
)
if (!identical(names(data_a), c("id", "variable", "value")) || nrow(data_a) != 96) {
  stop("Unexpected data1.csv schema or row count")
}
if (!setequal(unique(data_a$variable), groups_a)) {
  stop("Unexpected mutation-diversity group")
}
keys_a <- paste(data_a$id, data_a$variable, sep = "\r")
if (anyDuplicated(keys_a) > 0 || any(!nzchar(data_a$id)) || any(!nzchar(data_a$variable))) {
  stop("Invalid data1 patient-group key")
}
if (sum(is.na(data_a$value)) != 5) {
  stop("Unexpected data1 missing-value count")
}
ids_a <- sort(unique(data_a$id))

tests_a <- lapply(
  comparisons_a,
  function(comparison) {
    first <- data_a[
      data_a$variable == comparison[1] & !is.na(data_a$value),
      c("id", "value")
    ]
    second <- data_a[
      data_a$variable == comparison[2] & !is.na(data_a$value),
      c("id", "value")
    ]
    paired <- merge(first, second, by = "id", suffixes = c(".first", ".second"))
    result <- wilcox.test(
      paired$value.first,
      paired$value.second,
      paired = TRUE,
      alternative = "two.sided",
      exact = TRUE
    )
    list(
      first = comparison[1],
      second = comparison[2],
      n = nrow(paired),
      p = unname(result$p.value),
      delta = median(paired$value.second - paired$value.first)
    )
  }
)
q_a <- p.adjust(vapply(tests_a, function(test) test$p, numeric(1)), method = "BH")
for (index in seq_along(tests_a)) {
  tests_a[[index]]$q <- unname(q_a[index])
}

data_b <- read.csv(
  file.path(base_dir, "data2.csv"),
  stringsAsFactors = FALSE,
  check.names = FALSE
)
if (!identical(names(data_b), c("ID", "Age", "Day", "Type", "Value")) || nrow(data_b) != 814) {
  stop("Unexpected data2.csv schema or row count")
}
if (!setequal(unique(data_b$Age), ages_b) ||
    !setequal(unique(data_b$Day), days_b) ||
    !setequal(unique(data_b$Type), types_b)) {
  stop("Unexpected data2 category")
}
if (anyNA(data_b) || any(!nzchar(data_b$ID))) {
  stop("Missing data2 field")
}
keys_b <- paste(data_b$ID, data_b$Age, data_b$Day, data_b$Type, sep = "\r")
if (anyDuplicated(keys_b) > 0) {
  stop("Duplicate data2 patient-age-day-type key")
}
age_counts <- tapply(data_b$Age, data_b$ID, function(values) length(unique(values)))
if (any(age_counts != 1)) {
  stop("Patient assigned to multiple age groups")
}

tests_b <- list()
for (cell_type in types_b) {
  for (age in ages_b) {
    day0 <- data_b[
      data_b$Type == cell_type & data_b$Age == age & data_b$Day == "Day 0",
      c("ID", "Value")
    ]
    day7 <- data_b[
      data_b$Type == cell_type & data_b$Age == age & data_b$Day == "Day 7",
      c("ID", "Value")
    ]
    paired <- merge(day0, day7, by = "ID", suffixes = c(".day0", ".day7"))
    result <- wilcox.test(
      paired$Value.day0,
      paired$Value.day7,
      paired = TRUE,
      alternative = "two.sided",
      exact = TRUE
    )
    tests_b[[length(tests_b) + 1]] <- list(
      type = cell_type,
      age = age,
      ids = paired$ID,
      day0 = paired$Value.day0,
      day7 = paired$Value.day7,
      n = nrow(paired),
      p = unname(result$p.value)
    )
  }
}
q_b <- p.adjust(vapply(tests_b, function(test) test$p, numeric(1)), method = "BH")
for (index in seq_along(tests_b)) {
  tests_b[[index]]$q <- unname(q_b[index])
}

background <- "#F5F7F5"
png_arguments <- list(
  filename = file.path(base_dir, "plot_r.png"),
  width = 18,
  height = 13,
  units = "in",
  res = 360,
  bg = background
)
if (capabilities("cairo")) {
  png_arguments$type <- "cairo"
}
do.call(grDevices::png, png_arguments)
layout(
  matrix(
    c(
      1, 1, 1, 1, 1, 1,
      2, 2, 2, 2, 3, 3,
      4, 4, 4, 4, 4, 4,
      5, 5, 6, 6, 7, 7,
      8, 8, 9, 9, 10, 10,
      11, 11, 11, 11, 11, 11
    ),
    nrow = 6,
    byrow = TRUE
  ),
  widths = rep(1, 6),
  heights = c(0.20, 1.15, 0.17, 0.95, 0.95, 0.33)
)
par(
  family = "sans",
  fg = "#17242C",
  col.axis = "#31414A",
  col.lab = "#17242C",
  col.main = "#17242C",
  bg = background
)

par(mar = rep(0, 4))
plot.new()
text(
  0.01,
  0.73,
  "Paired within-patient profiles across diversity and immune-cell states",
  adj = c(0, 0.5),
  cex = 2.08,
  font = 2
)
text(
  0.01,
  0.20,
  "Raw observations, paired trajectories and distribution summaries",
  adj = c(0, 0.5),
  cex = 1.05,
  col = "#5B6A72"
)

par(mar = c(4.6, 5.2, 3.4, 0.8), mgp = c(3.1, 0.8, 0), tcl = -0.24)
plot(
  NA,
  xlim = c(0.45, 4.55),
  ylim = c(-0.035, 1.02),
  axes = FALSE,
  xlab = "",
  ylab = ""
)
abline(h = seq(0, 1, by = 0.2), col = "#DDE4E1", lwd = 0.8)
offsets_a <- setNames(seq(-0.14, 0.14, length.out = length(ids_a)), ids_a)
for (patient in ids_a) {
  for (index in 1:3) {
    first_value <- data_a$value[data_a$id == patient & data_a$variable == groups_a[index]]
    second_value <- data_a$value[data_a$id == patient & data_a$variable == groups_a[index + 1]]
    if (length(first_value) == 1 && length(second_value) == 1 &&
        !is.na(first_value) && !is.na(second_value)) {
      segments(
        index + offsets_a[patient],
        first_value,
        index + 1 + offsets_a[patient],
        second_value,
        col = adjustcolor("#8D989D", alpha.f = 0.62),
        lwd = 0.8
      )
    }
  }
}
arrays_a <- lapply(
  groups_a,
  function(group) data_a$value[data_a$variable == group & !is.na(data_a$value)]
)
for (index in seq_along(groups_a)) {
  draw_box(arrays_a[[index]], index, colors_a[index], 0.58)
  patients <- data_a$id[data_a$variable == groups_a[index] & !is.na(data_a$value)]
  values <- data_a$value[data_a$variable == groups_a[index] & !is.na(data_a$value)]
  points(
    index + offsets_a[patients],
    values,
    pch = 21,
    bg = colors_a[index],
    col = "#FFFFFF",
    lwd = 0.45,
    cex = 1.05
  )
}
axis(
  1,
  at = 1:4,
  labels = sprintf("%s\n(n=%d)", labels_a, vapply(arrays_a, length, integer(1))),
  cex.axis = 0.9,
  padj = 0.3
)
axis(2, at = seq(0, 1, by = 0.2), las = 1, cex.axis = 0.9)
box(bty = "l", col = "#7D8A91", lwd = 0.9)
mtext("Mean mutation diversity per patient", side = 2, line = 3.25, cex = 1.02)
mtext("A   Mutation diversity", side = 3, line = 1.55, adj = 0, cex = 1.28, font = 2)
mtext(
  "24 supplied patient IDs; 5 missing values retained as missing",
  side = 3,
  line = 0.35,
  adj = 0,
  cex = 0.82,
  col = "#5B6A72"
)

par(mar = c(1.5, 0.8, 3.4, 0.7))
plot.new()
plot.window(xlim = c(0, 1), ylim = c(0, 1))
text(0, 1.08, "Displayed paired comparisons", adj = c(0, 0), cex = 1.15, font = 2, xpd = NA)
text(0, 1.015, "Complete common IDs per row", adj = c(0, 0), cex = 0.82, col = "#5B6A72", xpd = NA)
headers <- c("Comparison", "n", "Median Δ", "raw p", "BH q")
columns <- c(0, 0.50, 0.69, 0.84, 0.98)
alignments <- c(0, 1, 1, 1, 1)
for (index in seq_along(headers)) {
  text(
    columns[index],
    0.91,
    headers[index],
    adj = c(alignments[index], 0.5),
    cex = 0.76,
    font = 2,
    col = "#3B4B54"
  )
}
segments(0, 0.865, 0.99, 0.865, col = "#9AA6AB", lwd = 0.9)
short_labels <- c(
  "intra-primary" = "Intra-primary",
  "intra-met" = "Intra-met",
  "inter-met" = "Inter-met",
  "primary-met" = "Primary-met"
)
for (index in seq_along(tests_a)) {
  test <- tests_a[[index]]
  y_value <- 0.77 - (index - 1) * 0.145
  if (index %% 2 == 1) {
    rect(0, y_value - 0.064, 0.99, y_value + 0.064, col = "#EAF0ED", border = NA)
  }
  values <- c(
    paste0(short_labels[test$first], " → ", short_labels[test$second]),
    as.character(test$n),
    sprintf("%+.3f", test$delta),
    format_probability(test$p),
    format_probability(test$q)
  )
  for (column_index in seq_along(values)) {
    text(
      columns[column_index],
      y_value,
      values[column_index],
      adj = c(alignments[column_index], 0.5),
      cex = 0.73,
      font = if (column_index == 5 && test$q < 0.05) 2 else 1
    )
  }
}
text(0, -0.02, "Δ = median(second − first)", adj = c(0, 0), cex = 0.73, col = "#5B6A72", xpd = NA)

par(mar = rep(0, 4))
plot.new()
text(
  0.01,
  0.72,
  "B   B-cell frequency change from Day 0 to Day 7",
  adj = c(0, 0.5),
  cex = 1.25,
  font = 2
)
text(
  0.01,
  0.15,
  "Pairing is performed separately by patient ID within each age group",
  adj = c(0, 0.5),
  cex = 0.82,
  col = "#5B6A72"
)

draw_b_panel <- function(cell_type, panel_index) {
  selected <- tests_b[vapply(tests_b, function(test) test$type == cell_type, logical(1))]
  names(selected) <- vapply(selected, function(test) test$age, character(1))
  positions <- c(1, 2, 3.65, 4.65)
  arrays <- list(
    selected$Young$day0,
    selected$Young$day7,
    selected$Older$day0,
    selected$Older$day7
  )
  all_values <- unlist(arrays, use.names = FALSE)
  span <- max(diff(range(all_values)), 0.8)
  lower <- min(all_values) - span * 0.08
  upper <- max(all_values) + span * 0.28
  par(
    mar = c(4.1, if (panel_index %% 3 == 1) 4.0 else 2.8, 2.5, 0.5),
    mgp = c(2.45, 0.65, 0),
    tcl = -0.22
  )
  plot(
    NA,
    xlim = c(0.45, 5.20),
    ylim = c(lower, upper),
    axes = FALSE,
    xlab = "",
    ylab = ""
  )
  abline(h = pretty(range(all_values), n = 5), col = "#E1E7E4", lwd = 0.7)
  for (age_index in seq_along(ages_b)) {
    age <- ages_b[age_index]
    test <- selected[[age]]
    offsets <- setNames(seq(-0.12, 0.12, length.out = test$n), test$ids)
    first_position <- if (age == "Young") 1 else 3.65
    for (index in seq_along(test$ids)) {
      patient <- test$ids[index]
      segments(
        first_position + offsets[patient],
        test$day0[index],
        first_position + 1 + offsets[patient],
        test$day7[index],
        col = adjustcolor("#879399", alpha.f = 0.62),
        lwd = 0.6
      )
      points(
        c(first_position + offsets[patient], first_position + 1 + offsets[patient]),
        c(test$day0[index], test$day7[index]),
        pch = 21,
        bg = colors_b[age],
        col = "#FFFFFF",
        lwd = 0.3,
        cex = 0.62
      )
    }
  }
  box_colors <- c(colors_b["Young"], colors_b["Young"], colors_b["Older"], colors_b["Older"])
  for (index in seq_along(arrays)) {
    draw_box(arrays[[index]], positions[index], box_colors[index], 0.52)
  }
  axis(
    1,
    at = positions,
    labels = c("Day 0\nYoung", "Day 7\nYoung", "Day 0\nOlder", "Day 7\nOlder"),
    cex.axis = 0.68,
    padj = 0.3
  )
  axis(2, at = pretty(range(all_values), n = 5), las = 1, cex.axis = 0.7)
  box(bty = "l", col = "#7D8A91", lwd = 0.8)
  mtext(cell_type, side = 3, line = 1.25, adj = 0, cex = 0.88, font = 2)
  text(
    0.57,
    upper - span * 0.025,
    sprintf(
      "Young n=%d  p=%s  q=%s",
      selected$Young$n,
      format_probability(selected$Young$p),
      format_probability(selected$Young$q)
    ),
    adj = c(0, 1),
    cex = 0.62,
    col = colors_b["Young"],
    font = 2
  )
  text(
    0.57,
    upper - span * 0.125,
    sprintf(
      "Older n=%d  p=%s  q=%s",
      selected$Older$n,
      format_probability(selected$Older$p),
      format_probability(selected$Older$q)
    ),
    adj = c(0, 1),
    cex = 0.62,
    col = colors_b["Older"],
    font = 2
  )
  if (panel_index %% 3 == 1) {
    mtext("Frequency (CLR)", side = 2, line = 2.45, cex = 0.82)
  }
}

for (index in seq_along(types_b)) {
  draw_b_panel(types_b[index], index)
}

par(mar = rep(0, 4))
plot.new()
text(
  0.01,
  0.78,
  "Supplied: patient IDs, group/time labels and observed values. Derived: box summaries, paired median changes, p values and BH q values.",
  adj = c(0, 0.5),
  cex = 0.72,
  col = "#506069"
)
text(
  0.01,
  0.48,
  "Tests are two-sided exact paired Wilcoxon tests; raw p and BH q are shown, with correction applied separately across A (5 comparisons) and B (12 comparisons).",
  adj = c(0, 0.5),
  cex = 0.72,
  col = "#506069"
)
text(
  0.01,
  0.18,
  "Panel A uses complete common IDs for each comparison. Panel B Plasma/Young lacks BR1023 at both days (n = 25); all other Young tests use n = 26 and Older tests use n = 42. No between-age tests were performed.",
  adj = c(0, 0.5),
  cex = 0.72,
  col = "#506069"
)
dev.off()
