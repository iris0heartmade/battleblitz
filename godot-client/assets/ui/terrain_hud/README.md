# 底栏地貌中层素材

## [2026-11-13] - 2026-11-13

### 新增
- 新增草原透明地貌 grassland-v1.png，采用两边高中间低的轮廓，已接入正式游戏底栏中层。
- 新增森林、岩地、沙地、水岸和中央建筑式城镇五套透明地貌；六张均为2172×724 RGBA，具有真实透明通道。
- 生成提示词见 GENERATION.md；未知地形降级使用草原构图，地形名和数值仍使用真实数据。

生成方式：内置 imagegen，透明背景。原始生成文件保留。本文件夹保存项目副本。

## 生成提示词

Generate a production game UI asset: a very wide, shallow panoramic grassland foreground strip, roughly 4:1 aspect ratio, TRANSPARENT BACKGROUND. This is ONLY original landscape artwork for the middle layer of a fantasy tactical RPG bottom HUD, NO interface, NO text, NO numbers, NO frames, NO portraits. Composition: continuous low grassy meadow along the bottom edge; slightly taller natural clusters of grass, tiny wildflowers and a few mossy stones on far left and far right; center very low, open and quiet so game statistics can later overlay it. Uneven organic silhouette; all sky and all area above grass must be genuinely transparent alpha, no painted sky or opaque rectangle. Ground is strongest at the bottom, feathering softly upward into sparse blades; do not fade the whole asset to invisibility. Ground plane seen at a gentle elevated angle, with short grass extending horizontally, not a side-view platform. Sophisticated painterly anime fantasy game environment, muted sage and olive green, warm ivory flowers, restrained sunlit highlights, soft natural shading, subtle depth, elegant hand-painted details. Bottom HUD landscape should feel like a meadow growing upward from screen bottom. Keep vegetation height under one quarter of image height at center and under two thirds at outer edges. No large trees, no buildings, no dramatic hills, no black backdrop, no checkerboard drawn into image, no watermark.
