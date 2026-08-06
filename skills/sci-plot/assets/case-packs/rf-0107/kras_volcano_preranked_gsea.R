script_directory <- function() {
  arguments <- commandArgs(trailingOnly = FALSE)
  file_argument <- grep("^--file=", arguments, value = TRUE)
  if (length(file_argument) > 0) return(dirname(normalizePath(sub("^--file=", "", file_argument[1]), mustWork = TRUE)))
  frames <- sys.frames()
  for (index in rev(seq_along(frames))) {
    source_file <- frames[[index]]$ofile
    if (!is.null(source_file)) return(dirname(normalizePath(source_file, mustWork = TRUE)))
  }
  normalizePath(getwd(), mustWork = TRUE)
}

find_input <- function(base, name) {
  candidates <- c(file.path(base, name), file.path(base, "data", name))
  existing <- candidates[file.exists(candidates)]
  if (length(existing) == 0) stop(paste("Required input not found:", name))
  existing[1]
}

read_gene_set <- function(path, name) {
  lines <- readLines(path, warn = FALSE, encoding = "UTF-8")
  match <- grep(paste0("^", name, "\t"), lines, value = TRUE)
  if (length(match) != 1) stop(paste("Expected exactly one GMT record for", name))
  fields <- strsplit(match, "\t", fixed = TRUE)[[1]]
  unique(fields[-c(1, 2)])
}

enrichment_curve <- function(ranked, members) {
  hits <- ranked$external_gene_name %in% members
  hit_count <- sum(hits)
  if (hit_count == 0 || hit_count == length(hits)) stop("Gene set must map to at least one but not all ranked genes")
  weights <- abs(ranked$logFC)
  hit_total <- sum(weights[hits])
  if (hit_total <= 0) {
    weights <- rep(1, length(weights))
    hit_total <- sum(weights[hits])
  }
  increments <- ifelse(hits, weights / hit_total, -1 / (length(hits) - hit_count))
  running <- cumsum(increments)
  high <- which.max(running)
  low <- which.min(running)
  peak <- if (abs(running[high]) >= abs(running[low])) high else low
  list(running = running, hits = which(hits), score = running[peak], peak = peak, mapped = hit_count)
}

transparent <- function(color, alpha) adjustcolor(color, alpha.f = alpha)

draw_enrichment <- function(result, title, color, panel) {
  ranks <- seq_along(result$running)
  lower <- min(result$running, 0)
  upper <- max(result$running, 0)
  span <- max(upper - lower, 0.2)
  barcode_bottom <- lower - 0.23 * span
  barcode_top <- lower - 0.10 * span
  par(mar = c(4.0, 4.1, 3.0, 0.8), mgp = c(2.35, 0.65, 0), tcl = -0.25)
  plot(ranks, result$running, type = "n", xlim = c(1, length(ranks)), ylim = c(barcode_bottom - 0.04 * span, upper + 0.19 * span), xlab = "Ranked genes: KRAS siRNA vs nonspecific siRNA log2FC", ylab = "Running ES", axes = FALSE, cex.lab = 0.84)
  abline(h = pretty(par("usr")[3:4]), col = "#DDE3E0", lwd = 0.65)
  polygon(c(ranks, rev(ranks)), c(result$running, rep(0, length(ranks))), col = transparent(color, 0.13), border = NA)
  lines(ranks, result$running, col = color, lwd = 2.0)
  abline(h = 0, col = "#6F7B79", lwd = 0.8)
  abline(v = result$peak, col = transparent(color, 0.8), lwd = 0.9, lty = 3)
  segments(result$hits, barcode_bottom, result$hits, barcode_top, col = transparent(color, 0.75), lwd = 0.45)
  axis(1, cex.axis = 0.77, col = "#283333", col.axis = "#344242")
  axis(2, las = 1, cex.axis = 0.77, col = "#283333", col.axis = "#344242")
  box(bty = "l", col = "#283333")
  mtext(panel, side = 3, adj = -0.03, line = 1.15, cex = 1.22, font = 2)
  mtext(title, side = 3, adj = 0, line = 0.35, cex = 0.94, font = 2, col = "#172322")
  text(par("usr")[2], par("usr")[4] - 0.035 * diff(par("usr")[3:4]), sprintf("ES = %+.3f\n%d/200 genes mapped", result$score, result$mapped), adj = c(1, 1), cex = 0.78, col = color)
  text(par("usr")[1] + 0.01 * diff(par("usr")[1:2]), barcode_top + 0.035 * span, "Gene-set hits", adj = c(0, 0), cex = 0.70, col = "#62706E")
}

