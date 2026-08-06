resolve_script_dir <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  file_args <- grep("^--file=", args, value = TRUE)
  if (length(file_args)) return(dirname(normalizePath(sub("^--file=", "", file_args[1]), winslash = "/", mustWork = FALSE)))
  frames <- sys.frames()
  if (length(frames)) for (i in rev(seq_along(frames))) if (!is.null(frames[[i]]$ofile)) return(dirname(normalizePath(frames[[i]]$ofile, winslash = "/", mustWork = FALSE)))
  normalizePath(getwd(), winslash = "/", mustWork = FALSE)
}

required_packages <- c("ggplot2","readxl")
missing_packages <- required_packages[!vapply(required_packages,requireNamespace,logical(1),quietly=TRUE)]
if(length(missing_packages)) stop("Missing required R packages: ",paste(missing_packages,collapse=", "))

script_dir <- resolve_script_dir()
profile_path <- file.path(script_dir,"immune_age_profiles.xlsx")
longitudinal_path <- file.path(script_dir,"longitudinal_immune_dynamics.xlsx")
colour_path <- file.path(script_dir,"cell_type_colors.csv")
if(!all(file.exists(c(profile_path,longitudinal_path,colour_path)))) stop("Required data file not found")

colour_data <- read.csv(colour_path,stringsAsFactors=FALSE,check.names=FALSE,fileEncoding="UTF-8-BOM")
if(!identical(names(colour_data),c("xpos","label","color")) || nrow(colour_data)!=71) stop("Unexpected cell-type colours")
cell_colours <- setNames(colour_data$color,trimws(colour_data$label))
colour_for <- function(label) {
  result <- unname(cell_colours[label])
  missing <- is.na(result)
  result[missing] <- unname(cell_colours[paste0(label[missing]," cell")])
  result[is.na(result)] <- "#6C7A89"
  result
}

stream_groups <- list(
  "CD8 T cells"=c("KLRF1+ GZMB+ CD27- EM CD8 T cell","KLRF1- GZMB+ CD27- EM CD8 T cell","GZMK+ CD27+ EM CD8 T cell","GZMK- CD27+ EM CD8 T cell","Core naive CD8 T cell","CM CD8 T cell"),
  "CD4 T cells"=c("KLRF1- GZMB+ CD27- memory CD4 T cell","GZMB- CD27+ EM CD4 T cell","GZMB- CD27- EM CD4 T cell","Core naive CD4 T cell","CM CD4 T cell"),
  "B cells"=c("Type 2 polarized memory B cell","Early memory B cell","Transitional B cell","Core naive B cell","Core memory B cell","CD95 memory B cell","CD27+ effector B cell","CD27- effector B cell")
)
short_labels <- c(
  "KLRF1+ GZMB+ CD27- EM CD8 T cell"="KLRF1+ GZMB+ EM CD8 T","KLRF1- GZMB+ CD27- EM CD8 T cell"="KLRF1− GZMB+ EM CD8 T","GZMK+ CD27+ EM CD8 T cell"="GZMK+ CD27+ EM CD8 T","GZMK- CD27+ EM CD8 T cell"="GZMK− CD27+ EM CD8 T","Core naive CD8 T cell"="Core naive CD8 T","CM CD8 T cell"="CM CD8 T","KLRF1- GZMB+ CD27- memory CD4 T cell"="KLRF1− GZMB+ memory CD4 T","GZMB- CD27+ EM CD4 T cell"="GZMB− CD27+ EM CD4 T","GZMB- CD27- EM CD4 T cell"="GZMB− CD27− EM CD4 T","Core naive CD4 T cell"="Core naive CD4 T","CM CD4 T cell"="CM CD4 T","Type 2 polarized memory B cell"="Type 2 polarized memory B","Early memory B cell"="Early memory B","Transitional B cell"="Transitional B","Core naive B cell"="Core naive B","Core memory B cell"="Core memory B","CD95 memory B cell"="CD95 memory B","CD27+ effector B cell"="CD27+ effector B","CD27- effector B cell"="CD27− effector B"
)
stream_outputs <- c("CD8 T cells"="cd8_t_cell_streamgraph_r.png","CD4 T cells"="cd4_t_cell_streamgraph_r.png","B cells"="b_cell_streamgraph_r.png")

