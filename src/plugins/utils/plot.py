from __future__ import annotations
from enum import Enum
from typing import Union, Tuple, List, Optional
from PIL import Image, ImageFont, ImageDraw
from PIL.ImageFont import ImageFont as Font
from dataclasses import dataclass

# =========================== 绘图 =========================== #

ALIGN_MAP = {
    'c': ('c', 'c'), 'l': ('l', 'c'), 'r': ('r', 'c'), 't': ('c', 't'), 'b': ('c', 'b'),
    'tl': ('l', 't'), 'tr': ('r', 't'), 'bl': ('l', 'b'), 'br': ('r', 'b'),
    'lt': ('l', 't'), 'lb': ('l', 'b'), 'rt': ('r', 't'), 'rb': ('r', 'b')
}

BLACK = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)
RED = (255, 0, 0, 255)
GREEN = (0, 255, 0, 255)
BLUE = (0, 0, 255, 255)
TRANSPARENT = (0, 0, 0, 0)

DEFAULT_FONT_PATH = "/root/.fonts/MicrosoftYaHei/Microsoft Yahei.ttf"


def get_font(path: str, size: int) -> Font:
    return ImageFont.truetype(path, size)

def get_text_size(font: Font, text: str) -> Tuple[int, int]:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]

def get_text_offset(font: Font, text: str) -> Tuple[int, int]:
    bbox = font.getbbox(text)
    return bbox[0], bbox[1]

def resize_keep_ratio(img: Image.Image, max_size: int, long_side=True) -> Image.Image:
    w, h = img.size
    if long_side:
        if w > h:
            ratio = max_size / w
        else:
            ratio = max_size / h
    else:
        if w > h:
            ratio = max_size / h
        else:
            ratio = max_size / w
    return img.resize((int(w * ratio), int(h * ratio)))


