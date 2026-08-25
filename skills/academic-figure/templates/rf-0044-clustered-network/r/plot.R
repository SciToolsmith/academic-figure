#!/usr/bin/env Rscript

fail <- function(msg) { message("ERROR: ", msg); quit(status = 2) }
args <- commandArgs(trailingOnly = TRUE)
opts <- list(nodes = NULL, edges = NULL, `output-prefix` = NULL, title = "Supplied network structure", dpi = "320")
for (arg in args) {
  if (!startsWith(arg, "--") || !grepl("=", arg, fixed = TRUE)) fail(paste0("arguments must use --name=value: ", arg))
  p <- strsplit(sub("^--", "", arg), "=", fixed = TRUE)[[1]]; key <- p[1]; value <- paste(p[-1], collapse = "=")
  if (!key %in% names(opts)) fail(paste0("unknown argument --", key)); opts[[key]] <- value
}
if (any(vapply(opts[c("nodes", "edges", "output-prefix")], is.null, logical(1)))) fail("--nodes, --edges, and --output-prefix are required")
dpi <- suppressWarnings(as.integer(opts$dpi)); if (is.na(dpi) || dpi < 72) fail("--dpi must be at least 72")
n <- tryCatch(read.csv(opts$nodes, stringsAsFactors = FALSE, check.names = FALSE), error = function(e) fail(conditionMessage(e)))
e <- tryCatch(read.csv(opts$edges, stringsAsFactors = FALSE, check.names = FALSE), error = function(e) fail(conditionMessage(e)))
nreq <- c("node_id", "label", "x", "y", "cluster"); ereq <- c("source", "target")
if (!all(nreq %in% names(n)) || nrow(n) == 0) fail(paste("nodes CSV must contain", paste(nreq, collapse = ", ")))
if (!all(ereq %in% names(e)) || nrow(e) == 0) fail(paste("edges CSV must contain", paste(ereq, collapse = ", ")))
if (nrow(n) < 5 || nrow(n) > 120) fail("nodes CSV must contain 5–120 rows")
if (nrow(e) > 500) fail("at most 500 edges are supported")
for (nm in c("node_id", "label", "cluster")) n[[nm]] <- trimws(as.character(n[[nm]]))
if (any(n$node_id == "") || anyDuplicated(n$node_id) || any(n$label == "") || any(n$cluster == "")) fail("node_id must be unique and label/cluster non-empty")
n$x <- suppressWarnings(as.numeric(n$x)); n$y <- suppressWarnings(as.numeric(n$y))
if (!"size" %in% names(n)) n$size <- 1; n$size <- suppressWarnings(as.numeric(n$size))
if (any(!is.finite(n$x)) || any(!is.finite(n$y)) || any(!is.finite(n$size)) || any(n$size <= 0)) fail("coordinates must be finite and size positive")
if (!"show_label" %in% names(n)) n$show_label <- FALSE
raw_show <- tolower(trimws(as.character(n$show_label)))
if (any(!raw_show %in% c("true", "false", "1", "0", "yes", "no", ""))) fail("show_label must be true or false")
n$show_label <- raw_show %in% c("true", "1", "yes")
clusters <- unique(n$cluster); if (length(clusters) > 12) fail("at most 12 clusters are supported")
for (nm in c("source", "target")) e[[nm]] <- trimws(as.character(e[[nm]]))
if (any(!e$source %in% n$node_id) || any(!e$target %in% n$node_id) || any(e$source == e$target)) fail("edge endpoints must reference two different known nodes")
edge_key <- apply(cbind(e$source, e$target), 1, function(z) paste(sort(z), collapse = "\r"))
if (anyDuplicated(edge_key)) fail("duplicate undirected edges are not allowed")
if (!"weight" %in% names(e)) e$weight <- 1; e$weight <- suppressWarnings(as.numeric(e$weight))
if (any(!is.finite(e$weight)) || any(e$weight <= 0)) fail("edge weight must be finite and positive")
if (!"edge_group" %in% names(e)) e$edge_group <- "edge"; e$edge_group <- trimws(as.character(e$edge_group)); e$edge_group[e$edge_group == ""] <- "edge"
groups <- unique(e$edge_group)
scale_to <- function(x, lo, hi) if (max(x) == min(x)) rep((lo + hi) / 2, length(x)) else lo + (x - min(x)) / (max(x) - min(x)) * (hi - lo)
palette <- c("#C8755C", "#4E8995", "#887DA5", "#789566", "#BE974A", "#A96775")
cols <- setNames(rep(palette, length.out = length(clusters)), clusters)
line_types <- setNames(seq_along(groups), groups); line_types[line_types > 2] <- 3
node_cex <- scale_to(n$size, 1.5, 2.8); edge_lwd <- scale_to(e$weight, 0.8, 2.3)
draw <- function(device_fun) {
  device_fun(); par(bg = "#FBFAF7", mar = c(1.2, 1.2, 5, 1.2), family = "sans", xpd = NA)
  xr <- range(n$x); yr <- range(n$y); padx <- max(diff(xr), 1) * 0.18; pady <- max(diff(yr), 1) * 0.18
  plot.new(); plot.window(xlim = xr + c(-padx, padx), ylim = yr + c(-pady, pady), asp = 1)
  for (i in seq_len(nrow(e))) {
    a <- match(e$source[i], n$node_id); b <- match(e$target[i], n$node_id)
    segments(n$x[a], n$y[a], n$x[b], n$y[b], col = adjustcolor("#91A0A5", alpha.f = 0.5), lwd = edge_lwd[i], lty = line_types[[e$edge_group[i]]])
  }
  points(n$x, n$y, pch = 21, bg = cols[n$cluster], col = "white", lwd = 1.4, cex = node_cex)
  if (any(n$show_label)) text(n$x[n$show_label], n$y[n$show_label], n$label[n$show_label], pos = 3, offset = 0.9, cex = 0.76, font = 2, col = "#20272D")
  legend("topleft", legend = clusters, pch = 21, pt.bg = cols[clusters], pt.cex = 1.15, col = "white", bty = "n", horiz = length(clusters) <= 4, cex = 0.76, inset = 0.01)
  title(main = opts$title, adj = 0, line = 2.25, cex.main = 1.35, col.main = "#20272D", font.main = 2)
  mtext("Coordinates, clusters, labels and edge weights are supplied; no network inference is performed.", side = 3, adj = 0, line = 0.55, cex = 0.74, col = "#68767D")
  dev.off()
}
prefix <- opts$`output-prefix`; dir.create(dirname(prefix), recursive = TRUE, showWarnings = FALSE)
draw(function() png(paste0(prefix, ".png"), width = 9.2, height = 7, units = "in", res = dpi, bg = "#FBFAF7"))
draw(function() pdf(paste0(prefix, ".pdf"), width = 9.2, height = 7, bg = "#FBFAF7", useDingbats = FALSE))
message(sprintf("Validated %d nodes, %d unique undirected edges, and %d supplied clusters; excluded rows: 0.", nrow(n), nrow(e), length(clusters)))
