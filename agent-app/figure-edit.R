# Frozen presentation helper. Statistical objects and source data are untouched.
ais_edit_figure <- function(p, e, chart) {
  composite <- inherits(p, "patchwork")
  index <- if(chart == "forest") 3L else if(chart == "upset") 2L else 1L
  main <- if(composite) p[[index]] else p
  if(!inherits(main, "ggplot")) stop("此脚本没有可编辑的 ggplot 坐标对象，请直接修改代码。")
  if(!is.null(e$x_label)) main <- main + ggplot2::labs(x=e$x_label)
  if(!is.null(e$y_label)) main <- main + ggplot2::labs(y=e$y_label)
  if(!is.null(e$title) && !composite) main <- main + ggplot2::labs(title=e$title)
  text_theme <- list()
  if(!is.null(e$axis_title_size)) text_theme$axis.title <- ggplot2::element_text(size=e$axis_title_size)
  if(!is.null(e$tick_size)) text_theme$axis.text <- ggplot2::element_text(size=e$tick_size)
  if(!is.null(e$title_size) && !composite) text_theme$plot.title <- ggplot2::element_text(size=e$title_size)
  main <- main + do.call(ggplot2::theme,text_theme)
  families <- list(axis.title=e$axis_title_family,axis.text=e$tick_family)
  if(!composite) families$plot.title <- e$title_family
  for(name in names(families)) if(!is.null(families[[name]]))
    main <- main + do.call(ggplot2::theme,setNames(list(ggplot2::element_text(family=families[[name]])),name))
  for(axis in c("x","y")) {
    size <- e[[paste0(axis,"_label_size")]]; family <- e[[paste0(axis,"_label_family")]]
    if(!is.null(size) || !is.null(family)) main <- main + do.call(ggplot2::theme,
      setNames(list(ggplot2::element_text(size=size,family=family)),paste0("axis.title.",axis)))
  }
  note <- NULL
  caption_style <- ggplot2::calc_element("plot.caption",ggplot2::theme_get()+main$theme)
  note_size <- caption_style$size
  note_family <- caption_style$family
  if(e$note_position == "manual" || !is.null(e$note_size) || !is.null(e$note_family)) {
    if(!is.null(main$labels$caption) && nzchar(as.character(main$labels$caption))) {
      note <- as.character(main$labels$caption)
      # Reserve the existing caption space so dragging does not resize the data panel.
      if(e$note_position == "manual") main <- main + ggplot2::theme(plot.caption=ggplot2::element_text(colour=NA))
      else { main <- main + ggplot2::theme(plot.caption=ggplot2::element_text(size=e$note_size,family=e$note_family)); note <- NULL }
    } else {
      # Only a constant statistical text annotation, never mapped gene labels,
      # counts, significance brackets, or the number-at-risk table.
      candidates <- which(vapply(main$layers, function(layer) {
        label <- layer$aes_params$label
        inherits(layer$geom,"GeomText") && !is.null(label) && length(label)==1 &&
          grepl("AUC|HR|[pPrR]\\s*[=<>]|Wilcoxon|Spearman|Pearson",label)
      }, logical(1)))
      if(length(candidates)!=1) stop("这张图没有唯一可移动的统计说明；基因标注、显著性括号等请使用代码或看图修改。")
      layer <- main$layers[[candidates]]
      note <- as.character(layer$aes_params$label)
      if(!is.null(layer$aes_params$size)) note_size <- layer$aes_params$size*72.27/25.4
      if(!is.null(layer$aes_params$family)) note_family <- layer$aes_params$family
      if(e$note_position == "manual") main$layers <- main$layers[-candidates]
      else {
        main$layers[[candidates]] <- ggplot2::ggproto(NULL,layer)
        if(!is.null(e$note_size)) main$layers[[candidates]]$aes_params$size <- e$note_size*25.4/72.27
        if(!is.null(e$note_family)) main$layers[[candidates]]$aes_params$family <- e$note_family
        note <- NULL
      }
    }
  }
  if(!is.null(e$note_size)) note_size <- e$note_size
  if(!is.null(e$note_family)) note_family <- e$note_family
  if(composite) {
    p[[index]] <- main
    if(!is.null(e$title)) p <- p + patchwork::plot_annotation(title=e$title)
    if(!is.null(e$title_size)) p <- p + patchwork::plot_annotation(theme=ggplot2::theme(plot.title=ggplot2::element_text(size=e$title_size)))
    if(!is.null(e$title_family)) p <- p + patchwork::plot_annotation(theme=ggplot2::theme(plot.title=ggplot2::element_text(family=e$title_family)))
  } else p <- main
  if(!is.null(e$legend_size)) {
    t <- ggplot2::theme(legend.title=ggplot2::element_text(size=e$legend_size),legend.text=ggplot2::element_text(size=e$legend_size))
    p <- if(composite) p & t else p + t
  }
  if(!is.null(e$legend_family)) {
    t <- ggplot2::theme(legend.title=ggplot2::element_text(family=e$legend_family),legend.text=ggplot2::element_text(family=e$legend_family))
    p <- if(composite) p & t else p + t
  }
  if(e$legend_position %in% c("left","right","top","bottom","none")) {
    t <- ggplot2::theme(legend.position=e$legend_position)
    p <- if(composite) p & t else p + t
  }
  make_grob <- function(plot) if(inherits(plot,"patchwork")) patchwork::patchworkGrob(plot) else ggplot2::ggplotGrob(plot)
  legend <- NULL
  if(e$legend_position == "manual") {
    g <- make_grob(p)
    ids <- which(grepl("^guide-box",g$layout$name) & !vapply(g$grobs,inherits,logical(1),"zeroGrob"))
    if(length(ids)!=1) stop("这张图没有唯一可移动的图例；请使用图例的上下左右位置，或直接修改代码。")
    legend <- g$grobs[[ids]]
    t <- ggplot2::theme(legend.position="none")
    p <- if(composite) p & t else p + t
  }
  info <- list(title=if(composite) p$patches$annotation$title else main$labels$title,
               x_label=main$labels$x, y_label=main$labels$y,
               note_moved=!is.null(note), legend_moved=!is.null(legend),
               font_sizes=e[c("title_size","axis_title_size","tick_size","legend_size","note_size","x_label_size","y_label_size")])
  jsonlite::write_json(info,"figure-edit-info.json",auto_unbox=TRUE,pretty=TRUE,null="null")
  if(is.null(note) && is.null(legend)) return(p)
  overlays <- list(make_grob(p))
  if(!is.null(legend)) {
    legend$vp <- grid::viewport(x=e$legend_x,y=e$legend_y,
      width=sum(legend$widths),height=sum(legend$heights),just=c(e$legend_x,e$legend_y))
    overlays <- c(overlays,list(legend))
  }
  if(!is.null(note)) overlays <- c(overlays,list(grid::textGrob(note,
    x=e$note_x,y=e$note_y,hjust=if(is.null(e$note_hjust)) e$note_x else e$note_hjust,vjust=if(is.null(e$note_vjust)) e$note_y else e$note_vjust,
    gp=grid::gpar(fontfamily=note_family,fontsize=note_size))))
  result <- do.call(grid::grobTree,overlays)
  class(result) <- c("aisi_edited_grob",class(result))
  result
}