class Painter:
    def __init__(self, img: Image.Image):
        self.img = img
        self.offset = (0, 0)
        self.size = img.size
        self.w = img.size[0]
        self.h = img.size[1]
        self.region_stack = []

    def set_region(self, pos: Tuple[int, int], size: Tuple[int, int]):
        self.region_stack.append((self.offset, self.size))
        self.offset = pos
        self.size = size
        self.w = size[0]
        self.h = size[1]
        return self

    def shrink_region(self, dlt: Tuple[int, int]):
        pos = (self.offset[0] + dlt[0], self.offset[1] + dlt[1])
        size = (self.size[0] - dlt[0] * 2, self.size[1] - dlt[1] * 2)
        return self.set_region(pos, size)

    def expand_region(self, dlt: Tuple[int, int]):
        pos = (self.offset[0] - dlt[0], self.offset[1] - dlt[1])
        size = (self.size[0] + dlt[0] * 2, self.size[1] + dlt[1] * 2)
        return self.set_region(pos, size)

    def move_region(self, dlt: Tuple[int, int], size: Tuple[int, int] = None):
        offset = (self.offset[0] + dlt[0], self.offset[1] + dlt[1])
        size = size or self.size
        return self.set_region(offset, size)

    def restore_region(self, depth=1):
        if not self.region_stack:
            self.offset = (0, 0)
            self.size = self.img.size
            self.w = self.img.size[0]
            self.h = self.img.size[1]
        else:
            self.offset, self.size = self.region_stack.pop()
            self.w = self.size[0]
            self.h = self.size[1]
        if depth > 1:
            return self.restore_region(depth - 1)
        return self

    def get(self) -> Image.Image:
        return self.img

    def text(
        self, 
        text: str, 
        pos: Tuple[int, int], 
        font: Font,
        fill: Tuple[int, int, int], 
        align: str = "left"
    ):
        draw = ImageDraw.Draw(self.img)
        text_offset = get_text_offset(font, text)
        pos = (pos[0] - text_offset[0] + self.offset[0], pos[1] - text_offset[1] + self.offset[1])
        draw.text(pos, text, font=font, fill=fill, align=align)
        return self
        
    def paste(
        self, 
        sub_img: Image.Image,
        pos: Tuple[int, int], 
        size: Tuple[int, int] = None
    ) -> Image.Image:
        if size and size != sub_img.size:
            sub_img = sub_img.resize(size)
        self.img.paste(sub_img, (pos[0] + self.offset[0], pos[1] + self.offset[1]), sub_img)
        return self

    def rect(
        self, 
        pos: Tuple[int, int], 
        size: Tuple[int, int], 
        fill: Tuple[int, int, int, int], 
        stroke: Tuple[int, int, int, int]=None, 
        stroke_width: int=1
    ):
        pos = (pos[0] + self.offset[0], pos[1] + self.offset[1])
        pos = pos + (pos[0] + size[0], pos[1] + size[1])
        if fill[3] == 255:
            draw = ImageDraw.Draw(self.img)
            draw.rectangle(pos, fill=fill)
            return self
        overlay = Image.new('RGBA', self.img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        if stroke:
            draw.rectangle(pos, fill=TRANSPARENT, outline=stroke, width=stroke_width)
        else:
            draw.rectangle(pos, fill=fill)
        self.img = Image.alpha_composite(self.img, overlay)
        return self
        
    def roundrect(
        self, 
        pos: Tuple[int, int], 
        size: Tuple[int, int], 
        fill: Tuple[int, int, int, int], 
        radius: int, 
        stroke: Tuple[int, int, int, int]=None, 
        stroke_width: int=1,
        corners = (True, True, True, True),
    ):
        pos = (pos[0] + self.offset[0], pos[1] + self.offset[1])
        pos = pos + (pos[0] + size[0], pos[1] + size[1])
        if fill[3] == 255:
            draw = ImageDraw.Draw(self.img)
            draw.rounded_rectangle(pos, fill=fill, radius=radius)
            return self
        overlay = Image.new('RGBA', self.img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        if stroke:
            draw.rounded_rectangle(pos, fill=fill, radius=radius, outline=stroke, width=stroke_width, corners=corners)
        else:
            draw.rounded_rectangle(pos, fill=fill, radius=radius, corners=corners)
        self.img = Image.alpha_composite(self.img, overlay)
        return self


# =========================== 布局类型 =========================== #

DEBUG_MODE = False
DEFAULT_PADDING = 0
DEFAULT_MARGIN = 0
DEFAULT_SEP = 8


class WidgetBg:
    def draw(self, p: Painter):
        raise NotImplementedError()

class FillBg(WidgetBg):
    def __init__(self, fill: Tuple[int, int, int, int], stroke: Tuple[int, int, int, int]=None, stroke_width: int=1):
        self.fill = fill
        self.stroke = stroke
        self.stroke_width = stroke_width

    def draw(self, p: Painter):
        p.rect((0, 0), p.size, self.fill, self.stroke, self.stroke_width)

class RoundRectBg(WidgetBg):
    def __init__(self, fill: Tuple[int, int, int, int], radius: int, stroke: Tuple[int, int, int, int]=None, stroke_width: int=1, corners = (True, True, True, True)):
        self.fill = fill
        self.radius = radius
        self.stroke = stroke
        self.stroke_width = stroke_width
        self.corners = corners
    
    def draw(self, p: Painter):
        p.roundrect((0, 0), p.size, self.fill, self.radius, self.stroke, self.stroke_width, self.corners)

class ImageBg(WidgetBg):
    def __init__(self, img: Union[str, Image.Image], align: str='c', mode='fit'):
        if isinstance(img, str):
            self.img = Image.open(img)
        else:
            self.img = img
        assert align in ALIGN_MAP
        self.align = align
        assert mode in ('fit', 'fill', 'fixed', 'repeat')
        self.mode = mode

    def draw(self, p: Painter):
        if self.mode == 'fit':
            ha, va = ALIGN_MAP[self.align]
            scale = max(p.w / self.img.size[0], p.h / self.img.size[1])
            w, h = int(self.img.size[0] * scale), int(self.img.size[1] * scale)
            if va == 'c':
                y = (p.h - h) // 2
            elif va == 't':
                y = 0
            else:
                y = p.h - h
            if ha == 'c':
                x = (p.w - w) // 2
            elif ha == 'l':
                x = 0
            else:
                x = p.w - w
            p.paste(self.img, (x, y), (w, h))
        if self.mode == 'fill':
            p.paste(self.img, (0, 0), p.size)
        if self.mode == 'fixed':
            ha, va = ALIGN_MAP[self.align]
            if va == 'c':
                y = (p.h - self.img.size[1]) // 2
            elif va == 't':
                y = 0
            else:
                y = p.h - self.img.size[1]
            if ha == 'c':
                x = (p.w - self.img.size[0]) // 2
            elif ha == 'l':
                x = 0
            else:
                x = p.w - self.img.size[0]
            p.paste(self.img, (x, y))
        if self.mode =='repeat':
            w, h = self.img.size
            for y in range(0, p.h, h):
                for x in range(0, p.w, w):
                    p.paste(self.img, (x, y))


class Widget:
    def __init__(self):
        self.parent: Optional[Widget] = None

        self.content_halign = 'l'
        self.content_valign = 't'
        self.vmargin = DEFAULT_MARGIN
        self.hmargin = DEFAULT_MARGIN
        self.vpadding = DEFAULT_PADDING
        self.hpadding = DEFAULT_PADDING
        self.w = None
        self.h = None
        self.bg = None

        self._calc_w = None
        self._calc_h = None


    def set_parent(self, parent: Widget):
        self.parent = parent
        return self

    def set_content_align(self, align: str):
        if align not in ALIGN_MAP:
            raise ValueError('Invalid align')
        self.content_halign, self.content_valign = ALIGN_MAP[align]
        return self

    def set_margin(self, margin: Union[int, Tuple[int, int]]):
        if isinstance(margin, int):
            self.vmargin = margin
            self.hmargin = margin
        else:
            self.vmargin = margin[0]
            self.hmargin = margin[1]
        return self

    def set_padding(self, padding: Union[int, Tuple[int, int]]):
        if isinstance(padding, int):
            self.vpadding = padding
            self.hpadding = padding
        else:
            self.vpadding = padding[0]
            self.hpadding = padding[1]
        return self

    def set_size(self, size: Tuple[int, int]):
        if not size: size = (None, None)
        self.w = size[0]
        self.h = size[1]
        return self

    def set_w(self, w: int):
        self.w = w
        return self
    
    def set_h(self, h: int):
        self.h = h
        return self

    def set_bg(self, bg: WidgetBg):
        self.bg = bg
        return self


    def _get_content_size(self):
        return (0, 0)
    
    def _get_self_size(self):
        if not all([self._calc_w, self._calc_h]):
            content_w, content_h = self._get_content_size()
            content_w_limit = self.w - self.hpadding * 2 if self.w is not None else content_w
            content_h_limit = self.h - self.vpadding * 2 if self.h is not None else content_h
            if content_w > content_w_limit or content_h > content_h_limit:
                raise ValueError('Content size is too large')
            self._calc_w = content_w_limit + self.hmargin * 2 + self.hpadding * 2
            self._calc_h = content_h_limit + self.vmargin * 2 + self.vpadding * 2
        return (self._calc_w, self._calc_h)

    def _get_content_pos(self):
        w, h = self._get_self_size()
        w -= self.hpadding * 2 + self.hmargin * 2
        h -= self.vpadding * 2 + self.vmargin * 2
        cw, ch = self._get_content_size()
        if self.content_halign == 'l':
            cx = 0
        elif self.content_halign == 'r':
            cx = w - cw
        elif self.content_halign == 'c':
            cx = (w - cw) // 2
        if self.content_valign == 't':
            cy = 0
        elif self.content_valign == 'b':
            cy = h - ch
        elif self.content_valign == 'c':
            cy = (h - ch) // 2
        return (cx, cy)
        
    def _draw_self(self, p: Painter):
        if DEBUG_MODE:
            import random
            color = (random.randint(0, 200), random.randint(0, 200), random.randint(0, 200), 255)
            p.rect((0, 0), (p.w, p.h), TRANSPARENT, stroke=color, stroke_width=2)
            font = get_font(DEFAULT_FONT_PATH, 16)
            s = f"{self.__class__.__name__}({p.w},{p.h})"
            s += f"self={self._get_self_size()}"
            s += f"content={self._get_content_size()}"
            p.text(s, (3, 3), font=font, fill=color)
        
        if self.bg:
            self.bg.draw(p)
    
    def _draw_content(self, p: Painter):
        pass
    
    def draw(self, p: Painter):
        assert p.size == self._get_self_size()

        p.shrink_region((self.hmargin, self.vmargin))
        self._draw_self(p)

        p.shrink_region((self.hpadding, self.vpadding))
        cx, cy = self._get_content_pos()
        p.move_region((cx, cy)) 
        self._draw_content(p)

        p.restore_region(3)
        

class Frame(Widget):
    def __init__(self, items: List[Widget]=None):
        super().__init__()
        self.items = items or []
        for item in self.items:
            item.set_parent(self)
    
    def add_item(self, item: Widget):
        item.set_parent(self)
        self.items.append(item)
        return self
    
    def set_items(self, items: List[Widget]):
        for item in self.items:
            item.set_parent(None)
        self.items = items
        for item in self.items:
            item.set_parent(self)
        return self

    def _get_content_size(self):
        size = (0, 0)
        for item in self.items:
            w, h = item._get_self_size()
            size = (max(size[0], w), max(size[1], h))
        return size
    
    def _draw_content(self, p: Painter):
        for item in self.items:
            w, h = item._get_self_size()
            x, y = 0, 0
            if self.content_halign == 'l':
                x = 0
            elif self.content_halign == 'r':
                x = p.w - w
            elif self.content_halign == 'c':
                x = (p.w - w) // 2
            if self.content_valign == 't':
                y = 0
            elif self.content_valign == 'b':
                y = p.h - h
            elif self.content_valign == 'c':
                y = (p.h - h) // 2
            p.move_region((x, y), (w, h))
            item.draw(p)
            p.restore_region()
    

class HSplit(Widget):
    def __init__(self, items: List[Widget]=None, ratios: List[float]=None, sep=DEFAULT_SEP, item_size_mode='fixed', item_align='c'):
        super().__init__()
        self.items = items or []
        for item in self.items:
            item.set_parent(self)
        self.ratios = ratios 
        self.sep = sep
        assert item_size_mode in ('expand', 'fixed')
        self.item_size_mode = item_size_mode
        if item_align not in ALIGN_MAP:
            raise ValueError('Invalid align')
        self.item_halign, self.item_valign = ALIGN_MAP[item_align]

    def set_items(self, items: List[Widget]):
        for item in self.items:
            item.set_parent(None)
        self.items = items
        for item in self.items:
            item.set_parent(self)
        return self
    
    def add_item(self, item: Widget):
        item.set_parent(self)
        self.items.append(item)
        return self

    def set_item_align(self, align: str):
        if align not in ALIGN_MAP:
            raise ValueError('Invalid align')
        self.item_halign, self.item_valign = ALIGN_MAP[align]
        return self

    def set_sep(self, sep: int):
        self.sep = sep  
        return self

    def set_ratios(self, ratios: List[float]):
        self.ratios = ratios
        return self

    def set_item_size_mode(self, mode: str):
        assert mode in ('expand', 'fixed')
        self.item_size_mode = mode
        return self

    def _get_item_sizes(self):
        ratios = self.ratios if self.ratios else [item._get_self_size()[0] for item in self.items]
        if self.item_size_mode == 'expand':
            assert self.w is not None, 'Expand mode requires width'
            ratio_sum = sum(ratios)
            unit_w = (self.w - self.sep * (len(ratios) - 1) - self.hpadding * 2) / ratio_sum
        else:
            unit_w = 0
            for r, item in zip(ratios, self.items):
                iw, ih = item._get_self_size()
                unit_w = max(unit_w, iw / r)
        ret = []
        h = max([item._get_self_size()[1] for item in self.items])
        for r, item in zip(ratios, self.items):
            ret.append((int(unit_w * r), h))
        return ret

    def _get_content_size(self):
        if not self.items:
            return (0, 0)
        sizes = self._get_item_sizes()
        return (sum(s[0] for s in sizes) + self.sep * (len(sizes) - 1), max(s[1] for s in sizes))
    
    def _draw_content(self, p: Painter):
        if not self.items:
            return
        sizes = self._get_item_sizes()
        cur_x = 0
        for item, (w, h) in zip(self.items, sizes):
            iw, ih = item._get_self_size()
            x, y = cur_x, 0
            if self.item_halign == 'l':
                x += 0
            elif self.item_halign == 'r':
                x += w - iw
            elif self.item_halign == 'c':
                x += (w - iw) // 2
            if self.item_valign == 't':
                y += 0
            elif self.item_valign == 'b':
                y += h - ih
            elif self.item_valign == 'c':
                y += (h - ih) // 2
            p.move_region((x, y), (iw, ih))
            item.draw(p)
            p.restore_region()
            cur_x += w + self.sep


class VSplit(Widget):
    def __init__(self, items: List[Widget]=None, ratios: List[float]=None, sep=DEFAULT_SEP, item_size_mode='fixed', item_align='c'):
        super().__init__()
        self.items = items or []
        for item in self.items:
            item.set_parent(self)
        self.ratios = ratios 
        self.sep = sep
        assert item_size_mode in ('expand', 'fixed')
        self.item_size_mode = item_size_mode
        if item_align not in ALIGN_MAP:
            raise ValueError('Invalid align')
        self.item_halign, self.item_valign = ALIGN_MAP[item_align]

    def set_items(self, items: List[Widget]):
        for item in self.items:
            item.set_parent(None)
        self.items = items
        for item in self.items:
            item.set_parent(self)
        return self
        
    def add_item(self, item: Widget):
        item.set_parent(self)
        self.items.append(item)
        return self

    def set_item_align(self, align: str):
        if align not in ALIGN_MAP:
            raise ValueError('Invalid align')
        self.item_halign, self.item_valign = ALIGN_MAP[align]
        return self
    
    def set_sep(self, sep: int):
        self.sep = sep  
        return self

    def set_ratios(self, ratios: List[float]):
        self.ratios = ratios
        return self

    def set_item_size_mode(self, mode: str):
        assert mode in ('expand', 'fixed')
        self.item_size_mode = mode
        return self

    def _get_item_sizes(self):
        ratios = self.ratios if self.ratios else [item._get_self_size()[1] for item in self.items]
        if self.item_size_mode == 'expand':
            assert self.h is not None, 'Expand mode requires height'
            ratio_sum = sum(ratios)
            unit_h = (self.h - self.sep * (len(ratios) - 1) - self.vpadding * 2) / ratio_sum
        else:
            unit_h = 0
            for r, item in zip(ratios, self.items):
                iw, ih = item._get_self_size()
                unit_h = max(unit_h, ih / r)
        ret = []
        w = max([item._get_self_size()[0] for item in self.items])
        for r, item in zip(ratios, self.items):
            ret.append((w, int(unit_h * r)))
        return ret
    
    def _get_content_size(self):
        if not self.items:
            return (0, 0)
        sizes = self._get_item_sizes()
        return (max(s[0] for s in sizes), sum(s[1] for s in sizes) + self.sep * (len(sizes) - 1))
    
    def _draw_content(self, p: Painter):
        if not self.items:
            return
        sizes = self._get_item_sizes()
        cur_y = 0
        for item, (w, h) in zip(self.items, sizes):
            iw, ih = item._get_self_size()
            x, y = 0, cur_y
            if self.item_halign == 'l':
                x += 0
            elif self.item_halign == 'r':
                x += w - iw
            elif self.item_halign == 'c':
                x += (w - iw) // 2
            if self.item_valign == 't':
                y += 0
            elif self.item_valign == 'b':
                y += h - ih
            elif self.item_valign == 'c':
                y += (h - ih) // 2
            p.move_region((x, y), (iw, ih))
            item.draw(p)
            p.restore_region()
            cur_y += h + self.sep
    

class Grid(Widget):
    def __init__(self, items: List[Widget]=None, row_count=None, col_count=None, item_size_mode='fixed', item_align='c', hsep=DEFAULT_SEP, vsep=DEFAULT_SEP):
        super().__init__()
        self.items = items or []
        for item in self.items:
            item.set_parent(self)
        self.row_count = row_count
        self.col_count = col_count
        assert not (self.row_count and self.col_count), 'Either row_count or col_count should be None'
        assert item_size_mode in ('expand', 'fixed')
        self.item_size_mode = item_size_mode
        self.hsep = hsep
        self.vsep = vsep
        if item_align not in ALIGN_MAP:
            raise ValueError('Invalid align')
        self.item_halign, self.item_valign = ALIGN_MAP[item_align]

    def set_items(self, items: List[Widget]):
        for item in self.items:
            item.set_parent(None)
        self.items = items
        for item in self.items:
            item.set_parent(self)
        return self
        
    def add_item(self, item: Widget):
        item.set_parent(self)
        self.items.append(item)
        return self
    
    def set_item_align(self, align: str):
        if align not in ALIGN_MAP:
            raise ValueError('Invalid align')
        self.item_halign, self.item_valign = ALIGN_MAP[align]
        return self

    def set_sep(self, hsep=None, vsep=None):
        if hsep is not None:
            self.hsep = hsep
        if vsep is not None:
            self.vsep = vsep
        return self

    def set_row_count(self, count: int):
        self.row_count = count
        self.col_count = None
        return self

    def set_col_count(self, count: int):
        self.col_count = count
        self.row_count = None
        return self

    def set_item_size_mode(self, mode: str):
        assert mode in ('expand', 'fixed')
        self.item_size_mode = mode
        return self

    def _get_grid_rc_and_size(self):
        r, c = self.row_count, self.col_count
        assert r and not c or c and not r, 'Either row_count or col_count should be None'
        if not r: r = (len(self.items) + c - 1) // c
        if not c: c = (len(self.items) + r - 1) // r
        if self.item_size_mode == 'expand':
            assert self.w is not None and self.h is not None, 'Expand mode requires width and height'
            gw = (self.w - self.hsep * (c - 1) - self.hpadding * 2) / c
            gh = (self.h - self.vsep * (r - 1) - self.vpadding * 2) / r
        else:
            gw, gh = 0, 0
            for item in self.items:
                iw, ih = item._get_self_size()
                gw = max(gw, iw)
                gh = max(gh, ih)
        return (r, c), (gw, gh)
    
    def _get_content_size(self):
        (r, c), (gw, gh) = self._get_grid_rc_and_size()
        return (c * gw + self.hsep * (c - 1), r * gh + self.vsep * (r - 1))
    
    def _draw_content(self, p: Painter):
        (r, c), (gw, gh) = self._get_grid_rc_and_size()
        for idx, item in enumerate(self.items):
            i, j = idx // c, idx % c
            x = j * (gw + self.hsep)
            y = i * (gh + self.vsep)
            iw, ih = item._get_self_size()
            if self.item_halign == 'l':
                x += 0
            elif self.item_halign == 'r':
                x += gw - iw
            elif self.item_halign == 'c':
                x += (gw - iw) // 2
            if self.item_valign == 't':
                y += 0
            elif self.item_valign == 'b':
                y += gh - ih
            elif self.item_valign == 'c':
                y += (gh - ih) // 2
            p.move_region((x, y), (iw, ih))
            item.draw(p)
            p.restore_region()


@dataclass
class TextStyle:
    font: str = DEFAULT_FONT_PATH
    size: int = 16
    color: Tuple[int, int, int, int] = BLACK


class Text(Widget):
    def __init__(self, text: str = '', style: TextStyle = None, line_count=1, line_sep=2, wrap=True, overflow='shrink'):
        super().__init__()
        self.text = text
        self.style = style or TextStyle()
        self.line_count = line_count
        self.line_sep = line_sep
        self.wrap = wrap
        assert overflow in ('shrink', 'clip')
        self.overflow = overflow

        self.set_padding(5)
        self.set_margin(0)

    def set_text(self, text: str):
        self.text = text
        return self

    def set_style(self, style: TextStyle):
        self.style = style
        return self
   
    def set_line_count(self, count: int):
        self.line_count = count
        return self
    
    def set_line_sep(self, sep: int):
        self.line_sep = sep

    def set_wrap(self, wrap: bool):
        self.wrap = wrap
        return self

    def set_overflow(self, overflow: str):
        assert overflow in ('shrink', 'clip')
        self.overflow = overflow

    def _get_pil_font(self):
        return get_font(self.style.font, self.style.size)

    def _get_clip_text_to_width_idx(self, text: str, width: int, suffix=''):
        font = self._get_pil_font()
        w, _ = get_text_size(font, text + suffix)
        if w <= width:
            return None
        l, r = 0, len(text)
        while l <= r:
            m = (l + r) // 2
            w, _ = get_text_size(font, text[:m] + suffix)
            if   w < width: l = m + 1
            elif w > width: r = m - 1
            else: return m
        return r

    def _get_lines(self):
        lines = self.text.split('\n')  
        clipped_lines = []
        for line in lines:
            if self.w:
                w = self.w - self.hpadding * 2
                suffix = '...' if self.overflow == 'shrink' else ''
                if self.wrap:
                    while True:
                        line_suffix = suffix if len(clipped_lines) == self.line_count - 1 else ''
                        clip_idx = self._get_clip_text_to_width_idx(line, w, line_suffix)
                        if clip_idx is None:
                            clipped_lines.append(line)
                            break
                        clipped_lines.append(line[:clip_idx] + line_suffix)
                        line = line[clip_idx:]
                        if len(clipped_lines) == self.line_count:
                            break
                else:
                    clip_idx = self._get_clip_text_to_width_idx(line, w, suffix)
                    if clip_idx is not None:
                        line = line[:clip_idx] + suffix
                    clipped_lines.append(line)
            else:
                clipped_lines.append(line)
        return clipped_lines[:self.line_count]

    def _get_content_size(self):
        lines = self._get_lines()
        w, h = 0, 0
        font = self._get_pil_font()
        for line in lines:
            lw, _ = get_text_size(font, line)
            w = max(w, lw)
        h = self.line_count * (self.style.size + self.line_sep) - self.line_sep
        if self.w:
            w = self.w - self.hpadding * 2
        if self.h:
            h = self.h - self.vpadding * 2
        return (w, h)
        
    def _draw_content(self, p: Painter):
        font = self._get_pil_font()
        lines = self._get_lines()
        text_h = (self.style.size + self.line_sep) * len(lines) - self.line_sep
        if self.content_valign == 't':
            start_y = 0
        elif self.content_valign == 'b':
            start_y = p.h - text_h
        elif self.content_valign == 'c':
            start_y = (p.h - text_h) // 2

        for i, line in enumerate(lines):
            lw, lh = get_text_size(font, line)
            x, y = 0, start_y + i * (self.style.size + self.line_sep)
            if self.content_halign == 'l':
                x += 0
            elif self.content_halign == 'r':
                x += p.w - lw
            elif self.content_halign == 'c':
                x += (p.w - lw) // 2
            p.move_region((x, y), (lw, lh))
            p.text(line, (0, 0), font=font, fill=self.style.color)
            p.restore_region()
    

class ImageBox(Widget):
    def __init__(self, image: Union[str, Image.Image], image_size_mode='original', size=None):
        super().__init__()
        if isinstance(image, str):
            self.image = Image.open(image)
        else:
            self.image = image

        assert image_size_mode in ('fit', 'fill', 'original')
        self.image_size_mode = image_size_mode

        if size:
            self.set_size(size)
        
        self.set_margin(0)
        self.set_padding(0)

    def set_image(self, image: Union[str, Image.Image]):
        if isinstance(image, str):
            self.image = Image.open(image)
        else:
            self.image = image
        return self

    def set_image_size_mode(self, mode: str):
        assert mode in ('fit', 'fill', 'original')
        self.image_size_mode = mode
        return self

    def _get_content_size(self):
        w, h = self.image.size
        if self.image_size_mode == 'original':
            return (w, h)
        elif self.image_size_mode == 'fit':
            assert self.w is not None or self.h is not None, 'Fit mode requires width or height'
            tw = self.w - self.hpadding * 2 if self.w else 1000000
            th = self.h - self.vpadding * 2 if self.h else 1000000
            scale = min(tw / w, th / h)
            return (int(w * scale), int(h * scale))
        elif self.image_size_mode == 'fill':
            assert self.w is not None or self.h is not None, 'Fill mode requires width or height'
            if self.w and self.h:
                return (self.w - self.hpadding * 2, self.h - self.vpadding * 2)
            else:
                tw = self.w - self.hpadding * 2 if self.w else 1000000
                th = self.h - self.vpadding * 2 if self.h else 1000000
                scale = max(tw / w, th / h)
                return (int(w * scale), int(h * scale))
    
    def _draw_content(self, p: Painter):
        w, h = self._get_content_size()
        p.paste(self.image, (0, 0), (w, h))


class Spacer(Widget):
    def __init__(self, w: int = None, h: int = None):
        super().__init__()
        self.set_size((w, h))
    
    def _get_content_size(self):
        return (self.w - 2 * self.hpadding, self.h - 2 * self.vpadding)

    def _draw_content(self, p: Painter):
        pass


class Canvas(Frame):
    def __init__(self, w=None, h=None, bg: WidgetBg=None):
        super().__init__()
        self.set_size((w, h))
        self.set_bg(bg)
        self.set_margin(0)

    def get_img(self) -> Image.Image:
        size = self._get_self_size()
        img = Image.new('RGBA', size, TRANSPARENT)
        p = Painter(img)
        self.draw(p)
        return p.get()

