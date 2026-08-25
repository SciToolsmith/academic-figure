#!/usr/bin/env Rscript

fail <- function(msg) { message("ERROR: ", msg); quit(status = 2) }
args <- commandArgs(trailingOnly = TRUE)
opts <- list(input = NULL, `output-prefix` = NULL, title = "Hierarchical composition", dpi = "320")
for (arg in args) {
  if (!startsWith(arg, "--") || !grepl("=", arg, fixed = TRUE)) fail(paste0("arguments must use --name=value: ", arg))
  parts <- strsplit(sub("^--", "", arg), "=", fixed = TRUE)[[1]]
  key <- parts[1]; value <- paste(parts[-1], collapse = "=")
  if (!key %in% names(opts)) fail(paste0("unknown argument --", key))
  opts[[key]] <- value
}
if (is.null(opts$input) || is.null(opts$`output-prefix`)) fail("--input and --output-prefix are required")
dpi <- suppressWarnings(as.integer(opts$dpi)); if (is.na(dpi) || dpi < 72) fail("--dpi must be at least 72")

d <- tryCatch(read.csv(opts$input, stringsAsFactors = FALSE, check.names = FALSE, na.strings = c("")), error = function(e) fail(conditionMessage(e)))
required <- c("node_id", "parent_id", "label", "value")
if (!all(required %in% names(d)) || nrow(d) == 0) fail(paste("CSV must contain", paste(required, collapse = ", ")))
if (nrow(d) > 120) fail("at most 120 nodes are supported")
for (nm in c("node_id", "parent_id", "label")) d[[nm]] <- trimws(ifelse(is.na(d[[nm]]), "", d[[nm]]))
if (any(d$node_id == "") || anyDuplicated(d$node_id)) fail("node_id must be non-empty and unique")
if (any(d$label == "")) fail("label must be non-empty")
if (!"color_group" %in% names(d)) d$color_group <- ""
if (!"order" %in% names(d)) d$order <- seq_len(nrow(d))
d$color_group <- trimws(ifelse(is.na(d$color_group), "", d$color_group))
d$order <- suppressWarnings(as.numeric(d$order)); if (any(!is.finite(d$order))) fail("order must be numeric when supplied")
d$value <- suppressWarnings(as.numeric(d$value))
roots <- which(d$parent_id == ""); if (length(roots) != 1) fail(paste0("expected exactly one root, found ", length(roots)))
root <- d$node_id[roots]
missing_parent <- setdiff(d$parent_id[d$parent_id != ""], d$node_id)
if (length(missing_parent)) fail(paste0("parent_id does not exist: ", missing_parent[1]))

children <- setNames(vector("list", nrow(d)), d$node_id)
for (id in d$node_id[d$node_id != root]) children[[d$parent_id[d$node_id == id]]] <- c(children[[d$parent_id[d$node_id == id]]], id)
for (id in names(children)) if (length(children[[id]])) {
  idx <- match(children[[id]], d$node_id)
  children[[id]] <- children[[id]][order(d$order[idx], idx)]
}
state <- setNames(rep(0L, nrow(d)), d$node_id); depth <- setNames(rep(NA_integer_, nrow(d)), d$node_id)
visit <- function(id, dep) {
  if (state[[id]] == 1L) fail(paste0("cycle detected at node ", id))
  if (state[[id]] == 2L) return(invisible(NULL))
  state[[id]] <<- 1L; depth[[id]] <<- dep
  for (kid in children[[id]]) visit(kid, dep + 1L)
  state[[id]] <<- 2L
}
visit(root, 0L)
if (any(state != 2L)) fail("hierarchy contains nodes that are not reachable from the root")
if (max(depth) > 5) fail("at most 5 visible levels are supported")

total <- setNames(rep(NA_real_, nrow(d)), d$node_id)
aggregate_node <- function(id) {
  idx <- match(id, d$node_id)
  if (length(children[[id]])) {
    if (!is.na(d$value[idx])) fail(paste0("internal node ", id, ": value must be blank to prevent double counting"))
    total[[id]] <<- sum(vapply(children[[id]], aggregate_node, numeric(1)))
  } else {
    if (!is.finite(d$value[idx]) || d$value[idx] <= 0) fail(paste0("leaf node ", id, ": value must be finite and positive"))
    total[[id]] <<- d$value[idx]
  }
  total[[id]]
}
invisible(aggregate_node(root))
if (!length(children[[root]])) fail("root must have at least one child")
for (kid in children[[root]]) {
  idx <- match(kid, d$node_id); grp <- if (d$color_group[idx] == "") d$label[idx] else d$color_group[idx]
  stack <- kid
  while (length(stack)) {
    current <- stack[1]; stack <- stack[-1]
    ci <- match(current, d$node_id); if (d$color_group[ci] == "") d$color_group[ci] <- grp
    stack <- c(stack, children[[current]])
  }
}

