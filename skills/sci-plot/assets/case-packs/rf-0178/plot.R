frame_files <- vapply(sys.frames(), function(x) {
  value <- x$ofile
  if (is.null(value)) "" else as.character(value)
}, character(1))
frame_files <- frame_files[nzchar(frame_files)]
if (length(frame_files) > 0) {
  script_path <- normalizePath(frame_files[length(frame_files)], mustWork = TRUE)
} else {
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args, value = TRUE)
  if (length(file_arg) == 0) stop("Cannot resolve plot.R location")
  script_path <- normalizePath(gsub("~+~", " ", sub("^--file=", "", file_arg[1]), fixed = TRUE), mustWork = TRUE)
}
base_dir <- dirname(script_path)
data_path <- file.path(base_dir, "data.csv")
output_path <- file.path(base_dir, "plot_r.png")
d <- read.csv(data_path, check.names = FALSE, stringsAsFactors = FALSE, fileEncoding = "UTF-8-BOM")
required <- c("completeness", "number_of_cds", "type", "length")
if (!all(required %in% names(d))) stop("data.csv does not contain the expected columns")
if (nrow(d) == 0) stop("data.csv contains no observations")
if (any(!is.finite(d$length)) || any(!is.finite(d$number_of_cds)) || any(!is.finite(d$completeness))) stop("data.csv contains non-finite numeric values")
if (any(d$length <= 0) || any(d$number_of_cds <= 0)) stop("length and number_of_cds must be positive")
groups <- c("WGS", "MAG", "SAG")
if (any(!d$type %in% groups)) stop("data.csv contains an unexpected genome type")
colors <- c(WGS = "#374955", MAG = "#8C6BB1", SAG = "#247BA0")
x <- log10(d$length)
y <- log10(d$number_of_cds)
model <- lm(y ~ x)
slope <- unname(coef(model)[2])
intercept <- unname(coef(model)[1])
fitted_values <- fitted(model)
residual_values <- resid(model)
r_squared <- summary(model)$r.squared
x_grid <- seq(min(x), max(x), length.out = 500)
prediction <- predict(model, newdata = data.frame(x = x_grid), interval = "confidence", level = 0.95)
pairs <- list(c("WGS", "MAG"), c("WGS", "SAG"), c("MAG", "SAG"))
raw_p <- vapply(pairs, function(pair) {
  wilcox.test(
    residual_values[d$type == pair[1]],
    residual_values[d$type == pair[2]],
    alternative = "two.sided",
    exact = FALSE,
    correct = TRUE
  )$p.value
}, numeric(1))
adjusted_p <- p.adjust(raw_p, method = "holm")
effect_sizes <- vapply(pairs, function(pair) {
  first_values <- residual_values[d$type == pair[1]]
  second_values <- residual_values[d$type == pair[2]]
  combined_ranks <- rank(c(first_values, second_values))
  first_u <- sum(combined_ranks[seq_along(first_values)]) - length(first_values) * (length(first_values) + 1) / 2
  2 * first_u / (length(first_values) * length(second_values)) - 1
}, numeric(1))
residual_span <- diff(range(residual_values))
residual_limits <- range(residual_values) + c(-0.035, 0.035) * residual_span
scientific <- function(value) {
  text <- formatC(value, format = "e", digits = 2)
  text <- sub("e-0", "e−", text, fixed = TRUE)
  text <- sub("e-", "e−", text, fixed = TRUE)
  text
}
alpha_color <- function(color, alpha) grDevices::adjustcolor(color, alpha.f = alpha)
format_log <- function(values) {
  result <- format(values, scientific = FALSE, trim = TRUE, big.mark = ",")
  result
}
device_arguments <- list(filename = output_path, width = 16, height = 12.5, units = "in", res = 360, bg = "#F7F5F1")
if (.Platform$OS.type != "windows" && capabilities("cairo")) device_arguments$type <- "cairo"
do.call(png, device_arguments)
layout(
  matrix(c(1, 1, 2, 3, 3, 4, 5, 5, 6), nrow = 3, byrow = TRUE),
  widths = c(5.5, 5.5, 2.25),
  heights = c(1.15, 5.4, 2.65)
)
par(family = "sans", oma = c(5.4, 1.2, 5.0, 1.2), xaxs = "i", yaxs = "i")
x_breaks <- seq(min(x), max(x), length.out = 30)
y_breaks <- seq(min(y), max(y), length.out = 30)
x_histograms <- lapply(groups, function(name) hist(x[d$type == name], breaks = x_breaks, plot = FALSE))
y_histograms <- lapply(groups, function(name) hist(y[d$type == name], breaks = y_breaks, plot = FALSE))
par(mar = c(0.4, 5.2, 0.8, 0.5))
plot(NA, xlim = range(x), ylim = c(0, max(vapply(x_histograms, function(h) max(h$density), numeric(1))) * 1.08), axes = FALSE, xlab = "", ylab = "")
axis(2, las = 1, cex.axis = 0.75, col.axis = "#4E5A60", col = "#8C969A", tck = -0.02)
mtext("Density", side = 2, line = 3.6, cex = 0.78, col = "#34434B")
abline(h = pretty(c(0, max(vapply(x_histograms, function(h) max(h$density), numeric(1))))), col = "#E3E0DA", lwd = 0.7)
for (i in seq_along(groups)) {
  h <- x_histograms[[i]]
  rect(h$breaks[-length(h$breaks)], 0, h$breaks[-1], h$density, col = alpha_color(colors[groups[i]], 0.10), border = NA)
  lines(rep(h$breaks, each = 2)[-c(1, 2 * length(h$breaks))], rep(h$density, each = 2), col = colors[groups[i]], lwd = 1.5)
}
text(min(x) + 0.01 * diff(range(x)), par("usr")[4] * 0.88, "Marginal distributions", adj = c(0, 0.5), cex = 0.86, font = 2, col = "#34434B")
box(bty = "l", col = "#8C969A")
par(mar = c(0.4, 0.6, 0.8, 0.4))
plot.new()
legend(
  "center",
  legend = c(
    sprintf("WGS  n = %s", format(sum(d$type == "WGS"), big.mark = ",")),
    sprintf("MAG  n = %s", format(sum(d$type == "MAG"), big.mark = ",")),
    sprintf("SAG  n = %s", format(sum(d$type == "SAG"), big.mark = ",")),
    "Global OLS fit"
  ),
  pch = c(16, 16, 16, NA),
  lty = c(NA, NA, NA, 1),
  col = c(colors, "#9C3D3A"),
  pt.cex = 1.1,
  lwd = c(NA, NA, NA, 2.2),
  bty = "n",
  xjust = 0,
  cex = 0.82,
  y.intersp = 1.4
)
par(mar = c(4.8, 5.2, 0.5, 0.5))
plot(
  d$length,
  d$number_of_cds,
  type = "n",
  log = "xy",
  xlab = "Genome length (bp)",
  ylab = "Number of coding sequences (CDS)",
  xaxt = "n",
  yaxt = "n",
  cex.lab = 1.03,
  col.lab = "#25333B"
)
x_ticks <- c(5e5, 1e6, 2e6, 5e6, 1e7)
y_ticks <- c(500, 1000, 2000, 5000, 10000)
axis(1, at = x_ticks, labels = format_log(x_ticks), cex.axis = 0.78, col.axis = "#46545A", col = "#8C969A", tck = -0.02)
axis(2, at = y_ticks, labels = format_log(y_ticks), las = 1, cex.axis = 0.78, col.axis = "#46545A", col = "#8C969A", tck = -0.02)
abline(v = x_ticks, h = y_ticks, col = "#D7D5CF", lwd = 0.7)
polygon(
  c(10^x_grid, rev(10^x_grid)),
  c(10^prediction[, "lwr"], rev(10^prediction[, "upr"])),
  border = NA,
  col = alpha_color("#B44E4A", 0.14)
)
for (name in groups) {
  selected <- d$type == name
  points(d$length[selected], d$number_of_cds[selected], pch = 16, cex = 0.42, col = alpha_color(colors[name], 0.38))
}
lines(10^x_grid, 10^prediction[, "fit"], col = "#9C3D3A", lwd = 2.2)
legend(
  "topleft",
  legend = c(
    "Global descriptive OLS on log10 scale",
    sprintf("slope = %.4f   R² = %.4f   n = %s", slope, r_squared, format(nrow(d), big.mark = ","))
  ),
  bty = "o",
  box.col = "#D8D5CE",
  bg = alpha_color("#FFFFFF", 0.94),
  text.col = "#25333B",
  cex = c(0.82, 0.79),
  text.font = c(2, 1),
  x.intersp = 0.3,
  inset = 0.015
)
text(max(d$length) / 1.03, min(d$number_of_cds) * 1.07, "Shaded band: 95% CI for fitted mean on log10 scale", adj = c(1, 0), cex = 0.70, col = "#5A6469")
box(col = "#8C969A")
par(mar = c(4.8, 0.5, 0.5, 0.8))
max_density <- max(vapply(y_histograms, function(h) max(h$density), numeric(1)))
plot(NA, xlim = c(0, max_density * 1.08), ylim = range(y), axes = FALSE, xlab = "Density", ylab = "")
axis(1, cex.axis = 0.72, col.axis = "#4E5A60", col = "#8C969A", tck = -0.02)
abline(v = pretty(c(0, max_density)), col = "#E3E0DA", lwd = 0.7)
for (i in seq_along(groups)) {
  h <- y_histograms[[i]]
  rect(0, h$breaks[-length(h$breaks)], h$density, h$breaks[-1], col = alpha_color(colors[groups[i]], 0.10), border = NA)
  lines(rep(h$density, each = 2), rep(h$breaks, each = 2)[-c(1, 2 * length(h$breaks))], col = colors[groups[i]], lwd = 1.5)
}
box(bty = "l", col = "#8C969A")
par(mar = c(4.9, 5.2, 2.0, 0.5))
residual_list <- lapply(groups, function(name) residual_values[d$type == name])
box_statistics <- vapply(residual_list, function(values) {
  quartiles <- quantile(values, c(0.25, 0.50, 0.75), type = 7, names = FALSE)
  spread <- quartiles[3] - quartiles[1]
  lower <- min(values[values >= quartiles[1] - 1.5 * spread])
  upper <- max(values[values <= quartiles[3] + 1.5 * spread])
  c(lower, quartiles, upper)
}, numeric(5))
box_object <- list(
  stats = box_statistics,
  n = vapply(residual_list, length, integer(1)),
  conf = matrix(NA_real_, nrow = 2, ncol = length(groups)),
  out = numeric(0),
  group = integer(0),
  names = groups
)
bxp(
  box_object,
  horizontal = TRUE,
  outline = FALSE,
  boxfill = alpha_color(colors, 0.30),
  border = "#66747A",
  medcol = "#17252C",
  medlwd = 1.8,
  whiskcol = "#66747A",
  staplecol = "#66747A",
  boxlwd = 1.0,
  whisklwd = 1.1,
  staplelwd = 1.1,
  xlab = "Residual: observed − fitted log10(CDS)",
  ylim = residual_limits,
  las = 1,
  cex.axis = 0.82,
  cex.lab = 0.92,
  col.lab = "#25333B"
)
set.seed(20260727)
for (i in seq_along(groups)) {
  values <- residual_list[[i]]
  points(values, i + runif(length(values), -0.18, 0.18), pch = 16, cex = 0.32, col = alpha_color(colors[groups[i]], 0.14))
}
abline(v = 0, col = "#9C3D3A", lwd = 1.4, lty = 2)
grid(nx = NULL, ny = NA, col = "#E1DED8", lwd = 0.7)
box(bty = "l", col = "#8C969A")
mtext("Residual distributions by genome type", side = 3, line = 0.7, adj = 0, cex = 1.02, font = 2, col = "#25333B")
par(mar = c(4.9, 0.6, 2.0, 0.4))
plot.new()
median_text <- paste(
  sprintf("%s   median %+.4f", groups, vapply(residual_list, median, numeric(1))),
  collapse = "\n"
)
comparison_text <- paste(
  vapply(
    seq_along(pairs),
    function(i) sprintf(
      "%s–%s   Holm p = %s   δ = %+.3f",
      pairs[[i]][1],
      pairs[[i]][2],
      scientific(adjusted_p[i]),
      effect_sizes[i]
    ),
    character(1)
  ),
  collapse = "\n"
)
text(0, 0.98, "Residual summary", adj = c(0, 1), cex = 0.94, font = 2, col = "#25333B")
text(0, 0.80, median_text, adj = c(0, 1), cex = 0.80, col = "#3E4A50", family = "mono")
text(0, 0.49, "Exploratory pairwise tests", adj = c(0, 1), cex = 0.84, font = 2, col = "#25333B")
text(0, 0.36, comparison_text, adj = c(0, 1), cex = 0.73, col = "#3E4A50", family = "mono")
text(0, 0.02, "Two-sided Mann–Whitney U tests; Holm adjustment.\nδ: rank-biserial effect, first group minus second.", adj = c(0, 0), cex = 0.65, col = "#687277")
mtext("Genome length and coding-sequence abundance", side = 3, outer = TRUE, line = 2.6, adj = 0.04, cex = 1.75, font = 2, col = "#1F2D34")
mtext("A global log–log relationship with group-resolved marginal and residual distributions", side = 3, outer = TRUE, line = 0.9, adj = 0.04, cex = 0.98, col = "#59666C")
mtext(
  "Analysis note. Each row is treated as one independent observation. The global OLS model uses genome length as the sole predictor;",
  side = 1,
  outer = TRUE,
  line = 2.1,
  adj = 0.04,
  cex = 0.72,
  col = "#5D676C"
)
mtext(
  "the completeness column is retained but not modeled. The classical OLS CI assumes homoscedastic residuals; residual tests are exploratory.",
  side = 1,
  outer = TRUE,
  line = 3.3,
  adj = 0.04,
  cex = 0.72,
  col = "#5D676C"
)
invisible(dev.off())
