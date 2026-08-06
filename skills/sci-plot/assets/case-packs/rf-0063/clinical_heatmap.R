resolve_script_dir <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  file_args <- grep("^--file=", args, value = TRUE)
  if (length(file_args)) return(dirname(normalizePath(sub("^--file=", "", file_args[1]), winslash = "/", mustWork = FALSE)))
  frames <- sys.frames()
  if (length(frames)) for (i in rev(seq_along(frames))) if (!is.null(frames[[i]]$ofile)) return(dirname(normalizePath(frames[[i]]$ofile, winslash = "/", mustWork = FALSE)))
  normalizePath(getwd(), winslash = "/", mustWork = FALSE)
}

script_dir <- resolve_script_dir()
data_path <- file.path(script_dir,"clinical_heatmap_data.tsv")
output_path <- file.path(script_dir,"clinical_heatmap_r.png")
if (!file.exists(data_path)) stop("Data file not found")

dat <- read.delim(data_path,sep="\t",stringsAsFactors=FALSE,check.names=FALSE,fileEncoding="UTF-8-BOM",na.strings=c("","NA","NaN"))
required <- c("patient_id","mrd_status","mrd_ctDNA_ppm_log","mol_ml_peudolog","cfdna_input_ng","main_histology","Stage","lesion1_size_pathology","pack_years_truncated","luad_subtype","oncogenic_event")
if (!all(required %in% names(dat)) || nrow(dat)!=171 || length(unique(dat$patient_id))!=171) stop("Unexpected clinical data")
dat$oncogenic_event[is.na(dat$oncogenic_event)|!nzchar(dat$oncogenic_event)] <- "None"
dat$luad_subtype <- ifelse(is.na(dat$luad_subtype)|!nzchar(dat$luad_subtype),"NA",tools::toTitleCase(tolower(dat$luad_subtype)))
dat <- dat[order(ifelse(dat$main_histology=="LUAD",0,1),ifelse(is.finite(dat$mrd_ctDNA_ppm_log),dat$mrd_ctDNA_ppm_log,0)),]
if (!identical(as.integer(table(factor(dat$main_histology,levels=c("LUAD","Non-LUAD")))),c(94L,77L))) stop("Unexpected histology counts")

histology_palette <- c(LUAD="#D0BB7E","Non-LUAD"="#91C7BA")
stage_palette <- c(I="#E8EAF5",II="#7AA8CE",III="#345C9F")
subtype_palette <- c("Invasive Mucinous"="#EAB874",Lepidic="#A6C7DB",Papillary="#4B7BB1",Acinar="#B3D291",Cribriform="#6CA956",Micropapillary="#DE9493",Solid="#CA2E2E")
event_palette <- c(None="#E5E5E5","EGFR mutated"="#602A84","MET exon 14 skipped"="#CCAC68")
ctdna_palette <- c(Detected="#8FD0F3","Not Detected"="#BFC2C5")
size_palette <- colorRampPalette(c("#F7F8FC","#A5A9C8","#2F386E"))(256)
smoking_palette <- colorRampPalette(c("#F7F7F7","#A7A7A7","#171717"))(256)

value_colours <- function(values,limits,palette,missing="#D9D9D9") {
  index <- round(pmax(0,pmin(1,(values-limits[1])/diff(limits)))*(length(palette)-1))+1
  result <- palette[index]
  result[!is.finite(values)] <- missing
  result
}

category_colours <- function(values,palette,missing="#D9D9D9") {
  result <- unname(palette[values])
  result[is.na(result)] <- missing
  result
}

x0 <- 0.058
x1 <- 0.796
label_x <- x1+0.010
n <- nrow(dat)
cell_width <- (x1-x0)/n
x_left <- x0+(seq_len(n)-1)*cell_width
x_right <- x_left+cell_width*0.88

draw_bar <- function(values,bottom,top,maximum,ticks,tick_labels,colours,label) {
  for(i in seq_along(ticks)) {
    y <- bottom+(ticks[i]/maximum)*(top-bottom)
    segments(x0,y,x1,y,col="#E8EBED",lwd=0.8)
    text(x0-0.006,y,tick_labels[i],adj=c(1,0.5),cex=0.62,col="#38434C")
  }
  for(i in seq_len(n)) if(is.finite(values[i])) rect(x_left[i],bottom,x_right[i],bottom+pmin(values[i],maximum)/maximum*(top-bottom),col=colours[i],border=NA)
  segments(x0,bottom,x1,bottom,col="#7E878E",lwd=0.8)
  segments(x0,bottom,x0,top,col="#7E878E",lwd=0.8)
  text(label_x,(bottom+top)/2,label,adj=c(0,0.5),cex=0.82,font=2,col="#2A333A")
}