print.aisi_edited_grob <- function(x,...) { grid::grid.newpage(); grid::grid.draw(x); invisible(x) }

# Runs made before finish() existed have no ais_save_figure in figure-style.R.
if (!exists("ais_save_figure")) ais_save_figure <- function(p,name,dir=".",size,formats=c("pdf","png","svg"),...) {
  labstyle::save_fig(p,name,dir=dir,size=size,formats=setdiff(formats,"pdf"),...)
  # Newly edited Chinese labels also need the Unicode-capable PDF device.
  if("pdf" %in% formats) {
    grDevices::cairo_pdf(file.path(dir,paste0(name,".pdf")),width=size[1],height=size[2],family="Arial")
    on.exit(grDevices::dev.off(),add=TRUE)
    if(inherits(p,"grob")) grid::grid.draw(p) else print(p)
  }
}

# Edits can turn the plot into a grid table: apply the run's colours first and
# keep the template's statistics, size and tables on the edited result.
local({
  edit <- ais_edit_figure
  ais_edit_figure <<- function(p, e, chart) {
    if (!inherits(p, "grob") && exists("ais_apply_colors")) p <- ais_apply_colors(p)
    out <- edit(p, e, chart)
    for (a in c("lab_stats", "lab_size", "lab_tables")) if (is.null(attr(out, a))) attr(out, a) <- attr(p, a)
    out
  }
})
