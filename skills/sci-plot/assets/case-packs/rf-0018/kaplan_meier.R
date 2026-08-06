args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
base_dir <- if (length(file_arg)) dirname(normalizePath(sub("^--file=", "", file_arg[1]), winslash = "/", mustWork = FALSE)) else getwd()
data <- read.csv(file.path(base_dir, "kaplan_meier_data.csv"), stringsAsFactors = FALSE, check.names = FALSE)
output <- file.path(base_dir, "kaplan_meier_r.png")
colors <- c(Male = "#E35D42", Female = "#3E7DBB")
groups <- c("Male", "Female")
kaplan_meier <- function(times, events) {
  unique_times <- sort(unique(times))
  survival <- 1
  result <- matrix(NA_real_, nrow = length(unique_times), ncol = 2)
  for (i in seq_along(unique_times)) {
    time <- unique_times[i]
    at_risk <- sum(times >= time)
    deaths <- sum(times == time & events == 1)
    if (deaths > 0) survival <- survival * (1 - deaths / at_risk)
    result[i, ] <- c(time, survival)
  }
  result
}
survival_at <- function(curve, query) {
  index <- max(which(curve[, 1] <= query), 0)
  if (index == 0) 1 else curve[index, 2]
}
median_survival <- function(curve) {
  reached <- which(curve[, 2] <= 0.5)
  if (length(reached)) curve[reached[1], 1] else NA_real_
}
logrank_p <- function(time_a, event_a, time_b, event_b) {
  event_times <- sort(unique(c(time_a[event_a == 1], time_b[event_b == 1])))
  observed <- 0
  expected <- 0
  variance <- 0
  for (time in event_times) {
    risk_a <- sum(time_a >= time)
    risk_b <- sum(time_b >= time)
    death_a <- sum(time_a == time & event_a == 1)
    death_b <- sum(time_b == time & event_b == 1)
    total_risk <- risk_a + risk_b
    total_death <- death_a + death_b
    observed <- observed + death_b
    expected <- expected + total_death * risk_b / total_risk
    if (total_risk > 1) variance <- variance + risk_a * risk_b * total_death * (total_risk - total_death) / (total_risk^2 * (total_risk - 1))
  }
  z <- (observed - expected) / sqrt(variance)
  2 * pnorm(-abs(z))
}
cox_binary <- function(times, events, group) {
  beta <- 0
  information <- 0
  for (iteration in seq_len(80)) {
    score <- 0
    information <- 0
    for (time in sort(unique(times[events == 1]))) {
      risk <- times >= time
      deaths <- times == time & events == 1
      death_count <- sum(deaths)
      weights <- exp(beta * group[risk])
      probability <- sum(weights * group[risk]) / sum(weights)
      score <- score + sum(group[deaths]) - death_count * probability
      information <- information + death_count * probability * (1 - probability)
    }
    change <- score / information
    beta <- beta + change
    if (abs(change) < 1e-11) break
  }
  standard_error <- sqrt(1 / information)
  c(exp(beta), exp(beta - 1.96 * standard_error), exp(beta + 1.96 * standard_error))
}
curves <- lapply(groups, function(group) {
  frame <- data[data$sex == group, ]
  kaplan_meier(frame$time_months, frame$event_observed)
})
names(curves) <- groups
medians <- vapply(curves, median_survival, numeric(1))
male <- data[data$sex == "Male", ]
female <- data[data$sex == "Female", ]
p_value <- logrank_p(male$time_months, male$event_observed, female$time_months, female$event_observed)
hazard <- cox_binary(data$time_months, data$event_observed, as.numeric(data$sex == "Female"))
png(output, width = 1992, height = 1656, res = 240, bg = "white", type = if (.Platform$OS.type == "windows") "windows" else "cairo")
layout(matrix(1:2, ncol = 1), heights = c(4.6, 1.25))
par(oma = c(4.5, 6.2, 8.5, 2), family = "sans")
par(mar = c(3.8, 4.0, 1.0, 0.8))
plot(c(0, 36), c(0, 1.02), type = "n", axes = FALSE, xlab = "", ylab = "")
abline(h = seq(0, 1, 0.25), col = "#E5E8EB", lwd = 0.8)
for (group in groups) {
  frame <- data[data$sex == group, ]
  curve <- curves[[group]]
  lines(c(0, curve[, 1], 36), c(1, curve[, 2], tail(curve[, 2], 1)), type = "s", col = colors[group], lwd = 2.2)
  censored <- frame$time_months[frame$event_observed == 0]
  points(censored, vapply(censored, function(time) survival_at(curve, time), numeric(1)), pch = 124, cex = 0.80, col = colors[group], lwd = 1.1)
}
abline(h = 0.5, col = "#A8B0B7", lwd = 0.9, lty = 3)
for (group in groups) {
  median <- medians[group]
  segments(median, 0, median, 0.5, col = adjustcolor(colors[group], 0.8), lwd = 1, lty = 3)
  text(median, if (group == "Female") 0.535 else 0.465, paste0(sprintf("%.1f", median), " mo"), adj = c(0.5, if (group == "Female") 0 else 1), cex = 0.69, font = 2, col = colors[group])
}
axis(1, at = seq(0, 36, 6), col = "#27313A", col.axis = "#46515C", tck = -0.018, cex.axis = 0.76)
axis(2, at = seq(0, 1, 0.25), labels = paste0(seq(0, 100, 25), "%"), las = 1, col = "#27313A", col.axis = "#46515C", tck = -0.018, cex.axis = 0.76)
mtext("Time (months)", side = 1, line = 2.7, cex = 0.78, font = 2, col = "#27313A")
mtext("Survival probability", side = 2, line = 3.0, cex = 0.78, font = 2, col = "#27313A")
box(bty = "l", col = "#27313A", lwd = 0.9)
legend("bottomleft", inset = c(0.01, 0.05), legend = paste0(groups, "  (n = ", vapply(groups, function(group) sum(data$sex == group), integer(1)), ")"), col = colors, lwd = 2.2, bty = "n", cex = 0.72)
annotation <- paste0("Female vs Male\nHR ", sprintf("%.2f", hazard[1]), "  (95% CI ", sprintf("%.2f", hazard[2]), "\u2013", sprintf("%.2f", hazard[3]), ")\nLog-rank P = ", sprintf("%.4f", p_value))
rect(23.2, 0.77, 35.3, 1.005, col = "white", border = "#D4D9DE", lwd = 0.9)
text(34.8, 0.98, annotation, adj = c(1, 1), cex = 0.69, col = "#27313A")
par(mar = c(0.4, 4.0, 1.8, 0.8))
plot(c(0, 36), c(-0.2, 2.35), type = "n", axes = FALSE, xlab = "", ylab = "")
risk_times <- seq(0, 36, 6)
text(-1.9, 2.1, "Number at risk", adj = 1, cex = 0.72, font = 2, col = "#27313A", xpd = NA)
for (i in seq_along(groups)) {
  group <- groups[i]
  row <- c(1.35, 0.38)[i]
  frame <- data[data$sex == group, ]
  points(-1.35, row, pch = 16, cex = 0.85, col = colors[group], xpd = NA)
  text(-1.85, row, group, adj = 1, cex = 0.70, col = "#27313A", xpd = NA)
  for (time in risk_times) text(time, row, sum(frame$time_months >= time), cex = 0.70, col = "#27313A")
}
mtext("Kaplan\u2013Meier survival analysis", side = 3, outer = TRUE, line = 5.8, adj = 0, cex = 1.52, font = 2, col = "#17212B")
mtext(paste0("Lung cancer example dataset  \u2022  n = ", nrow(data), "  \u2022  ", sum(data$event_observed), " events"), side = 3, outer = TRUE, line = 3.5, adj = 0, cex = 0.80, col = "#697580")
mtext("Data: ggsurvfit::df_lung, a formatted copy of the survival::lung example dataset", side = 1, outer = TRUE, line = 2.3, adj = 0, cex = 0.64, col = "#7A858F")
dev.off()
