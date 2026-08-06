args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", args, value = TRUE)
base_dir <- if (length(file_arg)) dirname(normalizePath(sub("^--file=", "", file_arg[1]), winslash = "/", mustWork = FALSE)) else getwd()
d <- read.csv(file.path(base_dir, "cox_forest_data.csv"), stringsAsFactors = FALSE, check.names = FALSE)
library(grid)
fmt <- function(v) {
  if (!is.finite(v)) return("")
  digits <- if (v>=100) 0 else if (v>=10) 1 else if (v>=1) 2 else 3
  sub("\\.$","",sub("0+$","",formatC(v,format="f",digits=digits)))
}
fmtp <- function(v) if (!is.finite(v)) "" else if (v<.001) "<0.001" else sub("\\.$","",sub("0+$","",formatC(v,format="f",digits=3)))
draw_panel <- function(z,title,y0,y1) {
  n <- nrow(z)
  top <- y1-.055
  bottom <- y0+.025
  rh <- (top-bottom)/(n+1.25)
  header_y <- top-.45*rh
  row_y <- header_y-(seq_len(n)) * rh
  lx <- c(.018,.342)
  fx <- c(.35,.655)
  sx <- c(.665,.982)
  grid.text(title,x=lx[1],y=y1-.005,just=c("left","top"),gp=gpar(fontsize=15,fontface="bold",col="#18232C"))
  grid.text("Subgroup",x=lx[1]+.007,y=header_y,just="left",gp=gpar(fontsize=9.5,fontface="bold",col="#46545F"))
  grid.text("N",x=lx[2]-.02,y=header_y,just="right",gp=gpar(fontsize=9.5,fontface="bold",col="#46545F"))
  grid.text("Hazard ratio",x=mean(fx),y=header_y,gp=gpar(fontsize=9.5,fontface="bold",col="#46545F"))
  grid.text("HR (95% CI)",x=sx[1]+.008,y=header_y,just="left",gp=gpar(fontsize=9.5,fontface="bold",col="#46545F"))
  grid.text("P value",x=sx[2]-.008,y=header_y,just="right",gp=gpar(fontsize=9.5,fontface="bold",col="#46545F"))
  mapx <- function(v) fx[1]+(log10(v)-log10(.35))/(log10(12.5)-log10(.35))*diff(fx)
  for (v in c(.5,1,2,5,10)) {
    xx <- mapx(v)
    grid.segments(xx,bottom,xx,header_y+.35*rh,gp=gpar(col="#D9E0E5",lwd=.7))
    grid.text(fmt(v),x=xx,y=bottom-.012,gp=gpar(fontsize=8.5,col="#52606D"))
  }
  grid.segments(mapx(1),bottom,mapx(1),header_y+.35*rh,gp=gpar(col="#65727C",lwd=1,lty=2))
  for (i in seq_len(n)) {
    typ <- z$row_type[i]
    bg <- if (typ=="header") "#E5EDF1" else if (i%%2) "#F5F7F8" else "white"
    grid.rect(x=.5,y=row_y[i],width=.965,height=rh*.94,gp=gpar(fill=bg,col=NA))
    indent <- if (typ %in% c("reference","level")) .026 else 0
    grid.text(z$subgroup[i],x=lx[1]+.007+indent,y=row_y[i],just="left",gp=gpar(fontsize=9.2,fontface=if(typ=="header")"bold" else "plain",col="#1E2A32"))
    if (is.finite(z$n[i])) grid.text(as.character(as.integer(z$n[i])),x=lx[2]-.02,y=row_y[i],just="right",gp=gpar(fontsize=9,col="#38454F"))
    if (typ=="header") next
    hr <- z$hr[i];lo <- z$lower[i];hi <- z$upper[i];pv <- z$p_value[i]
    sig <- is.finite(pv)&&pv<.05
    col <- if (sig) "#167C80" else "#344B5C"
    if (typ=="reference") {
      grid.circle(mapx(hr),row_y[i],r=unit(1.25,"mm"),gp=gpar(col=col,fill="white",lwd=1.2))
      ci <- "Reference"
    } else {
      grid.segments(mapx(lo),row_y[i],mapx(hi),row_y[i],gp=gpar(col=col,lwd=1.35))
      grid.segments(mapx(lo),row_y[i]-rh*.10,mapx(lo),row_y[i]+rh*.10,gp=gpar(col=col,lwd=1.1))
      grid.segments(mapx(hi),row_y[i]-rh*.10,mapx(hi),row_y[i]+rh*.10,gp=gpar(col=col,lwd=1.1))
      grid.rect(mapx(hr),row_y[i],width=unit(2.5,"mm"),height=unit(2.5,"mm"),gp=gpar(col=col,fill=col))
      ci <- paste0(fmt(hr)," (",fmt(lo),"-",fmt(hi),")")
    }
    grid.text(ci,x=sx[1]+.008,y=row_y[i],just="left",gp=gpar(fontsize=8.9,col="#26343D"))
    grid.text(fmtp(pv),x=sx[2]-.008,y=row_y[i],just="right",gp=gpar(fontsize=8.9,col="#26343D"))
  }
  grid.text("Hazard ratio (log scale)",x=mean(fx),y=bottom-.034,gp=gpar(fontsize=8.7,col="#46545F"))
}
png(file.path(base_dir,"cox_forest_plot_r.png"),width=3840,height=4080,res=300,bg="white",type=if(.Platform$OS.type=="windows")"windows" else "cairo")
grid.newpage()
grid.text("Cox proportional hazards analysis",x=.018,y=.978,just=c("left","top"),gp=gpar(fontsize=22,fontface="bold",col="#17232C"))
grid.text("Effect estimates with 95% confidence intervals",x=.018,y=.948,just=c("left","top"),gp=gpar(fontsize=11.5,col="#667782"))
draw_panel(d[d$model=="Univariate",],"Univariate analysis",.52,.885)
draw_panel(d[d$model=="Multivariate",],"Multivariate analysis",.075,.44)
dev.off()
