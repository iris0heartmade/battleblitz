# 手绘地表素材

## 当前版本（2026-11-12）
当前四张顶面使用先前生成的安静铺底版，不再将侧视土坡、灌木等立体轮廓画在顶面中。下方2026-11-11的提示词保留为上一版制作历史，不代表当前图片内容。

真实3D细节由 scripts/board/height_map/detail_models.gd 构建，detail_models.json 控制配色、地貌密度与边缘位置。map_contents.gd 在正式棋盘、编辑器和试验场共用这些模型。柱侧面不变。

## 历史版本目录说明（2026-11-11）
- grass_top.png：草坡、碎石与低灌木的色彩细节直接绘入草地图片。
- rock_top.png：岩棚、裂隙、石块与少量苔色直接绘入岩地图片。
- sand_top.png：浅沙丘、砂岩与枯草直接绘入沙地图片。
- water_top.png：浅滩、小洲、湖石、芦苇与水纹直接绘入水域图片。

## 历史版本使用方式（2026-11-11）
geometry.json 将上述图片贴到现有地块顶面，不添加独立图片节点或装饰层。柱侧面保持 handpainted 原图和原配置；旧顶面原图保留以供回退。当前四类基础地表供正式棋盘、地图编辑器和高差试验场共同使用。

## 生成记录
2026-11-11，内置 image_gen，原创手绘图片。参考用户认可的太吾式地貌配色和线条方向。

### 公共提示词
Generate ONE square full-bleed game terrain TOP TEXTURE, 1024x1024 or larger. This is an ACTUAL texture applied to a flat square ground surface. Paint all small landform details INTO this image itself. NO separate objects or sprites, no transparency. Orthographic straight overhead view. Original Taiwu-inspired Chinese illustrated-map aesthetic: confident dark fine outlines, simplified shaded color shapes, muted mineral pigments, clean hand-painted game art, NO paper grain or realistic photo texture. Richer embedded small landform details and color variation than plain swatches. Keep scale small and center relatively quiet for a unit. Scatter details in irregular groups, not a single central illustration. Consistent colored edges for adjacent tiles, no border, label, UI, diamond shape, perspective tile base, pillar or background. Landform illusion must be painted shallow highlights, contour curves and darker facets inside the flat texture. 

### grass
Olive and sage green grassy land. Paint 3 modest irregular low grassy rises with moss-green tops and narrow ochre shaded soil accents, several tiny slate pebbles, 2 little low rounded shrub patches and short dark grass tufts. Low hills occupy only about one quarter of total image; broad green quiet ground connects everything. Distinct clean ink accents and several green tones. NOT dense blades, NOT tall trees.

### rock
Slate blue-gray rocky land. Paint 3 irregular groups of shallow fractured outcrops and broad stone shelves, lighter upper facets and darker narrow edges, small scattered gray pebbles and tiny restrained moss patches. Main ground slate gray, clean ink fissures and angular planes, broad calm spaces. No tall mountains or huge vertical cliffs.

### sand
Muted sandy ochre beige desert land. Paint 3 shallow small curving dunes with cream ridges and warm ochre narrow shaded slopes, 2 little clusters of weathered sandstone pebbles and a few tiny dry tufts. Broad connecting sandy flats. Clean fine contour strokes, restrained colors, not orange saturated sand, no tall mountains.

### water
Dusty cyan blue-gray lake surface, covering at least 85 percent of image. Paint ONE small off-center irregular sandy shallow shoal with tiny moss-green patch, 2 small partly submerged slate stones and a few delicate reeds, all together less than 15 percent image. Add subtle darker blue depth patches, pale cyan shallows hugging shoal and scattered fine curved ivory ripple arcs. Keep ALL edges uninterrupted same lake blue. No enclosing bank, no square island, no tropical glossy water.

