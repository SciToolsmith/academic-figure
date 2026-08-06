args <- commandArgs(trailingOnly = FALSE)
fa <- grep("^--file=", args, value = TRUE)
base_dir <- if (length(fa)) dirname(normalizePath(sub("^--file=", "", fa[1]), winslash = "/", mustWork = FALSE)) else getwd()
cluster_cols <- c("#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD", "#8C564B", "#E377C2", "#7F7F7F", "#BCBD22")
heat_cols <- colorRampPalette(c("#164E8A", "#F7F5F2", "#B3202A"))(201)
asg <- read.csv(file.path(base_dir, "gene_cluster_assignments.csv"), stringsAsFactors = FALSE)
enr <- read.csv(file.path(base_dir, "enrichment_annotations.csv"), stringsAsFactors = FALSE)
zrow <- function(x) {
  m <- rowMeans(x)
  s <- apply(x, 1, sd)
  s[!is.finite(s) | s == 0] <- 1
  (x - m) / s
}
stable_order <- function(x) {
  if (nrow(x) < 3) return(seq_len(nrow(x)))
  y <- sweep(x, 2, colMeans(x))
  v <- svd(y, nu = 0, nv = 1)$v[, 1]
  f <- which(abs(v) > 1e-12)[1]
  if (length(f) && v[f] < 0) v <- -v
  order(as.vector(y %*% v), method = "radix")
}
draw_profile <- function(values, blocks, samples) {
  n <- nrow(values)
  plot.new(); plot.window(c(-.38, 1.05), c(n, 0), xaxs = "i", yaxs = "i")
  title("Cluster profile", line = .6, cex.main = .83, font.main = 2, col.main = "#26323D")
  xx <- seq(.04, .97, length.out = ncol(values))
  for (k in seq_len(nrow(blocks))) {
    b <- blocks[k, ]; cl <- b$cluster; st <- b$start; en <- b$end; h <- en - st
    rect(-.06, st, 1.02, en, col = if (k %% 2) "#F6F7F8" else "white", border = "#D8DDE2", lwd = .7)
    med <- apply(values[(st + 1):en, , drop = FALSE], 2, median)
    amp <- max(abs(med), .5)
    yy <- (st + en) / 2 - med / amp * h * .28
    lines(xx, yy, col = "white", lwd = 4)
    lines(xx, yy, col = cluster_cols[cl], lwd = 2.2)
    text(-.34, (st + en) / 2, paste0("C", cl), adj = 0, font = 2, cex = .76, col = "#26323D")
    text(-.02, st + h * .12, paste0("n = ", h), adj = c(0, 1), cex = .48, col = "#5E6A74")
  }
}
draw_genes <- function(genes, blocks, reps) {
  n <- length(genes)
  plot.new(); plot.window(c(0, 1), c(n, 0), xaxs = "i", yaxs = "i")
  title("Representative genes", line = .6, cex.main = .83, font.main = 2, col.main = "#26323D")
  for (k in seq_len(nrow(blocks))) {
    b <- blocks[k, ]; wanted <- reps[[as.character(b$cluster)]]
    wanted <- wanted[wanted %in% genes[(b$start + 1):b$end]]
    if (!length(wanted)) next
    targets <- seq(b$start + (b$end-b$start)*.16, b$end-(b$end-b$start)*.16, length.out = length(wanted))
    actual <- match(wanted, genes) - .5
    for (j in seq_along(wanted)) {
      segments(.87, targets[j], 1, actual[j], col = "#8B949C", lwd = .65)
      text(.83, targets[j], wanted[j], adj = 1, cex = .53, font = 3, col = "#26323D")
    }
  }
}
draw_heat <- function(values, samples, sample_cols, blocks) {
  n <- nrow(values); p <- ncol(values)
  plot.new(); plot.window(c(.5, p + .5), c(n, 0), xaxs = "i", yaxs = "i")
  z <- values
  z[z < -2] <- -2
  z[z > 2] <- 2
  image(x = seq_len(p), y = seq(.5, n - .5), z = t(z[n:1, , drop = FALSE]), col = heat_cols, zlim = c(-2, 2), add = TRUE, useRaster = TRUE)
  for (j in seq_len(p)) rect(j-.5, -n*.024, j+.5, -n*.008, col = sample_cols[j], border = "white", xpd = NA)
  for (j in seq_len(p)) text(j, -n*.035, samples[j], srt = 40, adj = 0, cex = .54, xpd = NA, col = "#34414A")
  for (y in blocks$end) segments(.5, y, p+.5, y, col = "#D4D9DD", lwd = .6)
  box(col = "#26323D", lwd = .8)
}
draw_stripe <- function(blocks, n) {
  plot.new(); plot.window(c(0,1), c(n,0), xaxs="i", yaxs="i")
  for (k in seq_len(nrow(blocks))) {
    b <- blocks[k, ]; rect(0,b$start,1,b$end,col=cluster_cols[b$cluster],border="white")
    text(.5,(b$start+b$end)/2,paste0("C",b$cluster,"  n=",b$end-b$start),srt=90,col="white",font=2,cex=.42)
  }
}
draw_terms <- function(blocks, enrichment, n, dataset) {
  plot.new(); plot.window(c(0,1), c(n,0), xaxs="i", yaxs="i")
  title("Functional enrichment", line=.6, cex.main=.83, font.main=2, col.main="#26323D")
  for (k in seq_len(nrow(blocks))) {
    b <- blocks[k, ]; rect(0,b$start,1,b$end,col=if(k%%2)"#F7F7F6" else "#FBFBFA",border="#AEB6BC",lwd=.65)
    q <- enrichment[enrichment$cluster == b$cluster, ]
    q <- q[order(q$rank), ]
    if (dataset == "pbmc" && b$end-b$start <= 5) q <- head(q,3)
    yy <- seq(b$start+(b$end-b$start)*.14,b$end-(b$end-b$start)*.14,length.out=nrow(q))
    for (j in seq_len(nrow(q))) text(.018,yy[j],q$term[j],adj=0,cex=if(dataset=="pbmc").47 else .51,font=if(j==1)2 else 1,col=cluster_cols[b$cluster])
  }
}
draw_bars <- function(blocks, enrichment, n, dataset) {
  plot.new(); plot.window(c(0,1.04), c(n,0), xaxs="i", yaxs="i")
  title("Relative enrichment", line=.6, cex.main=.83, font.main=2, col.main="#26323D")
  for (k in seq_len(nrow(blocks))) {
    b <- blocks[k, ]; q <- enrichment[enrichment$cluster == b$cluster, ]; q <- q[order(q$rank), ]
    if (dataset == "pbmc" && b$end-b$start <= 5) q <- head(q,3)
    yy <- seq(b$start+(b$end-b$start)*.14,b$end-(b$end-b$start)*.14,length.out=nrow(q))
    hh <- max(n*.0015,(b$end-b$start)/(max(1,nrow(q))*2.8))
    for (j in seq_len(nrow(q))) { rect(0,yy[j]-hh/2,1,yy[j]+hh/2,col="#EEF0F2",border=NA); rect(0,yy[j]-hh/2,q$relative_score[j],yy[j]+hh/2,col=cluster_cols[b$cluster],border=NA) }
  }
}
render <- function(dataset, genes, samples, values, clusters, scores, cluster_order, sample_cols, reps, title_text, subtitle_text, output) {
  ord <- integer(); starts <- numeric(); ends <- numeric()
  for (cl in cluster_order) {
    ii <- which(clusters == cl)
    if (dataset == "embryonic") ii <- ii[stable_order(values[ii, , drop=FALSE])]
    starts <- c(starts,length(ord)); ord <- c(ord,ii); ends <- c(ends,length(ord))
  }
  values <- values[ord,,drop=FALSE]; genes <- genes[ord]; clusters <- clusters[ord]
  blocks <- data.frame(cluster=cluster_order,start=starts,end=ends)
  enrichment <- enr[enr$dataset == dataset,]
  png(file.path(base_dir,output),width=4400,height=2500,res=220,bg="white")
  par(oma=c(3.1,3.2,7.5,2),mar=c(.5,.2,2.6,.2),family="sans")
  layout(matrix(1:6,1,6),widths=c(1.7,1.55,1.6,.22,5.6,1.55))
  draw_profile(values,blocks,samples)
  draw_genes(genes,blocks,reps)
  draw_heat(values,samples,sample_cols,blocks)
  draw_stripe(blocks,nrow(values))
  draw_terms(blocks,enrichment,nrow(values),dataset)
  draw_bars(blocks,enrichment,nrow(values),dataset)
  mtext(title_text,outer=TRUE,side=3,line=4.6,adj=0,font=2,cex=1.7,col="#202A33")
  mtext(subtitle_text,outer=TRUE,side=3,line=2.8,adj=0,cex=.9,col="#687680")
  mtext("Rows are genes; colors show row-wise z-scores. Profiles summarize median expression within each cluster.",outer=TRUE,side=1,line=1.2,adj=0,cex=.72,col="#687680")
  dev.off()
}
emb <- read.csv(file.path(base_dir,"embryonic_expression.csv"),check.names=FALSE)
ea <- asg[asg$dataset=="embryonic",]
ix <- match(emb$gene,ea$gene)
stopifnot(nrow(emb)==3767,all(!is.na(ix)))
ereps <- list(`1`=c("Apeh","Ckb","Nit2"),`2`=c("Abcf1","Top2a","Ipo5"),`3`=c("Fam192a","Ndufb11"),`4`=c("Fem1b","Thrap3","Peci","Psmd11"),`5`=c("Tbc1d23","Dusp7","Cdk5rap2"),`6`=c("Rab27a","Dtx2","Acad10","AU015836"),`7`=c("Morc3","Yipf3","Luc7l2","Timm8a1"),`8`=c("Tbcc","Atp11c","Tm7sf2","LOC100503972"))
render("embryonic",emb$gene,c("Zygote","2-cell","4-cell","8-cell","Morula","Blastocyst"),zrow(as.matrix(emb[,-1])),ea$cluster[ix],ea$score[ix],c(6,1,8,5,3,7,4,2),c("#F1D94F","#7776DE","#D67812","#75DCA2","#F27418","#1768B5"),ereps,"Embryonic expression programs","Fuzzy clustering of 3,767 genes across six stages of preimplantation development","embryonic_gene_cluster_heatmap_r.png")
pb <- read.csv(file.path(base_dir,"pbmc_normalized_expression.csv"),check.names=FALSE)
meta <- read.csv(file.path(base_dir,"pbmc_cell_metadata.csv"),stringsAsFactors=FALSE)
pa <- asg[asg$dataset=="pbmc",]
levels_pb <- c("Naive CD4 T","Memory CD4 T","CD14+ Mono","B","CD8 T","FCGR3A+ Mono","NK","DC","Platelet")
cell_type <- meta$cell_type[match(names(pb)[-1],meta$cell)]
lin <- expm1(as.matrix(pb[,-1]))
avg <- sapply(levels_pb,function(z) rowMeans(lin[,cell_type==z,drop=FALSE]))
sel <- match(pa$gene,pb$gene)
preps <- list(`1`=c("RPS23","FUS","RPSA"),`2`=c("GIMAP7","CRIP1","PRDX2"),`3`=c("GPX1","JUND","LYL1","VAMP5"),`4`=c("PKIG","POLD4","SELL"),`5`=c("SH2D1A","BIN2","CELF2"),`6`=c("MBD2","CXCL16","TMEM127","RAB31"),`7`=c("C19orf10","MAD2L2","TMBIM4.1","CARD8"),`8`=c("TRAPPC9","AMPD2","ENHO","PRR14L"),`9`=c("CD9","RBBP6","GNG11"))
render("pbmc",pa$gene,levels_pb,zrow(avg[sel,,drop=FALSE]),pa$cluster,pa$score,1:9,c("#7A9A01","#4DE88D","#62E679","#3A12C6","#84AAA0","#D000B9","#168CA8","#71DEDC","#58EFB5"),preps,"Cell-type marker programs","Differential expression and functional enrichment across nine PBMC lineages","pbmc_gene_cluster_heatmap_r.png")