draw_track <- function(colours,bottom,label) {
  top <- bottom+0.032
  for(i in seq_len(n)) rect(x0+(i-1)*cell_width,bottom,x0+i*cell_width,top,col=colours[i],border=NA)
  text(label_x,(bottom+top)/2,label,adj=c(0,0.5),cex=0.79,col="#2A333A")
}

draw_legend <- function(x,y,title,labels,colours,ncol=1,width=0.09) {
  text(x,y+0.035,title,adj=c(0,0),cex=0.78,font=2,col="#28323A")
  for(i in seq_along(labels)) {
    column <- (i-1)%%ncol
    row <- (i-1)%/%ncol
    xx <- x+column*width
    yy <- y-row*0.025
    rect(xx,yy-0.007,xx+0.010,yy+0.007,col=colours[i],border=NA)
    text(xx+0.014,yy,labels[i],adj=c(0,0.5),cex=0.64,col="#3B464E")
  }
}

draw_gradient <- function(x,y,w,palette,ticks,limits,title) {
  text(x,y+0.035,title,adj=c(0,0),cex=0.76,font=2,col="#28323A")
  for(i in seq_along(palette)) rect(x+(i-1)/length(palette)*w,y,x+i/length(palette)*w,y+0.018,col=palette[i],border=NA)
  for(v in ticks) text(x+(v-limits[1])/diff(limits)*w,y-0.006,v,adj=c(0.5,1),cex=0.60,col="#38434C")
}

png(output_path,width=6000,height=3450,res=300,bg="white",type=if(.Platform$OS.type=="windows") "windows" else "cairo")
par(family="sans",mar=c(0,0,0,0),xpd=NA)
plot.new()
plot.window(xlim=c(0,1),ylim=c(0,1))
text(x0,0.958,"Clinicopathological landscape of early-stage lung cancer",adj=c(0,1),cex=1.95,font=2,col="#20272D")
text(x0,0.918,"171 patients ordered by histology and preoperative ctDNA abundance",adj=c(0,1),cex=0.96,col="#64717B")

ctdna_colours <- category_colours(dat$mrd_status,ctdna_palette)
draw_bar(as.numeric(dat$mrd_ctDNA_ppm_log),0.735,0.880,5.65,0:5,c("0","10","100","1,000","10,000","100,000"),ctdna_colours,"ctDNA (PPM)")
draw_bar(as.numeric(dat$mol_ml_peudolog),0.655,0.727,5.9,c(0,1,3,5),c("0","10","1,000","100,000"),rep("#3C5488",n),"Tumor molecules/mL")
draw_track(category_colours(dat$main_histology,histology_palette),0.616,"Histology")
draw_track(category_colours(dat$Stage,stage_palette),0.577,"pTNM stage")
draw_track(value_colours(as.numeric(dat$lesion1_size_pathology),c(5,120),size_palette),0.538,"Tumor size (mm)")
draw_track(value_colours(as.numeric(dat$pack_years_truncated),c(0,136),smoking_palette),0.499,"Smoking (pack years)")
draw_track(category_colours(dat$luad_subtype,subtype_palette),0.460,"LUAD subtype")
draw_track(category_colours(dat$oncogenic_event,event_palette),0.421,"Oncogenic event")
draw_bar(as.numeric(dat$cfdna_input_ng),0.337,0.413,52,c(0,20,40),c("0","20","40"),rep("#B09C85",n),"Input cfDNA (ng)")

split_x <- x0+94*cell_width
segments(split_x,0.337,split_x,0.880,col="white",lwd=2.5)
for(i in seq_len(n)) text(x0+(i-0.5)*cell_width,0.323,gsub("CRUK","",dat$patient_id[i]),srt=90,adj=c(1,0.5),cex=0.39,col="#364047")
text(label_x,0.311,"CRUK ID",adj=c(0,0.5),cex=0.79,col="#2A333A")

draw_legend(0.058,0.165,"Histology",names(histology_palette),histology_palette)
draw_legend(0.150,0.165,"ctDNA",names(ctdna_palette),ctdna_palette)
draw_legend(0.260,0.165,"pTNM stage",names(stage_palette),stage_palette)
draw_legend(0.365,0.165,"LUAD subtype",names(subtype_palette),subtype_palette,2,0.105)
draw_legend(0.615,0.165,"Oncogenic event",names(event_palette),event_palette)
draw_gradient(0.058,0.055,0.145,size_palette,c(5,50,100,120),c(5,120),"Tumor size (mm)")
draw_gradient(0.245,0.055,0.145,smoking_palette,c(0,50,100,136),c(0,136),"Smoking (pack years)")
text(0.955,0.055,"Bars and tracks share patient order",adj=c(1,0),cex=0.64,col="#7A848C")
dev.off()
cat("Saved:",output_path,"\n")
