args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
base_dir <- if (length(file_arg)) dirname(normalizePath(sub("^--file=", "", file_arg[1]), winslash = "/", mustWork = FALSE)) else getwd()
if (!requireNamespace("readxl", quietly = TRUE)) stop("Package 'readxl' is required")
d <- as.data.frame(readxl::read_excel(file.path(base_dir, "swimmer_data.xlsx"), sheet = "Sheet2"), stringsAsFactors = FALSE)
response_col <- "Comfirmed best overall response"
d <- d[!is.na(d[[response_col]]) & toupper(as.character(d[[response_col]])) != "NA", ]
time_cols <- c("first_partial_response","first_stable_disease","first_progressive_disease","last_follow_up")
for (nm in time_cols) {
  d[[nm]] <- suppressWarnings(as.numeric(d[[nm]]))
  d[[nm]][d[[nm]]<0] <- NA
  d[[nm]] <- d[[nm]]/30
}
d$death_event <- !is.na(d$death)
d$follow_up_event <- !is.na(d[["follow up"]])
response_names <- c(PR="Partial response",SD="Stable disease",PD="Progressive disease")
d$response <- unname(response_names[toupper(as.character(d[[response_col]]))])
d <- d[order(d$last_follow_up), ]
response_cols <- c("Partial response"="#E4A19C","Stable disease"="#9FAFD3","Progressive disease"="#8FBEA6")
png(file.path(base_dir, "swimmer_plot_r.png"), width = 3960, height = 3060, res = 300, bg = "white", type = if (.Platform$OS.type == "windows") "windows" else "cairo")
par(mar=c(5.6,5.2,6.6,15.5),family="sans",xaxs="i",yaxs="i")
y <- seq_len(nrow(d))
plot(NA,xlim=c(0,46),ylim=c(.3,nrow(d)+.7),axes=FALSE,xlab="",ylab="")
abline(v=seq(0,45,5),col="#DEE3E6",lwd=.7)
rect(0,y-.29,d$last_follow_up,y+.29,col=response_cols[d$response],border="white",lwd=.7)
event <- list(c("first_partial_response",17,"#B80C46","#B80C46",1.2),c("first_stable_disease",23,"white","#E6373E",1.2),c("first_progressive_disease",25,"#148554","#148554",1.2))
for (e in event) {
  k <- is.finite(d[[e[[1]]]])
  points(d[[e[[1]]]][k],y[k],pch=as.numeric(e[[2]]),bg=e[[3]],col=e[[4]],cex=1.0,lwd=as.numeric(e[[5]]))
}
points(d$last_follow_up[d$death_event]+.18,y[d$death_event],pch=22,bg="#04A2C4",col="white",cex=.92)
points(d$last_follow_up[d$follow_up_event]+.18,y[d$follow_up_event],pch=23,bg="#70B83F",col="white",cex=.92)
axis(1,at=seq(0,45,5),cex.axis=.78,col.axis="#53616A")
axis(2,at=y,labels=sprintf("P%02d",as.integer(d$id)),las=1,tick=FALSE,cex.axis=.68,col.axis="#53616A")
box(bty="l",col="#27323A")
mtext("Time since treatment initiation (months)",side=1,line=3.2,cex=1.0,font=2,col="#27323A")
mtext("Patient",side=2,line=3.4,cex=1.0,font=2,col="#27323A")
mtext("Treatment response over time",side=3,line=4.2,adj=0,cex=1.52,font=2,col="#202A35")
mtext(paste0("Duration and first documented response events for ",nrow(d)," patients"),side=3,line=2.5,adj=0,cex=.86,col="#64737B")
par(xpd=NA)
legend(47.4,nrow(d)+.2,legend=c("First partial response","First stable disease","First progressive disease","Death","Follow-up"),pch=c(17,23,25,22,23),pt.bg=c("#B80C46","white","#148554","#04A2C4","#70B83F"),col=c("#B80C46","#E6373E","#148554","white","white"),title="Clinical events",bty="n",cex=.78,pt.cex=1.05,y.intersp=1.25,xjust=0)
legend(47.4,nrow(d)*.62,legend=names(response_cols),fill=response_cols,border=NA,title="Confirmed best\noverall response",bty="n",cex=.78,y.intersp=1.25,xjust=0)
dev.off()
