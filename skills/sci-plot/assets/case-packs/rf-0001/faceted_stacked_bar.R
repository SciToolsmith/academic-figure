args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
base_dir <- if (length(file_arg)) dirname(normalizePath(sub("^--file=", "", file_arg[1]), winslash = "/", mustWork = FALSE)) else getwd()
data <- read.csv(file.path(base_dir, "faceted_stacked_bar_data.csv"), stringsAsFactors = FALSE, check.names = FALSE)
output <- file.path(base_dir, "faceted_stacked_bar_r.png")
days <- c("Day 0", "Day 7", "Day 10", "Day 31")
legend_order <- c("Microbe_7", "Microbe_4", "Microbe_2", "Microbe_9", "Microbe_5", "Microbe_8", "Microbe_1", "Microbe_3", "Microbe_6", "Microbe_10")
stack_order <- rev(legend_order)
colors <- c(Microbe_1 = "#D3D1D2", Microbe_2 = "#CC79A8", Microbe_3 = "#7AC0EA", Microbe_4 = "#0EA079", Microbe_5 = "#68C49D", Microbe_6 = "#EACEDF", Microbe_7 = "#5AB4E5", Microbe_8 = "#D99BBB", Microbe_9 = "#98D1F0", Microbe_10 = "#7F7F7F")
stopifnot(nrow(data) == 240, all(data$source_type == "simulated"), all(data$source_seed == 123))
png(output, width = 2400, height = 1360, res = 200, bg = "white", type = if (.Platform$OS.type == "windows") "windows" else "cairo")
par(family = "sans")
panel_left <- c(0.09, 0.265, 0.44, 0.615)
panel_right <- panel_left + 0.163
for (panel_index in seq_along(days)) {
  day <- days[panel_index]
  frame <- data[data$day == day, ]
  samples <- sort(unique(frame$sample_id))
  matrix_values <- sapply(samples, function(sample) {
    values <- frame$relative_abundance[frame$sample_id == sample]
    names(values) <- frame$microbe[frame$sample_id == sample]
    values[stack_order]
  })
  par(fig = c(panel_left[panel_index], panel_right[panel_index], 0.18, 0.79), mar = c(3.8, if (panel_index == 1) 4.8 else 0.5, 0.3, 0.4), new = panel_index > 1)
  bar_positions <- barplot(matrix_values, plot = FALSE, space = 0.08)
  plot(NA, xlim = c(min(bar_positions) - 0.55, max(bar_positions) + 0.55), ylim = c(0, 1), axes = FALSE, xlab = "", ylab = "", xaxs = "i", yaxs = "i")
  abline(h = seq(0, 1, 0.25), col = "#E5E8EB", lwd = 0.7)
  barplot(matrix_values, col = colors[stack_order], border = "white", lwd = 0.55, space = 0.08, axes = FALSE, add = TRUE)
  axis(1, at = mean(range(bar_positions)), labels = day, tick = FALSE, line = 1.5, cex.axis = 1.05, font = 2, col.axis = "#2F3740")
  if (panel_index == 1) {
    axis(2, at = seq(0, 1, 0.25), labels = paste0(seq(0, 100, 25), "%"), las = 1, cex.axis = 0.86, tck = -0.018, col = "#2F3740", col.axis = "#4E5965")
    mtext("Relative abundance", side = 2, line = 3.4, cex = 1.02, font = 2, col = "#2F3740")
  }
  segments(par("usr")[1], 0, par("usr")[2], 0, col = "#2F3740", lwd = 1.0)
  if (panel_index == 1) segments(par("usr")[1], 0, par("usr")[1], 1, col = "#2F3740", lwd = 1.0)
}
par(fig = c(0.80, 0.98, 0.22, 0.76), mar = c(0, 0, 0, 0), new = TRUE)
plot.new()
legend("topleft", legend = legend_order, fill = colors[legend_order], border = NA, title = "Family", bty = "n", cex = 0.85, title.adj = 0, y.intersp = 1.12, x.intersp = 0.55)
par(fig = c(0, 1, 0, 1), mar = c(0, 0, 0, 0), new = TRUE)
plot.new()
text(0.09, 0.945, "Microbial community composition", adj = 0, cex = 1.72, font = 2, col = "#20262E")
text(0.09, 0.902, "Vehicle cohort \u00b7 simulated composition generated with R seed 123", adj = 0, cex = 0.92, col = "#63707C")
dev.off()
