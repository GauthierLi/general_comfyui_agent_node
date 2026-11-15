from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps

from comfy_api.latest import io, ui


class ImagePathPreview(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ICafeImagePathPreview",
            display_name="image_path_preview",
            category="工具",
            description="按图像路径读取图片并在节点上预览。输入路径列表时预览全部图片。",
            inputs=[io.String.Input("path", display_name="图像路径", default="")],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            # Receive a ComfyUI output list of paths as one list instead of one call per element.
            is_input_list=True,
            is_output_node=True,
        )

    @classmethod
    def execute(cls, path) -> io.NodeOutput:
        # A single Python list value, e.g. the list_string_transfer output, arrives wrapped as [list].
        if len(path) == 1 and isinstance(path[0], (list, tuple)):
            path = path[0]
        paths = [str(item).strip() for item in path if str(item).strip()]
        if not paths:
            raise ValueError("image_path_preview 的图像路径为空。")
        results = []
        for item in paths:
            file = Path(item).expanduser()
            if not file.is_file():
                raise FileNotFoundError(f"图像文件不存在：{file}")
            with Image.open(file) as image:
                rgb = ImageOps.exif_transpose(image).convert("RGB")
            tensor = torch.from_numpy(np.array(rgb).astype(np.float32) / 255.0)[None]
            results += ui.ImageSaveHelper.save_images(
                tensor, filename_prefix="ICafeImagePathPreview", folder_type=io.FolderType.temp, cls=cls, compress_level=1,
            )
        return io.NodeOutput(ui=ui.SavedImages(results))