sectors <- data.frame(id = character(), start = numeric(), end = numeric(), stringsAsFactors = FALSE)
allocate <- function(id, start, end) {
  cursor <- start
  for (kid in children[[id]]) {
    span <- (end - start) * total[[kid]] / total[[id]]
    sectors <<- rbind(sectors, data.frame(id = kid, start = cursor, end = cursor + span))
    allocate(kid, cursor, cursor + span)
    cursor <- cursor + span
  }
}
allocate(root, pi / 2, pi / 2 + 2 * pi)
palette <- c("#C7775A", "#4F8994", "#8A7EA8", "#789864", "#C19A4B", "#A96976")
groups <- unique(d$color_group[d$color_group != ""]); group_col <- setNames(rep(palette, length.out = length(groups)), groups)
blend <- function(col, amount) {
  rgbv <- col2rgb(col) / 255
  rgb((1 - amount) * rgbv[1] + amount, (1 - amount) * rgbv[2] + amount, (1 - amount) * rgbv[3] + amount)
}
draw <- function(device_fun) {
  device_fun()
  par(bg = "#FBFAF7", mar = c(1.2, 1.2, 4.5, 1.2), family = "sans", xpd = NA)
  plot.new(); plot.window(xlim = c(-1.08, 1.08), ylim = c(-1.08, 1.08), asp = 1)
  max_depth <- max(depth); inner <- 0.24; ring <- 0.72 / max_depth
  for (i in seq_len(nrow(sectors))) {
    id <- sectors$id[i]; dep <- depth[[id]]; idx <- match(id, d$node_id)
    theta <- seq(sectors$start[i], sectors$end[i], length.out = max(8, ceiling((sectors$end[i] - sectors$start[i]) * 80)))
    r0 <- inner + (dep - 1) * ring; r1 <- inner + dep * ring - 0.05 * ring
    x <- c(r0 * cos(theta), rev(r1 * cos(theta))); y <- c(r0 * sin(theta), rev(r1 * sin(theta)))
    polygon(x, y, col = blend(group_col[[d$color_group[idx]]], min(0.38, 0.10 * (dep - 1))), border = "#F6F3EE", lwd = 1.2)
    span <- (sectors$end[i] - sectors$start[i]) * 180 / pi
    if (span >= if (dep == 1) 11 else 16) {
      mid <- (sectors$start[i] + sectors$end[i]) / 2; rr <- inner + (dep - 0.5) * ring
      text(rr * cos(mid), rr * sin(mid), d$label[idx], cex = if (dep == 1) 0.78 else 0.64, col = "#20272D", font = if (dep == 1) 2 else 1)
    }
  }
  symbols(0, 0, circles = inner * 0.92, inches = FALSE, add = TRUE, bg = "white", fg = "#E4E0D9")
  text(0, 0.025, d$label[match(root, d$node_id)], cex = 0.82, font = 2, col = "#20272D")
  text(0, -0.055, paste0("Total ", format(total[[root]], trim = TRUE)), cex = 0.68, col = "#66747B")
  title(main = opts$title, adj = 0, line = 2.1, cex.main = 1.35, col.main = "#20272D", font.main = 2)
  mtext("Sector area is aggregated from positive leaf weights; parent values are derived.", side = 3, adj = 0, line = 0.55, cex = 0.75, col = "#66747B")
  dev.off()
}
prefix <- opts$`output-prefix`; dir.create(dirname(prefix), recursive = TRUE, showWarnings = FALSE)
draw(function() png(paste0(prefix, ".png"), width = 8.6, height = 7.2, units = "in", res = dpi, bg = "#FBFAF7"))
draw(function() pdf(paste0(prefix, ".pdf"), width = 8.6, height = 7.2, bg = "#FBFAF7", useDingbats = FALSE))
leaf_count <- sum(vapply(children, length, integer(1)) == 0)
message(sprintf("Validated %d nodes and %d leaves; derived root total %g; excluded rows: 0.", nrow(d), leaf_count, total[[root]]))