stream_data <- as.data.frame(readxl::read_excel(profile_path,sheet="Fig2c_d_e"),check.names=FALSE)
if(!identical(names(stream_data),c("Ages","celltypist_l3","percentage")) || nrow(stream_data)!=968 || any(!complete.cases(stream_data))) stop("Unexpected streamgraph data")

smooth_stream <- function(frame,categories) {
  ages <- 40:90
  result <- do.call(rbind,lapply(categories,function(category) {
    part <- frame[frame$celltypist_l3==category,]
    fit <- smooth.spline(part$Ages,part$percentage,spar=0.55)
    data.frame(Ages=ages,celltypist_l3=category,percentage=pmax(0,predict(fit,ages)$y),stringsAsFactors=FALSE)
  }))
  totals <- ave(result$percentage,result$Ages,FUN=sum)
  result$percentage <- result$percentage/totals*100
  result$celltypist_l3 <- factor(result$celltypist_l3,levels=categories)
  result
}

for(group_name in names(stream_groups)) {
  categories <- stream_groups[[group_name]]
  smooth_data <- smooth_stream(stream_data[stream_data$celltypist_l3 %in% categories,],categories)
  palette <- setNames(colour_for(categories),categories)
  p <- ggplot2::ggplot(smooth_data,ggplot2::aes(x=Ages,y=percentage,fill=celltypist_l3))+
    ggplot2::geom_area(colour="#202A31",linewidth=0.45)+
    ggplot2::scale_fill_manual(values=palette,labels=unname(short_labels[categories]),name=NULL)+
    ggplot2::scale_x_continuous(limits=c(40,90),breaks=seq(40,90,10),expand=c(0,0))+
    ggplot2::scale_y_continuous(breaks=seq(0,100,20),labels=function(x) paste0(x,"%"),expand=c(0,0))+
    ggplot2::coord_cartesian(ylim=c(0,100))+
    ggplot2::labs(title=paste0(group_name," composition across age"),subtitle="Smoothed proportional trajectories from ages 40 to 90",x="Age (years)",y=paste0("Share within ",group_name))+
    ggplot2::theme_classic(base_family="sans",base_size=11)+
    ggplot2::theme(plot.title=ggplot2::element_text(size=21,face="bold",colour="#202A31",margin=ggplot2::margin(b=6)),plot.subtitle=ggplot2::element_text(size=10.5,colour="#697680",margin=ggplot2::margin(b=20)),axis.title=ggplot2::element_text(size=12,colour="#303A42"),axis.text=ggplot2::element_text(colour="#34414A"),legend.position="bottom",legend.text=ggplot2::element_text(size=9),legend.key.width=grid::unit(1.2,"cm"),plot.margin=ggplot2::margin(24,25,10,28))+
    ggplot2::guides(fill=ggplot2::guide_legend(nrow=if(length(categories)<=6) 2 else 2,byrow=TRUE))
  ggplot2::ggsave(file.path(script_dir,stream_outputs[group_name]),p,width=13.5,height=8.2,units="in",dpi=300,bg="white")
}

