args <- commandArgs(trailingOnly = FALSE)
file_arg <- sub("^--file=", "", args[grep("^--file=", args)])
root <- if (length(file_arg)) dirname(normalizePath(file_arg)) else getwd()
suppressPackageStartupMessages({library(sf); library(readxl); library(ggplot2); library(patchwork); library(ragg)})
city <- st_read(file.path(root, "china_city.geojson"), quiet = TRUE)
province <- st_read(file.path(root, "china_province.geojson"), quiet = TRUE)
city_poly <- city[grepl("POLYGON", as.character(st_geometry_type(city))), ]
city_line <- city[grepl("LINESTRING", as.character(st_geometry_type(city))), ]
province_poly <- province[grepl("POLYGON", as.character(st_geometry_type(province))), ]
province_line <- province[grepl("LINESTRING", as.character(st_geometry_type(province))), ]
d1 <- read_excel(file.path(root, "data1.xlsx"))
d2 <- read_excel(file.path(root, "data2.xlsx"))
agg <- aggregate(as.numeric(d1$`Number of tick samples`), list(City = d1$City, Genus = d1$`Tick genus`), sum, na.rm = TRUE)
names(agg)[3] <- "samples"
total <- aggregate(samples ~ City, agg, sum)
dom <- do.call(rbind, lapply(split(agg, agg$City), function(z) z[which.max(z$samples), c("City", "Genus")]))
ticks <- merge(total, dom, by = "City")
points <- suppressWarnings(st_point_on_surface(city))
points <- merge(points, ticks, by.x = "name", by.y = "City")
point_xy <- st_coordinates(points)
point_data <- cbind(st_drop_geometry(points), X = point_xy[, 1], Y = point_xy[, 2])
genera <- sort(unique(agg$Genus))
pal <- c("#B84C4C", "#D58B3E", "#708C48", "#318884", "#4D75A1", "#7B6599", "#AD617E", "#8B7355")
gcol <- setNames(rep(pal, length.out = length(genera)), genera)
base_theme <- theme_void(base_size = 9) + theme(plot.title = element_text(face = "bold", size = 12), plot.subtitle = element_text(size = 7, colour = "#606668"), plot.background = element_rect(fill = "#FBFAF7", colour = NA), panel.background = element_rect(fill = "#FBFAF7", colour = NA), legend.background = element_blank(), legend.key = element_blank())
p1 <- ggplot() + geom_sf(data = city_poly, fill = "#F0EEE7", colour = "white", linewidth = .06, show.legend = FALSE) + geom_sf(data = city_line, colour = "#D5D2CB", linewidth = .08, show.legend = FALSE) + geom_sf(data = province_poly, fill = NA, colour = "#4D5354", linewidth = .22, show.legend = FALSE) + geom_sf(data = province_line, colour = "#4D5354", linewidth = .22, show.legend = FALSE) + geom_point(data = point_data, aes(X, Y, size = samples, colour = Genus), alpha = .86) + scale_colour_manual(values = gcol, name = "Dominant genus") + scale_size_area(max_size = 7, guide = "none") + coord_sf(xlim = c(73, 136), ylim = c(17, 54.5), expand = FALSE) + labs(title = "A  Tick sampling landscape", subtitle = "Bubble area: total tick samples · color: dominant tick genus") + base_theme + theme(legend.position = c(.12, .2), legend.text = element_text(size = 6), legend.title = element_text(size = 7))
city2 <- merge(city, d2, by.x = "name", by.y = "City", all.x = TRUE)
city2_poly <- city2[grepl("POLYGON", as.character(st_geometry_type(city2))), ]
city2_line <- city2[grepl("LINESTRING", as.character(st_geometry_type(city2))), ]
cap <- as.numeric(quantile(d2$Value, .98, na.rm = TRUE))
legend_cols <- colorRampPalette(c("#F4EADB", "#E9B66C", "#D8674A", "#7B2D45"))(5)
p2 <- ggplot() + geom_sf(data = city2_poly, aes(fill = pmin(Value, cap)), colour = "white", linewidth = .05, show.legend = FALSE) + geom_sf(data = city2_line, colour = "#D5D2CB", linewidth = .08, show.legend = FALSE) + geom_sf(data = province_poly, fill = NA, colour = "#4D5354", linewidth = .22, show.legend = FALSE) + geom_sf(data = province_line, colour = "#4D5354", linewidth = .22, show.legend = FALSE) + annotate("rect", xmin = seq(75.8, 80.6, length.out = 5), xmax = seq(77, 81.8, length.out = 5), ymin = 18.6, ymax = 19.4, fill = legend_cols, colour = NA) + annotate("text", x = 76.4, y = 18.15, label = "0", hjust = .5, size = 2.1, colour = "#606668") + annotate("text", x = 81.2, y = 18.15, label = round(cap), hjust = .5, size = 2.1, colour = "#606668") + annotate("text", x = 78.8, y = 17.45, label = "Value", hjust = .5, size = 2.2, colour = "#606668") + scale_fill_gradientn(colours = c("#F4EADB", "#E9B66C", "#D8674A", "#7B2D45"), limits = c(0, cap * 1.000001), guide = "none") + coord_sf(xlim = c(73, 136), ylim = c(17, 54.5), expand = FALSE) + labs(title = "B  City-level value distribution", subtitle = "Color capped at the 98th percentile; source values unchanged") + base_theme
p <- p1 | p2
p <- p + plot_annotation(title = "China spatial evidence atlas", subtitle = "City geometries and province outlines are read directly from the supplied GeoJSON files", caption = "Tick data: 196 of 198 named cities matched exactly; Wanzhou and Fuling districts were not positioned. Administrative boundaries are shown as supplied and imply no endorsement.", theme = theme(plot.title = element_text(size = 19, face = "bold"), plot.subtitle = element_text(size = 9, colour = "#656B6E"), plot.caption = element_text(size = 7, colour = "#656B6E"), plot.background = element_rect(fill = "#FBFAF7", colour = NA)))
agg_png(file.path(root, "plot_r.png"), width = 14.6, height = 7.3, units = "in", res = 360, background = "#FBFAF7")
print(p)
dev.off()
