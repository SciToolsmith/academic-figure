#!/usr/bin/env Rscript

fail <- function(msg) { message("ERROR: ", msg); quit(status = 2) }
args <- commandArgs(trailingOnly = TRUE)
opts <- list(composition=NULL, boundaries=NULL, `output-prefix`=NULL, `crs-label`=NULL, title="Spatial distribution and composition", dpi="320")
for (arg in args) { if (!startsWith(arg,"--") || !grepl("=",arg,fixed=TRUE)) fail(paste0("arguments must use --name=value: ",arg)); p<-strsplit(sub("^--","",arg),"=",fixed=TRUE)[[1]]; key<-p[1]; value<-paste(p[-1],collapse="="); if(!key%in%names(opts)) fail(paste0("unknown argument --",key)); opts[[key]]<-value }
if (any(vapply(opts[c("composition","boundaries","output-prefix","crs-label")],is.null,logical(1)))) fail("--composition, --boundaries, --output-prefix and --crs-label are required")
dpi<-suppressWarnings(as.integer(opts$dpi)); if(is.na(dpi)||dpi<72) fail("--dpi must be at least 72")
d<-tryCatch(read.csv(opts$composition,stringsAsFactors=FALSE,check.names=FALSE),error=function(e) fail(conditionMessage(e)))
b<-tryCatch(read.csv(opts$boundaries,stringsAsFactors=FALSE,check.names=FALSE),error=function(e) fail(conditionMessage(e)))
creq<-c("location_id","label","x","y","component","value"); breq<-c("polygon_id","vertex_order","x","y")
if(!all(creq%in%names(d))||nrow(d)==0) fail(paste("composition CSV must contain",paste(creq,collapse=", ")))
if(!all(breq%in%names(b))||nrow(b)==0) fail(paste("boundaries CSV must contain",paste(breq,collapse=", ")))
for(nm in c("location_id","label","component")) d[[nm]]<-trimws(as.character(d[[nm]]))
if(any(d$location_id=="")||any(d$label=="")||any(d$component=="")) fail("composition identifiers and labels must be non-empty")
if(anyDuplicated(paste(d$location_id,d$component,sep="\r"))) fail("duplicate location/component pairs are not allowed")
for(nm in c("x","y","value")) d[[nm]]<-suppressWarnings(as.numeric(d[[nm]]))
if(!"location_order"%in%names(d)) d$location_order<-match(d$location_id,unique(d$location_id)); d$location_order<-suppressWarnings(as.numeric(d$location_order))
if(any(!is.finite(d$x))||any(!is.finite(d$y))||any(!is.finite(d$value))||any(!is.finite(d$location_order))||any(d$value<0)) fail("coordinates/order must be finite and values nonnegative")
meta_ok<-tapply(seq_len(nrow(d)),d$location_id,function(ii) length(unique(paste(d$label[ii],d$x[ii],d$y[ii],d$location_order[ii],sep="\r")))==1)
if(any(!meta_ok)) fail("label, coordinates and location_order must be consistent within location")
locations<-names(sort(tapply(d$location_order,d$location_id,unique))); components<-unique(d$component)
if(length(locations)<1||length(locations)>80||length(components)<1||length(components)>8) fail("expected 1–80 locations and 1–8 components")
values<-matrix(0,nrow=length(components),ncol=length(locations),dimnames=list(components,locations)); for(i in seq_len(nrow(d))) values[d$component[i],d$location_id[i]]<-d$value[i]
totals<-colSums(values); if(any(totals<=0)) fail("each location component total must be positive")
b$polygon_id<-trimws(as.character(b$polygon_id)); b$vertex_order<-suppressWarnings(as.numeric(b$vertex_order)); b$x<-suppressWarnings(as.numeric(b$x)); b$y<-suppressWarnings(as.numeric(b$y))
if(any(b$polygon_id=="")||any(!is.finite(b$vertex_order))||any(!is.finite(b$x))||any(!is.finite(b$y))) fail("boundary identifiers, coordinates and order must be valid")
if(any(table(b$polygon_id)<3)) fail("each polygon must have at least three vertices")
palette<-c("#C8755C","#4E8995","#887DA5","#789566","#BE974A","#A96775","#5F91B7","#B87C44"); cols<-setNames(palette[seq_along(components)],components)
xr<-range(b$x); yr<-range(b$y); span<-max(diff(xr),diff(yr),1); area<-if(max(totals)==min(totals)) rep(.42,length(totals)) else .25+(totals-min(totals))/(max(totals)-min(totals))*.33; radii<-sqrt(area/pi)*span*.14
draw_pie<-function(x,y,vals,r){ start<-pi/2; total<-sum(vals); for(i in seq_along(vals)){ end<-start+2*pi*vals[i]/total; if(vals[i]>0){ th<-seq(start,end,length.out=max(5,ceiling((end-start)*50))); polygon(c(x,x+r*cos(th),x),c(y,y+r*sin(th),y),col=cols[i],border="#FBFAF7",lwd=.8) }; start<-end }; symbols(x,y,circles=r,inches=FALSE,add=TRUE,fg="white",bg=NA,lwd=.7) }
draw<-function(device_fun){ device_fun(); par(bg="#FBFAF7",mar=c(1,1,5,1),family="sans",xpd=NA); plot.new(); plot.window(xlim=xr+c(-.08,.08)*span,ylim=yr+c(-.10,.10)*span,asp=1)
  for(pid in unique(b$polygon_id)){ z<-b[b$polygon_id==pid,]; z<-z[order(z$vertex_order),]; polygon(z$x,z$y,col="#F0F1EC",border="#B9C0BD",lwd=1) }
  for(j in seq_along(locations)){ loc<-locations[j]; ii<-which(d$location_id==loc)[1]; draw_pie(d$x[ii],d$y[ii],values[,j],radii[j]); text(d$x[ii],d$y[ii]-radii[j]-.035*span,d$label[ii],cex=.62,col="#20272D",pos=1,offset=0) }
  legend("topleft",legend=components,pch=21,pt.bg=cols[components],col="white",bty="n",horiz=length(components)<=4,cex=.72)
  title(main=opts$title,adj=0,line=2.15,cex.main=1.35,font.main=2,col.main="#20272D"); mtext(paste0("Supplied projected coordinates · ",opts$`crs-label`," · symbol area encodes location total; sectors encode composition."),side=3,adj=0,line=.5,cex=.72,col="#68767D"); dev.off() }
prefix<-opts$`output-prefix`; dir.create(dirname(prefix),recursive=TRUE,showWarnings=FALSE)
draw(function() png(paste0(prefix,".png"),width=10.2,height=6.8,units="in",res=dpi,bg="#FBFAF7")); draw(function() pdf(paste0(prefix,".pdf"),width=10.2,height=6.8,bg="#FBFAF7",useDingbats=FALSE))
message(sprintf("Validated %d locations, %d components, and %d supplied polygons; excluded rows: 0.",length(locations),length(components),length(unique(b$polygon_id))))