longitudinal_order <- c("Adaptive NK cell","KLRF1- GZMB+ CD27- EM CD8 T cell","KLRF1- GZMB+ CD27- memory CD4 T cell","KLRF1+ GZMB+ CD27- EM CD8 T cell","KLRF1+ effector Vd1 gdT","KLRF1- effector Vd1 gdT")
longitudinal <- as.data.frame(readxl::read_excel(longitudinal_path,sheet="Fig3b"),check.names=FALSE)
if(!identical(names(longitudinal),c("AIFI_L3","subject.subjectGuid","Age Group","sample.daysSinceFirstVisit","AIFI_L3_clr")) || nrow(longitudinal)!=1463 || any(!complete.cases(longitudinal))) stop("Unexpected longitudinal data")
longitudinal <- longitudinal[longitudinal$AIFI_L3 %in% longitudinal_order,]
longitudinal$AIFI_L3 <- factor(longitudinal$AIFI_L3,levels=longitudinal_order)
longitudinal$`Age Group` <- factor(longitudinal$`Age Group`,levels=c("Young","Older"))
age_colours <- c(Young="#35978F",Older="#BF812D")
correlation_rows <- do.call(rbind,lapply(split(longitudinal,list(longitudinal$AIFI_L3,longitudinal$`Age Group`),drop=TRUE),function(part) {
  test <- suppressWarnings(cor.test(part$sample.daysSinceFirstVisit,part$AIFI_L3_clr,method="spearman",exact=FALSE))
  data.frame(AIFI_L3=part$AIFI_L3[1],`Age Group`=part$`Age Group`[1],label=sprintf("%s: ρ = %.2f, p = %s",part$`Age Group`[1],unname(test$estimate),if(test$p.value<0.001) format(test$p.value,scientific=TRUE,digits=2) else sprintf("%.3f",test$p.value)),stringsAsFactors=FALSE,check.names=FALSE)
}))
correlation_rows$AIFI_L3 <- factor(correlation_rows$AIFI_L3,levels=longitudinal_order)
correlation_rows$`Age Group` <- factor(correlation_rows$`Age Group`,levels=c("Young","Older"))
correlation_rows$x <- -10
limits_by_cell <- tapply(longitudinal$AIFI_L3_clr,longitudinal$AIFI_L3,range)
correlation_rows$y <- vapply(seq_len(nrow(correlation_rows)),function(i) {
  values <- longitudinal$AIFI_L3_clr[longitudinal$AIFI_L3==correlation_rows$AIFI_L3[i]]
  max(values)-(.08+.10*(as.integer(correlation_rows$`Age Group`[i])-1))*diff(range(values))
},numeric(1))

p_long <- ggplot2::ggplot(longitudinal,ggplot2::aes(x=sample.daysSinceFirstVisit,y=AIFI_L3_clr,colour=`Age Group`))+
  ggplot2::geom_line(ggplot2::aes(group=interaction(subject.subjectGuid,`Age Group`)),linewidth=0.32,alpha=0.20)+
  ggplot2::geom_smooth(ggplot2::aes(group=`Age Group`),method="lm",formula=y~x,se=TRUE,linewidth=1.25,alpha=0.13)+
  ggplot2::geom_text(data=correlation_rows,ggplot2::aes(x=x,y=y,label=label,colour=`Age Group`),inherit.aes=FALSE,hjust=0,size=2.8,show.legend=FALSE)+
  ggplot2::facet_wrap(~AIFI_L3,ncol=2,scales="free_y")+
  ggplot2::scale_colour_manual(values=age_colours,drop=FALSE)+
  ggplot2::scale_x_continuous(limits=c(-20,620),breaks=c(0,200,400,600))+
  ggplot2::labs(title="Longitudinal immune-cell dynamics",subtitle="Individual trajectories, age-group linear fits and 95% confidence intervals",x="Time since first visit (days)",y="Centered log-ratio abundance",colour=NULL)+
  ggplot2::theme_bw(base_family="sans",base_size=10)+
  ggplot2::theme(plot.title=ggplot2::element_text(size=22,face="bold",colour="#202A31"),plot.subtitle=ggplot2::element_text(size=10.5,colour="#697680",margin=ggplot2::margin(b=16)),strip.text=ggplot2::element_text(size=9.2,face="bold",colour="#27323A"),strip.background=ggplot2::element_rect(fill="#E8EDF0",colour=NA),panel.grid.minor=ggplot2::element_blank(),panel.grid.major.x=ggplot2::element_blank(),legend.position="top",legend.justification="right",plot.margin=ggplot2::margin(25,24,18,28))
ggplot2::ggsave(file.path(script_dir,"longitudinal_cell_dynamics_r.png"),p_long,width=14.5,height=15.8,units="in",dpi=300,bg="white")

