from . import *
from ..utils import *
import easyocr
from PIL import Image
from tenacity import retry, stop_after_attempt, wait_fixed


config = get_config('llm')
logger = get_logger("Llm")
file_db = get_file_db("data/llm/db.json", logger)


from concurrent.futures import ThreadPoolExecutor
ocr_pool_executor = ThreadPoolExecutor(max_workers=1)


@dataclass
class TranslationResult:
    img: Image.Image
    
    ocr_time: float

    merge_cost: float
    merge_time: float
    merge_model: str

    trans_cost: float
    trans_time: float
    trans_model: str

    total_time: float
    total_cost: float


class Translator:
    def __init__(self):
        self.readers = {}
        self.model_loaded = False
        self.font_path = 'data/utils/fonts/SourceHanSansCN-Regular.otf'
        self.merge_prompt_path = "data/llm/translator/prompt_merge.txt"
        self.trans_prompt_path = "data/llm/translator/prompt_trans.txt"
        self.model_name = "gpt-4o"
        self.task_id_top = 0
        self.langs = ['ja', 'ko']
        self.max_size = 1024

    def draw_box_with_label(self, img, p1, p2, label):
        import random
        color = (random.randint(0, 150), random.randint(0, 150), random.randint(0, 150))
        draw = ImageDraw.Draw(img)
        x1, y1 = p1
        x2, y2 = p2
        draw.rectangle([x1, y1, x2, y2], outline=color)
        label_size = 20
        font = ImageFont.truetype(self.font_path, label_size)
        draw.rectangle([x2 + 1, y2 - label_size, x2 + label_size, y2], fill='white')
        draw.text((x2, y2 - label_size), str(label), fill=color, font=font)

    def draw_text(self, img, p1, p2, text):
        draw = ImageDraw.Draw(img)
        x1, y1 = p1
        x2, y2 = p2
        w, h = x2 - x1, y2 - y1
        font_size = 50
        border = 2
        font = ImageFont.truetype(self.font_path, font_size)
        while font_size > 5:
            font = font.font_variant(size=font_size)
            bbox = draw.multiline_textbbox([0, 0], text, font=font)
            size = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if size[0] + border * 2 <= w and size[1] + border * 2 <= h:
                break
            font_size -= 1
        draw.rectangle([x1, y1, x2, y2], outline='black', fill='white')
        draw.text((x1 + border, y1 + border), text, font=font, fill='black')

    def load_json_from_response(self, text) -> dict:
        first_bracket_index = text.find('{')
        last_bracket_index = text.rfind('}')
        return dict(json.loads(text[first_bracket_index:last_bracket_index+1]))

    def load_model(self) -> bool:
        if not self.model_loaded:
            for lang in self.langs:
                self.readers[lang] = easyocr.Reader(['en', lang])
                logger.info(f'OCR模型{lang}加载成功')
            self.model_loaded = True
            return True
        return False

    async def translate(self, ctx: HandlerContext, img: Image.Image, lang=None) -> TranslationResult:
        with Timer() as t_total:
            if not self.model_loaded:
                raise Exception('OCR模型未加载')
            if lang is None:
                lang = self.langs[0]
            if lang not in self.readers:
                raise Exception(f'不支持的语言:{lang}, 支持语言有:{self.readers.keys()}')
            reader: easyocr.Reader = self.readers[lang]

            tid = f"[{self.task_id_top}]"
            self.task_id_top += 1

            img = img.convert('RGB')
            img = resize_keep_ratio(img, self.max_size)

            user_id  = ctx.user_id  if ctx else None
            group_id = ctx.group_id if ctx else None

            logger.info(f'开始图片翻译任务{tid} lang={lang}')

            # ocr
            with Timer() as t_ocr:
                try:
                    npy_img = np.array(img)
                    ocr_result = await run_in_pool(reader.readtext, npy_img, pool=ocr_pool_executor)
                except Exception as e:
                    raise Exception(f'OCR失败: {e}')
                logger.info(f'翻译任务{tid}OCR完成，检测到{len(ocr_result)}个框')

            # draw ocr boxes
            img_w_ocr_boxes = img.copy()
            for i, (box, text, score) in enumerate(ocr_result):
                logger.debug(f'{tid}OCR框{i+1}: {box} | {text} | score={score}')
                x1, y1 = box[0]
                x2, y2 = box[2] 
                self.draw_box_with_label(img_w_ocr_boxes, (x1, y1), (x2, y2), i + 1)
            logger.info(f'翻译任务{tid}OCR框绘制完成')

            # query llm to merge
            with Timer() as t_merge:
                @retry(reraise=True, stop=stop_after_attempt(3), wait=wait_fixed(3))
                async def query_merge():
                    session = ChatSession()
                    session.append_user_content(
                        Path(self.merge_prompt_path).read_text().strip(), 
                        [get_image_b64(img_w_ocr_boxes)],
                        verbose=False
                    )
                    response = await session.get_response(
                        model_name=self.model_name,
                        usage='translator_merge',
                        user_id=user_id,
                        group_id=group_id,
                    )
                    response['data'] = self.load_json_from_response(response['result'])
                    return response

                logger.info(f'翻译任务{tid}开始向LLM请求合并框')
                try:
                    merge_result = await query_merge()
                except Exception as e:
                    raise Exception(f'向LLM请求合并框失败: {e}')
                logger.info(f'翻译任务{tid}LLM合并框请求完成，合并后{len(merge_result["data"])}个框')

            # draw merged boxes
            merged_boxes = []
            for idx, id_list in merge_result['data'].items():
                x1, y1 = 1e9, 1e9
                x2, y2 = -1e9, -1e9
                for i in id_list:
                    if int(i) - 1 >= len(ocr_result):
                        continue
                    box = ocr_result[int(i) - 1][0]
                    x1 = min(x1, box[0][0])
                    y1 = min(y1, box[0][1])
                    x2 = max(x2, box[2][0])
                    y2 = max(y2, box[2][1])
                merged_boxes.append(((x1, y1), (x2, y2)))
                logger.debug(f'{tid}合并框{idx}: {merged_boxes[-1]}')
            
            img_w_merged_boxes = img.copy()
            for i, box in enumerate(merged_boxes):
                self.draw_box_with_label(img_w_merged_boxes, box[0], box[1], i + 1)
            logger.info(f'翻译任务{tid}合并框绘制完成')
                
            # query llm to translate
            with Timer() as t_trans:
                @retry(reraise=True, stop=stop_after_attempt(3), wait=wait_fixed(3))
                async def query_trans():
                    session = ChatSession()
                    session.append_user_content(
                        Path(self.trans_prompt_path).read_text().strip(), 
                        [get_image_b64(img_w_merged_boxes)],
                        verbose=False
                    )
                    response = await session.get_response(
                        model_name=self.model_name,
                        usage='translator_trans',
                        user_id=user_id,
                        group_id=group_id,
                    )
                    response['data'] = self.load_json_from_response(response['result'])
                    assert len(response['data']) == len(merged_boxes)
                    for idx, text in response['data'].items():
                        idx = int(idx) - 1
                        assert idx >= 0 and idx < len(merged_boxes)
                    return response
                
                logger.info(f'翻译任务{tid}开始向LLM请求翻译结果')
                try:
                    trans_result = await query_trans()
                except Exception as e:
                    raise Exception(f'向LLM请求翻译失败: {e}')
                logger.info(f'翻译任务{tid}LLM翻译结果请求完成')

            # draw translated text
            for idx, text in trans_result['data'].items():
                idx = int(idx) - 1
                logger.debug(f'{tid}翻译结果{idx+1}: {text}')
                box = merged_boxes[idx]
                self.draw_text(img, box[0], box[1], text)
            logger.info(f'翻译任务{tid}翻译结果绘制完成')

        return TranslationResult(
            img=img,
            merge_model=self.model_name,
            merge_cost=merge_result['cost'],
            trans_model=self.model_name,
            trans_cost=trans_result['cost'],
            total_time=t_total.get(),
            ocr_time=t_ocr.get(),
            merge_time=t_merge.get(),
            trans_time=t_trans.get(),
            total_cost=merge_result['cost'] + trans_result['cost'],
        )

