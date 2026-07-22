extends RefCounted
## texture_loader.gd
##
## Centralised texture / image loader (07-21 M7). Both ``unit_node.gd``
## and ``tile_set_builder.gd`` previously called ``Image.load()`` /
## ``Image.load_from_file()`` directly at runtime to bypass the
## ``.import`` pipeline; that path is fragile on Windows builds and
## leaks runtime I/O into the gameplay frame budget. This helper
## encapsulates the same fallback chain with a single audit point.
##
## 1. If a tracked ``.import``-registered resource exists at
##    ``res://<path>`` or its ``.import`` mirror, return its Texture2D
##    (preferred).
## 2. Otherwise load the raw file through ``Image.load_from_file()`` so
##    the gameplay frame budget is not blown away.
## 3. Optionally resize the resulting image to ``target_size`` keeping
##    the aspect ratio (alpha-cropped, like the previous inline code).
##
## The helper is intentionally a static-only utility — no autoload
## state — so it can be unit-tested without a scene.

class_name TextureLoader


# Resize a res:// PNG/JPG/WEBP file to ``target_size`` and return a
# Texture2D. Returns ``null`` if the file cannot be read.
static func load_resized(res_path: String, target_size: int = 0) -> Texture2D:
	if res_path == "":
		return null
	var img := load_image(res_path)
	if img == null:
		return null
	return fit_image_to_square(img, target_size)


# Read an Image from a res:// path, preferring the imported resource
# (which has the .import metadata) and falling back to raw file load.
static func load_image(res_path: String) -> Image:
	if res_path == "":
		return null
	# Fast path: imported texture is preferred when its generated .ctex is
	# present. Some checked-in .import files can point at stale local cache
	# entries, and calling load() on those emits noisy errors before fallback.
	if _imported_texture_ready(res_path) and ResourceLoader.exists(res_path):
		var res: Resource = load(res_path)
		if res is Texture2D:
			var tex: Texture2D = res
			if tex.get_image() != null:
				return tex.get_image()
	# Fallback: raw file load. Image.load is the Godot 4.x API; for
	# local paths use Image.load_from_file.
	if res_path.begins_with("res://") or res_path.begins_with("user://"):
		var abs_path := ProjectSettings.globalize_path(res_path)
		if FileAccess.file_exists(abs_path):
			return Image.load_from_file(abs_path)
		# ``res://`` paths that lack a globalised file (e.g. .import
		# redirects) cannot be loaded here. The caller treats null as
		# "missing texture", which mirrors the prior behaviour.
		return null
	return Image.load_from_file(res_path)


static func _imported_texture_ready(res_path: String) -> bool:
	if not res_path.begins_with("res://"):
		return false
	var import_meta_path := res_path + ".import"
	if not FileAccess.file_exists(import_meta_path):
		return false
	var file := FileAccess.open(import_meta_path, FileAccess.READ)
	if file == null:
		return false
	var text := file.get_as_text()
	file.close()
	var marker := "dest_files=[\""
	var start := text.find(marker)
	if start < 0:
		return true
	start += marker.length()
	var end := text.find("\"", start)
	if end < 0:
		return false
	var dest_path := text.substr(start, end - start)
	return FileAccess.file_exists(dest_path)


# Crop transparent borders and resize to ``target_size`` preserving
# aspect ratio. Pure function (no side effects on the input image).
static func fit_image_to_square(img: Image, target_size: int = 0) -> Texture2D:
	if img == null or img.is_empty():
		return null
	if img.get_format() != Image.FORMAT_RGBA8:
		img.convert(Image.FORMAT_RGBA8)
	var crop_rect: Rect2i = alpha_crop_rect(img)
	if crop_rect.size.x > 0 and crop_rect.size.y > 0:
		var cropped: Image = Image.create(crop_rect.size.x, crop_rect.size.y, false, Image.FORMAT_RGBA8)
		cropped.fill(Color(0, 0, 0, 0))
		cropped.blit_rect(img, crop_rect, Vector2i.ZERO)
		img = cropped
	if target_size > 0:
		var scale: float = min(
			float(target_size) / float(max(1, img.get_width())),
			float(target_size) / float(max(1, img.get_height()))
		)
		var out_w: int = max(1, int(round(float(img.get_width()) * scale)))
		var out_h: int = max(1, int(round(float(img.get_height()) * scale)))
		# Unit and hero illustrations are high-resolution art, so keep
		# this resize smooth. Pixel-art tiles keep NEAREST in TileSetBuilder.
		img.resize(out_w, out_h, Image.INTERPOLATE_LANCZOS)
		var canvas: Image = Image.create(target_size, target_size, false, Image.FORMAT_RGBA8)
		canvas.fill(Color(0, 0, 0, 0))
		canvas.blit_rect(
			img,
			Rect2i(0, 0, out_w, out_h),
			Vector2i((target_size - out_w) / 2, (target_size - out_h) / 2)
		)
		img = canvas
	return ImageTexture.create_from_image(img)


# Compute the bounding rect of non-transparent pixels.
static func alpha_crop_rect(img: Image) -> Rect2i:
	if img == null or img.is_empty():
		return Rect2i()
	var min_x := img.get_width()
	var min_y := img.get_height()
	var max_x := -1
	var max_y := -1
	for y in range(img.get_height()):
		for x in range(img.get_width()):
			if img.get_pixel(x, y).a <= 0.05:
				continue
			min_x = min(min_x, x)
			min_y = min(min_y, y)
			max_x = max(max_x, x)
			max_y = max(max_y, y)
	if max_x < min_x or max_y < min_y:
		return Rect2i()
	return Rect2i(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)
