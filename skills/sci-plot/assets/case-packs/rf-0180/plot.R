frame_files <- vapply(sys.frames(), function(frame) if (is.null(frame$ofile)) "" else as.character(frame$ofile), character(1))
source_arg <- tail(frame_files[nzchar(frame_files)], 1)
args <- commandArgs(trailingOnly = FALSE)
script_arg <- grep("^--file=", args, value = TRUE)
script_path <- if (length(source_arg)) source_arg else if (length(script_arg)) gsub("~+~", " ", sub("^--file=", "", script_arg[1]), fixed = TRUE) else ""
if (!nzchar(script_path)) stop("Unable to resolve the script location")
root <- dirname(normalizePath(script_path, winslash = "/", mustWork = TRUE))
d <- read.csv(file.path(root, "data.csv"), stringsAsFactors = FALSE, check.names = FALSE)
expected_columns <- c("runaway_id", "spectral_type", "spt_short", "phot_g_mean_mag", "v_t", "v_t_error", "v_t_error_plus", "v_t_error_min", "t_kin", "t_kin_error_plus", "t_kin_error_min")
stopifnot(nrow(d) == 55, identical(names(d), expected_columns), length(unique(d$runaway_id)) == nrow(d), !anyNA(d))
numeric_columns <- setdiff(expected_columns, c("spectral_type", "spt_short"))
stopifnot(all(vapply(d[numeric_columns], is.numeric, logical(1))), all(is.finite(as.matrix(d[numeric_columns]))))
error_columns <- c("v_t_error", "v_t_error_plus", "v_t_error_min", "t_kin_error_plus", "t_kin_error_min")
stopifnot(all(as.matrix(d[error_columns]) > 0), all(d$v_t - d$v_t_error_min > 0))
category_order <- c("wnh", "o2", "o3", "o4", "o5", "o6", "o7", "o8", "o9", "borlater", "unk")
category_labels <- c(wnh = "WN(h)", o2 = "O2", o3 = "O3", o4 = "O4", o5 = "O5", o6 = "O6", o7 = "O7", o8 = "O8", o9 = "O9", borlater = "B or later", unk = "Unknown")
category_colors <- c(wnh = "#6C5B7B", o2 = "#0072B2", o3 = "#56B4E9", o4 = "#009E73", o5 = "#7A9E3A", o6 = "#E3A11A", o7 = "#E07A2D", o8 = "#D95F45", o9 = "#A33A3A", borlater = "#8A5A44", unk = "#8A9094")
stopifnot(setequal(unique(d$spt_short), category_order))
magnitude_marker <- function(value) if (value > 15) 21 else if (value < 13) 23 else 22
bin_width <- 0.15
bandwidth <- 0.20
bin_edges <- seq(0, 3, by = bin_width)
histogram <- hist(d$t_kin, breaks = bin_edges, plot = FALSE, include.lowest = TRUE, right = FALSE)
kde_grid <- seq(0, 3, length.out = 600)
kde_density <- vapply(kde_grid, function(value) mean(dnorm((value - d$t_kin) / bandwidth)) / bandwidth, numeric(1))
kde_scaled <- kde_density * nrow(d) * bin_width
mag_counts <- c(sum(d$phot_g_mean_mag > 15), sum(d$phot_g_mean_mag >= 13 & d$phot_g_mean_mag <= 15), sum(d$phot_g_mean_mag < 13))
bg <- "#F7F6F2"
ink <- "#17242C"
muted <- "#58676D"
grid_color <- "#D8DAD6"
device_args <- list(filename = file.path(root, "plot_r.png"), width = 13.4, height = 9.6, units = "in", res = 360, bg = bg)
if (.Platform$OS.type != "windows" && capabilities("cairo")) device_args$type <- "cairo"
do.call(png, device_args)
layout(matrix(c(1, 2, 3, 4), nrow = 2, byrow = TRUE), widths = c(4.5, 1.35), heights = c(1.25, 4.35))
par(oma = c(4.4, 0.9, 5.1, 0.9), bg = bg, fg = ink, family = "sans")
par(mar = c(1.5, 5.2, 2.7, 0.7))
y_max <- max(c(histogram$counts, kde_scaled)) * 1.18
plot(NA, xlim = c(0, 3), ylim = c(0, y_max), xaxs = "i", yaxs = "i", xlab = "", ylab = "Objects per 0.15 Myr", axes = FALSE)
abline(h = pretty(c(0, y_max)), col = grid_color, lwd = 0.6)
rect(histogram$breaks[-length(histogram$breaks)], 0, histogram$breaks[-1], histogram$counts, col = "#D98067", border = bg, lwd = 1)
lines(kde_grid, kde_scaled, col = ink, lwd = 2)
axis(1, at = seq(0, 3, 0.5), cex.axis = 0.8)
axis(2, las = 1, cex.axis = 0.8)
box(bty = "l", col = "#69767B", lwd = 0.8)
title("a   Kinematic-age distribution", adj = 0, line = 1.0, cex.main = 1.1, font.main = 2)
legend("topright", legend = c("Histogram", "Gaussian KDE, bw = 0.20 Myr"), lwd = c(7, 2), col = c("#D98067", ink), bty = "n", cex = 0.72, seg.len = 1.5)
par(mar = c(0.5, 0.5, 2.7, 0.5))
plot.new()
plot.window(xlim = c(0, 1), ylim = c(0, 1))
text(0.02, 0.96, "Dataset overview", adj = c(0, 1), cex = 0.95, font = 2)
text(0.02, 0.74, sprintf("%d objects\n%d supplied spectral classes", nrow(d), length(category_order)), adj = c(0, 1), cex = 0.78, col = muted)
text(0.02, 0.38, "Photometric G strata", adj = c(0, 1), cex = 0.74, font = 2)
text(0.02, 0.22, sprintf("> 15: %d   13 to 15: %d   < 13: %d", mag_counts[1], mag_counts[2], mag_counts[3]), adj = c(0, 1), cex = 0.66, col = muted)
par(mar = c(4.2, 5.2, 2.8, 0.7))
plot(NA, xlim = c(0, 4), ylim = c(18, 220), log = "y", xaxs = "i", yaxs = "i", xlab = "Kinematic age (Myr)", ylab = expression(paste("Transverse velocity (km ", s^{-1}, ")")), axes = FALSE)
abline(v = seq(0, 4, 0.5), h = c(20, 30, 50, 100, 200), col = grid_color, lwd = 0.6)
abline(h = 27.6, col = "#37474D", lty = 2, lwd = 1)
text(3.96, 27.6 * 1.035, expression("27.6 km " * s^{-1} * " reference threshold"), adj = c(1, 0), cex = 0.63, col = "#37474D")
for (i in seq_len(nrow(d))) {
  x_low <- d$t_kin[i] - d$t_kin_error_min[i]
  x_high <- d$t_kin[i] + d$t_kin_error_plus[i]
  y_low <- d$v_t[i] - d$v_t_error_min[i]
  y_high <- d$v_t[i] + d$v_t_error_plus[i]
  segments(x_low, d$v_t[i], x_high, d$v_t[i], col = "#6E777B9E", lwd = 0.85)
  segments(x_low, d$v_t[i] / 1.018, x_low, d$v_t[i] * 1.018, col = "#6E777B9E", lwd = 0.75)
  segments(x_high, d$v_t[i] / 1.018, x_high, d$v_t[i] * 1.018, col = "#6E777B9E", lwd = 0.75)
  segments(d$t_kin[i], y_low, d$t_kin[i], y_high, col = "#6E777B9E", lwd = 0.85)
  segments(d$t_kin[i] - 0.014, y_low, d$t_kin[i] + 0.014, y_low, col = "#6E777B9E", lwd = 0.75)
  segments(d$t_kin[i] - 0.014, y_high, d$t_kin[i] + 0.014, y_high, col = "#6E777B9E", lwd = 0.75)
  points(d$t_kin[i], d$v_t[i], pch = magnitude_marker(d$phot_g_mean_mag[i]), bg = category_colors[d$spt_short[i]], col = ink, cex = 0.88, lwd = 0.55)
}
axis(1, at = seq(0, 4, 0.5), cex.axis = 0.8)
axis(2, at = c(20, 30, 50, 100, 200), labels = c("20", "30", "50", "100", "200"), las = 1, cex.axis = 0.8)
box(bty = "l", col = "#69767B", lwd = 0.8)
title("b   Velocity with asymmetric uncertainty in both axes", adj = 0, line = 1.0, cex.main = 1.1, font.main = 2)
par(mar = c(3.8, 0.5, 2.8, 0.5))
plot.new()
plot.window(xlim = c(0, 1), ylim = c(0, 1))
legend(0, 1, legend = unname(category_labels[category_order]), title = "Discrete spectral class", pch = 21, pt.bg = unname(category_colors[category_order]), col = ink, pt.cex = 0.9, cex = 0.68, bty = "n", xjust = 0, yjust = 1, x.intersp = 0.75, y.intersp = 0.82)
legend(0, 0.18, legend = c("G > 15", "13 <= G <= 15", "G < 13"), title = "Photometric G stratum", pch = c(21, 22, 23), pt.bg = "white", col = ink, pt.cex = 0.9, cex = 0.68, bty = "n", xjust = 0, yjust = 1, x.intersp = 0.75, y.intersp = 0.95)
mtext("Kinematic age and transverse velocity in the supplied runaway-star sample", side = 3, outer = TRUE, line = 3.5, adj = 0, cex = 1.55, font = 2, col = ink)
mtext("All 55 objects are shown; colours are categorical, while marker shape records the supplied photometric-magnitude stratum.", side = 3, outer = TRUE, line = 2.0, adj = 0, cex = 0.8, col = muted)
mtext("Asymmetric lower/upper uncertainties come directly from t_kin_error_min/plus and v_t_error_min/plus. The 27.6 km s^-1 line is a reference threshold from the original workflow, not an estimate from these data.", side = 1, outer = TRUE, line = 2.5, adj = 0, cex = 0.67, col = muted)
mtext("The density curve is descriptive only and uses a fixed 0.20-Myr Gaussian bandwidth, scaled to the 0.15-Myr histogram-bin count.", side = 1, outer = TRUE, line = 1.15, adj = 0, cex = 0.67, col = muted)
invisible(dev.off())
