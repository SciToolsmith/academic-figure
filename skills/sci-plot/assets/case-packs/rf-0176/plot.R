suppressPackageStartupMessages({
  library(ggplot2)
  library(patchwork)
})
args <- commandArgs(trailingOnly = FALSE)
script_arg <- grep("^--file=", args, value = TRUE)
frame_files <- vapply(sys.frames(), function(frame) if (is.null(frame$ofile)) "" else as.character(frame$ofile), character(1))
source_arg <- tail(frame_files[nzchar(frame_files)], 1)
script_path <- if (length(script_arg)) sub("^--file=", "", script_arg[1]) else if (length(source_arg)) source_arg else ""
root <- if (nzchar(script_path)) dirname(normalizePath(script_path, winslash = "/", mustWork = TRUE)) else getwd()
d <- read.csv(file.path(root, "data.csv"), check.names = FALSE, stringsAsFactors = FALSE)
subtypes <- c("CD8 Undefined", "CD8 Tissue resident", "CD8 Stem-like", "CD4 Tissue resident", "CD8 IFN-responsive", "CD4 T regulatory", "CD8 Early activated", "CD8 Proliferative", "CD8 Chemokine producing", "CD8 NK-like")
pal <- setNames(c("#AEB5BA", "#B84A3A", "#2E9D75", "#5264B4", "#9CBC42", "#4A94CA", "#DF6B35", "#D5A62F", "#62B867", "#B86CB2"), subtypes)
stopifnot(nrow(d) == 172386, identical(names(d), c("Cell", "T_subtype", "Timepoint", "UMAP_1", "UMAP_2")), setequal(unique(d$T_subtype), subtypes), !anyNA(d))
d$T_subtype <- factor(d$T_subtype, levels = subtypes)
centers <- aggregate(cbind(UMAP_1, UMAP_2) ~ T_subtype, d, median)
counts <- as.data.frame(table(d$T_subtype), stringsAsFactors = FALSE)
names(counts) <- c("T_subtype", "n")
counts$T_subtype <- factor(counts$T_subtype, levels = counts$T_subtype[order(counts$n)])
counts$label <- sprintf("%s\n(%.1f%%)", format(counts$n, big.mark = ","), 100 * counts$n / nrow(d))
theme_pub <- theme_minimal(base_size = 9) + theme(panel.grid.minor = element_blank(), panel.grid.major = element_line(color = "#DADBD6", linewidth = 0.3), plot.background = element_rect(fill = "#F6F5F1", color = NA), panel.background = element_rect(fill = "#F6F5F1", color = NA), plot.title = element_text(face = "bold", color = "#17242C"))
p1 <- ggplot(d, aes(UMAP_1, UMAP_2, color = T_subtype)) +
  geom_point(size = 0.16, alpha = 0.70, stroke = 0) +
  geom_label(data = centers, aes(label = T_subtype), size = 2.05, fontface = "bold", fill = "#FCFBF8E8", linewidth = 0.22, label.padding = grid::unit(0.09, "lines"), show.legend = FALSE) +
  scale_color_manual(values = pal) +
  coord_equal() +
  labs(x = "UMAP 1", y = "UMAP 2", title = "a   T-cell subtype landscape") +
  theme_pub +
  theme(legend.position = "none", axis.line = element_line(color = "#66747A", linewidth = 0.35))
p2 <- ggplot(counts, aes(n, T_subtype, fill = T_subtype)) +
  geom_col(width = 0.76, color = "white", linewidth = 0.3) +
  geom_text(aes(label = label), hjust = -0.08, size = 2.25, color = "#536168") +
  scale_fill_manual(values = pal) +
  scale_x_continuous(expand = expansion(mult = c(0, 0.22))) +
  labs(x = "Number of cells", y = NULL, title = "b   Supplied subtype counts") +
  theme_pub +
  theme(legend.position = "none", panel.grid.major.y = element_blank(), axis.ticks.y = element_blank(), axis.line.x = element_line(color = "#66747A", linewidth = 0.35), axis.text.y = element_text(size = 7.5))
time_counts <- table(d$Timepoint)
final <- p1 + p2 + plot_layout(widths = c(1.62, 0.82)) + plot_annotation(title = "T-cell states in the extracted single-cell UMAP", subtitle = "All 172,386 cells from the supplied Seurat object are shown; labels mark median subtype positions.", caption = sprintf("Transparent input: Cell, T_subtype, Timepoint and UMAP coordinates extracted from tcells_resubset.rds. Timepoint counts: post = %s; pre = %s. No inferential comparisons are made.", format(time_counts["post"], big.mark = ","), format(time_counts["pre"], big.mark = ",")), theme = theme(plot.background = element_rect(fill = "#F6F5F1", color = NA), plot.title = element_text(size = 18, face = "bold", color = "#17242C"), plot.subtitle = element_text(size = 9.5, color = "#5C696E"), plot.caption = element_text(size = 7.5, color = "#536168", hjust = 0)))
ragg::agg_png(file.path(root, "plot_r.png"), width = 11.2, height = 6.6, units = "in", res = 360, background = "#F6F5F1")
print(final)
dev.off()