base <- script_directory()
data_path <- find_input(base, "science.adk0775_data_s1.csv")
gmt_path <- find_input(base, "h.all.v2023.2.Hs.symbols.gmt")
output_path <- file.path(base, "kras_volcano_preranked_gsea_r.png")
data <- read.csv(data_path, stringsAsFactors = FALSE, check.names = FALSE)
required <- c("external_gene_name", "logFC", "FDR")
if (!all(required %in% names(data))) stop(paste("CSV must contain columns:", paste(required, collapse = ", ")))
data$logFC <- suppressWarnings(as.numeric(data$logFC))
data$FDR <- suppressWarnings(as.numeric(data$FDR))
plot_data <- data[is.finite(data$logFC) & is.finite(data$FDR) & data$FDR > 0, , drop = FALSE]
symbols <- trimws(as.character(plot_data$external_gene_name))
valid <- plot_data[!is.na(symbols) & nzchar(symbols), , drop = FALSE]
valid$external_gene_name <- trimws(as.character(valid$external_gene_name))
valid$.source_order <- seq_len(nrow(valid))
valid$.abs_logFC <- abs(valid$logFC)
collapse_order <- order(valid$external_gene_name, -valid$.abs_logFC, valid$FDR, valid$.source_order)
collapsed <- valid[collapse_order, , drop = FALSE]
collapsed <- collapsed[!duplicated(collapsed$external_gene_name), , drop = FALSE]
ranked <- collapsed[order(-collapsed$logFC, collapsed$.source_order), , drop = FALSE]
up_name <- "HALLMARK_KRAS_SIGNALING_UP"
dn_name <- "HALLMARK_KRAS_SIGNALING_DN"
up_set <- read_gene_set(gmt_path, up_name)
dn_set <- read_gene_set(gmt_path, dn_name)
up_result <- enrichment_curve(ranked, up_set)
dn_result <- enrichment_curve(ranked, dn_set)
plot_data$neglog10_fdr <- -log10(plot_data$FDR)
symbols <- ifelse(is.na(plot_data$external_gene_name), "", trimws(as.character(plot_data$external_gene_name)))
up_sig <- plot_data$FDR < 0.05 & plot_data$logFC > 0.5
down_sig <- plot_data$FDR < 0.05 & plot_data$logFC < -0.5
up_members <- symbols %in% up_set
dn_members <- symbols %in% dn_set
special <- symbols %in% c("KRAS", "FOSL1", "MYC")
x_extent <- ceiling(max(abs(plot_data$logFC)) * 2) / 2
y_extent <- max(6.5, max(plot_data$neglog10_fdr) + 0.45)
threshold_y <- -log10(0.05)
png(output_path, width = 4800, height = 3440, res = 400, bg = "#F7F6F2", type = if (capabilities("cairo")) "cairo" else getOption("bitmapType"))
layout(matrix(c(1, 2, 1, 3, 4, 0), nrow = 3, byrow = TRUE), widths = c(1.58, 1), heights = c(1, 1, 0.18))
par(oma = c(4.5, 0.5, 3.4, 0.5))
par(family = "sans", fg = "#283333", col.axis = "#344242", col.lab = "#172322", lend = "round")
par(mar = c(5.0, 4.8, 4.8, 1.0), mgp = c(2.7, 0.72, 0), tcl = -0.25)
plot(plot_data$logFC, plot_data$neglog10_fdr, type = "n", xlim = c(-x_extent, x_extent), ylim = c(0, y_extent), xlab = "KRAS siRNA vs nonspecific siRNA log2FC", ylab = "Significance (-log10 FDR)", axes = FALSE, cex.lab = 0.98)
rect(-x_extent, threshold_y, -0.5, y_extent, col = transparent("#426EAA", 0.055), border = NA)
rect(0.5, threshold_y, x_extent, y_extent, col = transparent("#D65A4A", 0.055), border = NA)
abline(h = pretty(c(0, y_extent)), col = "#DDE3E0", lwd = 0.65)
points(plot_data$logFC, plot_data$neglog10_fdr, pch = 16, cex = 0.24, col = transparent("#B8BFBC", 0.30))
points(plot_data$logFC[down_sig], plot_data$neglog10_fdr[down_sig], pch = 16, cex = 0.28, col = transparent("#426EAA", 0.40))
points(plot_data$logFC[up_sig], plot_data$neglog10_fdr[up_sig], pch = 16, cex = 0.28, col = transparent("#D65A4A", 0.40))
points(plot_data$logFC[up_members], plot_data$neglog10_fdr[up_members], pch = 21, cex = 0.58, bg = transparent("#E7A621", 0.88), col = "#172322", lwd = 0.45)
points(plot_data$logFC[dn_members], plot_data$neglog10_fdr[dn_members], pch = 21, cex = 0.55, bg = transparent("#8EA4C9", 0.86), col = "#172322", lwd = 0.45)
points(plot_data$logFC[special], plot_data$neglog10_fdr[special], pch = 21, cex = 0.86, bg = "#46C8C8", col = "#142020", lwd = 0.75)
abline(v = c(-0.5, 0.5), col = c("#426EAA", "#D65A4A"), lwd = 0.9, lty = 3)
abline(h = threshold_y, col = "#596664", lwd = 0.9, lty = 3)
abline(v = 0, col = "#899390", lwd = 0.75)
axis(1, cex.axis = 0.84, col = "#283333", col.axis = "#344242")
axis(2, las = 1, cex.axis = 0.84, col = "#283333", col.axis = "#344242")
box(bty = "l", col = "#283333")
mtext("A", side = 3, adj = -0.04, line = 2.15, cex = 1.22, font = 2)
mtext("KRAS suppression reshapes the PDAC transcriptome", side = 3, adj = 0, line = 1.35, cex = 1.14, font = 2, col = "#172322")
text(-x_extent + 0.18, y_extent - 0.2, sprintf("%s KRAS-dependent genes", format(sum(down_sig), big.mark = ",")), adj = c(0, 1), cex = 0.81, font = 2, col = "#426EAA")
text(x_extent - 0.18, y_extent - 0.2, sprintf("%s KRAS-inhibited genes", format(sum(up_sig), big.mark = ",")), adj = c(1, 1), cex = 0.81, font = 2, col = "#D65A4A")
text(x_extent - 0.1, threshold_y + 0.08, "FDR = 0.05", adj = c(1, 0), cex = 0.73, col = "#596664")
label_offsets <- list(KRAS = c(0.34, 0.10), FOSL1 = c(0.34, 0.18), MYC = c(0.34, 0.15))
for (gene in names(label_offsets)) {
  index <- which(symbols == gene)[1]
  if (!is.na(index)) {
    x <- plot_data$logFC[index]
    y <- plot_data$neglog10_fdr[index]
    delta <- label_offsets[[gene]]
    segments(x, y, x + delta[1] * 0.82, y + delta[2] * 0.82, col = "#6D7977", lwd = 0.7)
    text(x + delta[1], y + delta[2], gene, adj = c(0, 0.5), cex = 0.74, font = 2, col = "#172322")
  }
}
draw_enrichment(up_result, "HALLMARK KRAS SIGNALING UP", "#D99716", "B")
draw_enrichment(dn_result, "HALLMARK KRAS SIGNALING DN", "#647FAE", "C")
par(mar = c(0, 4.8, 0, 1.0), xpd = NA)
plot.new()
legend("center", bty = "n", ncol = 2, pch = c(16, 16, 21, 21), pt.bg = c("#426EAA", "#D65A4A", "#E7A621", "#8EA4C9"), col = c("#426EAA", "#D65A4A", "#172322", "#172322"), pt.cex = c(0.9, 0.9, 1.0, 1.0), cex = 0.66, legend = c("FDR < .05, log2FC < -.5", "FDR < .05, log2FC > .5", "HALLMARK KRAS UP", "HALLMARK KRAS DN"))
mtext("Differential expression and Hallmark KRAS preranked enrichment", side = 3, outer = TRUE, adj = 0.03, line = 1.0, cex = 1.38, font = 2, col = "#13201F")
mtext("Weighted preranked ES (|log2FC|^1); duplicates: max |log2FC|, then min FDR, then source order. MSigDB Hallmark v2023.2.", side = 1, outer = TRUE, adj = 0.03, line = 2.35, cex = 0.71, col = "#485654")
mtext("Only gene-level summaries are supplied: phenotype-permutation P is not estimable; this ES-only analysis reports neither permutation P nor NES.", side = 1, outer = TRUE, adj = 0.03, line = 1.15, cex = 0.71, col = "#485654")
dev.off()
cat(sprintf("Rows: %s; ranked unique symbols: %s\n", format(nrow(data), big.mark = ","), format(nrow(ranked), big.mark = ",")))
cat(sprintf("DEG threshold counts: down=%s, up=%s\n", format(sum(down_sig), big.mark = ","), format(sum(up_sig), big.mark = ",")))
cat(sprintf("%s: ES=%.10f, mapped=%d/200\n", up_name, up_result$score, up_result$mapped))
cat(sprintf("%s: ES=%.10f, mapped=%d/200\n", dn_name, dn_result$score, dn_result$mapped))
cat(paste0(output_path, "\n"))