curve_order <- c("CM CD4 T","CM CD8 T","Core naive CD4 T","Core naive CD8 T","GZMB- CD27- EM CD4 T","GZMB- CD27+ EM CD4 T","GZMK+ CD27+ EM CD8 T","Naive CD4 Treg")
dataset_order <- c("Follow up\n10x Flex","Onek1k\n10x 3'","Terekhova\n10x 5'")
curves <- as.data.frame(readxl::read_excel(profile_path,sheet="Fig2f_g"),check.names=FALSE)
if(!identical(names(curves),c("pbmc_sample_id","Ages","RNA_Age_Metric_Up","celltype","Dataset")) || nrow(curves)!=10248 || any(!complete.cases(curves))) stop("Unexpected curve data")
curves$celltype <- factor(curves$celltype,levels=curve_order)
curves$Dataset <- factor(curves$Dataset,levels=dataset_order)
curve_colours <- setNames(colour_for(curve_order),curve_order)
curve_stats <- do.call(rbind,lapply(split(curves,list(curves$Dataset,curves$celltype),drop=TRUE),function(part) {
  test <- suppressWarnings(cor.test(part$Ages,part$RNA_Age_Metric_Up,method="spearman",exact=FALSE))
  data.frame(Dataset=part$Dataset[1],celltype=part$celltype[1],label=sprintf("ρ = %.2f\np = %s",unname(test$estimate),if(test$p.value<0.001) format(test$p.value,scientific=TRUE,digits=2) else sprintf("%.3f",test$p.value)),x=89,y=min(part$RNA_Age_Metric_Up),stringsAsFactors=FALSE)
}))
curve_stats$Dataset <- factor(curve_stats$Dataset,levels=dataset_order)
curve_stats$celltype <- factor(curve_stats$celltype,levels=curve_order)

p_curve <- ggplot2::ggplot(curves,ggplot2::aes(x=Ages,y=RNA_Age_Metric_Up,colour=celltype))+
  ggplot2::geom_smooth(method="loess",formula=y~x,span=0.8,se=TRUE,fill="#AAB1B6",alpha=0.42,linewidth=1.0)+
  ggplot2::geom_text(data=curve_stats,ggplot2::aes(x=x,y=y,label=label,colour=celltype),inherit.aes=FALSE,hjust=1,vjust=-0.25,size=2.25,show.legend=FALSE)+
  ggplot2::facet_grid(Dataset~celltype,scales="free_y",labeller=ggplot2::label_wrap_gen(width=18))+
  ggplot2::scale_colour_manual(values=curve_colours,guide="none")+
  ggplot2::scale_x_continuous(limits=c(39,91),breaks=seq(40,90,10))+
  ggplot2::labs(title="RNA age metric trajectories",subtitle="Local quadratic fits with 95% confidence intervals across three independent datasets",x="Age (years)",y="RNA age metric (upregulated genes)")+
  ggplot2::theme_bw(base_family="sans",base_size=8)+
  ggplot2::theme(plot.title=ggplot2::element_text(size=22,face="bold",colour="#202A31"),plot.subtitle=ggplot2::element_text(size=10.5,colour="#697680",margin=ggplot2::margin(b=16)),strip.text.x=ggplot2::element_text(size=7.5,face="bold"),strip.text.y=ggplot2::element_text(size=8.2,face="bold",angle=90),panel.grid.minor=ggplot2::element_blank(),panel.grid.major.x=ggplot2::element_blank(),axis.text=ggplot2::element_text(size=6.8),plot.margin=ggplot2::margin(25,20,18,25))
ggplot2::ggsave(file.path(script_dir,"rna_age_metric_curves_r.png"),p_curve,width=19.2,height=8.8,units="in",dpi=300,bg="white")

cat("Saved:",paste(file.path(script_dir,c(stream_outputs,"longitudinal_cell_dynamics_r.png","rna_age_metric_curves_r.png")),collapse="\nSaved: "),"\n")
