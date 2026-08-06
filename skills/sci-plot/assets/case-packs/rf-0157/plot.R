args <- commandArgs(trailingOnly = FALSE)
file_arg <- sub("^--file=", "", args[grep("^--file=", args)])
root <- if (length(file_arg)) dirname(normalizePath(file_arg)) else getwd()
suppressPackageStartupMessages({library(readxl); library(ggplot2); library(patchwork); library(ragg)})
ink <- "#202528"
teal <- "#287D78"
up <- "#C84A5B"
down <- "#4C78A8"
mix <- "#C6923B"
clinical <- read_excel(file.path(root, "data1.xlsx"))
sets1 <- names(clinical)[-1]
m1 <- as.matrix(clinical[, sets1])
m1[is.na(m1)] <- 0
m1 <- (m1 > 0) * 1
m1 <- m1[rowSums(m1) > 0, , drop = FALSE]
time <- read_excel(file.path(root, "data2.xlsx"))
days <- c("D9", "D7", "D5", "D3", "D1")
down_m <- sapply(days, function(d) as.numeric(time[[paste0(d, ".log2fc")]]) < -.5 & as.numeric(time[[paste0(d, ".padj")]]) < .05)
up_m <- sapply(days, function(d) as.numeric(time[[paste0(d, ".log2fc")]]) > .5 & as.numeric(time[[paste0(d, ".padj")]]) < .05)
m2 <- cbind(down_m, up_m) * 1
colnames(m2) <- c(paste(days, "Sym"), paste(days, "Apo"))
m2 <- m2[rowSums(m2, na.rm = TRUE) > 0, , drop = FALSE]
m2[is.na(m2)] <- 0
make_pair <- function(mat, title, letter, is_time = FALSE) {
  keys <- apply(mat, 1, paste0, collapse = "")
  tab <- sort(table(keys), decreasing = TRUE)
  tab <- head(tab, 16)
  pats <- do.call(rbind, strsplit(names(tab), ""))
  storage.mode(pats) <- "numeric"
  vals <- as.numeric(tab)
  k <- seq_along(vals)
  cls <- if (!is_time) rep("Clinical", length(vals)) else apply(pats, 1, function(x) if (any(x[1:5] > 0) && any(x[6:10] > 0)) "Mixed" else if (any(x[6:10] > 0)) "Apo" else "Sym")
  bars <- data.frame(k, vals, cls)
  p1 <- ggplot(bars, aes(k, vals, fill = cls)) + geom_col(width = .72) + geom_text(aes(label = vals), vjust = -.35, size = 2.1) + scale_fill_manual(values = c("Clinical" = teal, "Apo" = up, "Sym" = down, "Mixed" = mix), guide = "none") + scale_x_continuous(breaks = NULL) + labs(x = NULL, y = "Exact intersection size", title = paste(letter, title), subtitle = paste(format(nrow(mat), big.mark = ","), "records in ≥1 set · top", length(vals), "exact patterns")) + theme_minimal(base_size = 9) + theme(panel.grid.major.x = element_blank(), panel.grid.minor = element_blank(), axis.line.y = element_line(linewidth = .3), plot.title = element_text(face = "bold", size = 12), plot.subtitle = element_text(size = 7, colour = "#656B6E"), plot.background = element_rect(fill = "#FBFAF7", colour = NA), panel.background = element_rect(fill = "#FBFAF7", colour = NA))
  points <- expand.grid(k = k, set = seq_len(ncol(mat)))
  points$active <- as.vector(pats) > 0
  points$colour <- if (!is_time) teal else ifelse(points$set <= 5, down, up)
  seg <- do.call(rbind, lapply(k, function(i) {a <- which(pats[i, ] > 0); if (length(a)) data.frame(k = i, ymin = min(a), ymax = max(a)) else NULL}))
  set_sizes <- colSums(mat)
  labels <- paste0(colnames(mat), "   ", format(set_sizes, big.mark = ","))
  p2 <- ggplot(points, aes(k, set)) + geom_tile(aes(fill = set %% 2 == 0), width = 1, height = 1, alpha = .45) + scale_fill_manual(values = c("TRUE" = "#F0EEE9", "FALSE" = "#FBFAF7"), guide = "none") + geom_point(colour = "#D6D6D2", size = 1) + geom_segment(data = seg, aes(x = k, xend = k, y = ymin, yend = ymax), inherit.aes = FALSE, colour = ink, linewidth = .7) + geom_point(data = points[points$active, ], aes(colour = I(colour)), size = 2) + scale_y_reverse(breaks = seq_len(ncol(mat)), labels = labels) + scale_x_continuous(breaks = NULL) + labs(x = "Set name  ·  total members", y = NULL) + theme_void(base_size = 8) + theme(axis.text.y = element_text(colour = ink, hjust = 1), axis.title.x = element_text(size = 8, margin = margin(t = 8)), plot.background = element_rect(fill = "#FBFAF7", colour = NA))
  p1 / p2 + plot_layout(heights = c(1.05, .8))
}
p <- make_pair(m1, "Clinical comparison intersections", "A", FALSE) | make_pair(m2, "Time-course differential intersections", "B", TRUE)
p <- p + plot_annotation(title = "Intersection architecture across two studies", subtitle = "Exact membership patterns, ranked without collapsing combinations", caption = "Time-course sets require adjusted P < 0.05 and |log₂FC| > 0.5. Sym = negative direction; Apo = positive direction. Clinical sets use supplied binary memberships.", theme = theme(plot.title = element_text(size = 19, face = "bold", colour = ink), plot.subtitle = element_text(size = 9, colour = "#656B6E"), plot.caption = element_text(size = 7, colour = "#656B6E"), plot.background = element_rect(fill = "#FBFAF7", colour = NA)))
agg_png(file.path(root, "plot_r.png"), width = 13.4, height = 7.8, units = "in", res = 360, background = "#FBFAF7")
print(p)
dev.off()
