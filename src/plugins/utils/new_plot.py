from __future__ import annotations
from enum import Enum
from typing import Union, Tuple, List, Optional
from PIL import Image, ImageFont, ImageDraw, ImageFilter
from PIL.ImageFont import FreeTypeFont as Font
import threading
import contextvars
from dataclasses import dataclass
import os
import numpy as np

# =========================== 绘图 =========================== #

Size = Union[Tuple[int, int], Tuple[float, float]]
Position = Union[Tuple[int, int], Tuple[float, float]]
Color = Union[Tuple[int, int, int], Tuple[int, int, int, int]]

BLACK       = (0, 0, 0, 255)
DRAK_GRAY   = (64, 64, 64, 255)
GRAY        = (128, 128, 128, 255)
LIGHT_GRAY  = (192, 192, 192, 255)
WHITE       = (255, 255, 255, 255)
RED         = (255, 0, 0, 255)
GREEN       = (0, 255, 0, 255)
BLUE        = (0, 0, 255, 255)
TRANSPARENT = (0, 0, 0, 0)

ALIGN_MAP = {
    'c': ('c', 'c'), 'l': ('l', 'c'), 'r': ('r', 'c'), 't': ('c', 't'), 'b': ('c', 'b'),
    'tl': ('l', 't'), 'tr': ('r', 't'), 'bl': ('l', 'b'), 'br': ('r', 'b'),
    'lt': ('l', 't'), 'lb': ('l', 'b'), 'rt': ('r', 't'), 'rb': ('r', 'b')
}

def crop_by_align(original_size: Size, crop_size: Size, align: str):
    """
    以指定的对齐方式裁剪图片
    """
    w, h = original_size
    cw, ch = crop_size
    assert cw <= w and ch <= h, "Crop size must be smaller than original size"
    x, y = 0, 0
    xa, ya = ALIGN_MAP[align]
    if xa == 'l':
        x = 0
    elif xa == 'r':
        x = w - cw
    elif xa == 'c':
        x = (w - cw) // 2
    if ya == 't':
        y = 0
    elif ya == 'b':
        y = h - ch
    elif ya == 'c':
        y = (h - ch) // 2
    return x, y, x + cw, y + ch

FONT_DIR = "data/utils/fonts/"
DEFAULT_FONT        = "SourceHanSansCN-Regular"
DEFAULT_BOLD_FONT   = "SourceHanSansCN-Bold"
DEFAULT_HEAVY_FONT  = "SourceHanSansCN-Heavy"

def lerp_color(c1: Color, c2: Color, t: float) -> Color:
    """
    线性插值两个颜色
    """
    assert len(c1) == len(c2), "Color length must be the same"
    ret = []
    for i in range(len(c1)):
        ret.append(int(c1[i] * (1 - t) + c2[i] * t))
    return tuple(ret)

def get_font(path: str, size: int) -> Font:
    """
    指定路径获取指定大小字体
    """
    paths = [path]
    paths.append(os.path.join(FONT_DIR, path))
    paths.append(os.path.join(FONT_DIR, path + ".ttf"))
    paths.append(os.path.join(FONT_DIR, path + ".otf"))
    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    raise FileNotFoundError(f"Font file not found: {paths}")

def get_text_size(font: Font, text: str) -> Size:
    """
    根据文本和字体获取文本bbox大小
    """
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]

def get_text_offset(font: Font, text: str) -> Position:
    """
    根据文本和字体获取文本bbox偏移
    """
    bbox = font.getbbox(text)
    return bbox[0], bbox[1]

def resize_keep_ratio(img: Image.Image, max_size: int, mode='long', scale: Optional[float]=None) -> Image.Image:
    """
    保存图片原比例缩放图片指定边为max_size
    - mode: 'long' 长边缩放 'short' 短边缩放, 'w' 宽度缩放, 'h' 高度缩放
    - scale: 额外缩放比例
    """
    assert mode in ['long', 'short', 'w', 'h']
    w, h = img.size
    if mode == 'long':
        if w > h:
            ratio = max_size / w
        else:
            ratio = max_size / h
    elif mode == 'short':
        if w > h:
            ratio = max_size / h
        else:
            ratio = max_size / w
    elif mode == 'w':
        ratio = max_size / w
    else:
        ratio = max_size / h
    if scale:
        ratio *= scale
    return img.resize((int(w * ratio), int(h * ratio)))

class Gradient:
    """
    渐变色基类
    """

    def get_colors(self, size: Size) -> np.ndarray: 
        """
        根据指定大小获取渐变色二维数组 [W, H, 4]
        """
        raise NotImplementedError()

    def get_img(self, size: Size, mask: Image.Image=None) -> Image.Image:
        """
        根据指定大小和遮罩获取渐变色图片
        """
        img = Image.fromarray(self.get_colors(size), 'RGBA')
        if mask:
            assert mask.size == size, "Mask size must match image size"
            if mask.mode == 'RGBA':
                mask = mask.split()[3]
            else:
                mask = mask.convert('L')
            img.putalpha(mask)
        return img

class LinearGradient(Gradient):
    """
    线性渐变色
    """
    def __init__(self, c1: Color, c2: Color, p1: Position, p2: Position):
        """
        - c1: 起始颜色
        - c2: 终止颜色
        - p1: 起始位置（坐标浮点数[0,1]范围内）
        - p2: 终止位置（坐标浮点数[0,1]范围内）
        """
        self.c1 = c1
        self.c2 = c2
        self.p1 = p1
        self.p2 = p2
        assert p1 != p2, "p1 and p2 cannot be the same point"

    def get_colors(self, size: Size) -> np.ndarray:
        w, h = size
        p1 = np.array(self.p1) * np.array((w, h))
        p2 = np.array(self.p2) * np.array((w, h))
        y_indices, x_indices = np.meshgrid(np.arange(h), np.arange(w), indexing='ij')
        coords = np.stack((x_indices, y_indices), axis=-1)
        dist = np.linalg.norm(coords - p1, axis=-1) / np.linalg.norm(p2 - p1)
        dist = np.clip(dist, 0, 1)
        colors = dist[:, :, np.newaxis] * np.array(self.c1) + (1 - dist)[:, :, np.newaxis] * np.array(self.c2)
        return colors.astype(np.uint8)

class RadialGradient(Gradient):
    """
    径向渐变色
    """
    def __init__(self, c1: Color, c2: Color, center: Position, radius: float):
        """
        - c1: 中心颜色
        - c2: 边缘颜色
        - center: 中心位置（坐标浮点数[0,1]范围内）
        - radius: 半径
        """
        self.c1 = c1
        self.c2 = c2
        self.center = center
        self.radius = radius

    def get_colors(self, size: Size) -> np.ndarray:
        w, h = size
        center = np.array(self.center) * np.array((w, h))
        y_indices, x_indices = np.meshgrid(np.arange(h), np.arange(w), indexing='ij')
        coords = np.stack((x_indices, y_indices), axis=-1)
        dist = np.linalg.norm(coords - center, axis=-1) / self.radius
        dist = np.clip(dist, 0, 1)
        colors = dist[:, :, np.newaxis] * np.array(self.c1) + (1 - dist)[:, :, np.newaxis] * np.array(self.c2)
        return colors.astype(np.uint8)
    

