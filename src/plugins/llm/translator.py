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

    correct_cost: float
    correct_time: float
    correct_model: str

    total_time: float
    total_cost: float


class Translator:
    def __init__(self):
        self.readers = {}
        self.model_loaded = False
        self.font_path = 'data/utils/fonts/SourceHanSansCN-Regular.otf'
        self.merge_prompt_path = "data/llm/translator/prompt_merge.txt"
        self.trans_prompt_path = "data/llm/translator/prompt_trans.txt"
        self.correct_prompt_path = "data/llm/translator/prompt_correct.txt"
        self.model_name = "gpt-4o"
        self.task_id_top = 0
        self.langs = ['ja', 'ko']
        self.max_resolution = 1024 * 768
        self.merge_method = 'alg'   # alg or llm

    def calc_box_dist(self, b1, b2):
        sx1, sy1 = b1[0]
        tx1, ty1 = b1[2]
        sx2, sy2 = b2[0]
        tx2, ty2 = b2[2]
        w1, h1 = tx1 - sx1, ty1 - sy1
        w2, h2 = tx2 - sx2, ty2 - sy2
        x1, y1 = min(sx1, sx2), min(sy1, sy2)
        x2, y2 = max(tx1, tx2), max(ty1, ty2)
        w, h = x2 - x1, y2 - y1
        return (w - w1 - w2, h - h1 - h2)

    def draw_box_with_label(self, img, p1, p2, label):
        import random
        color = (random.randint(0, 150), random.randint(0, 150), random.randint(0, 150))
        draw = ImageDraw.Draw(img)
        x1, y1 = p1
        x2, y2 = p2
        draw.rectangle([x1, y1, x2, y2], outline=color)
        label_size = 16
        font = ImageFont.truetype(self.font_path, label_size)
        draw.rectangle([x2 - label_size - 2, y2 - label_size - 2, x2, y2], fill=(255, 255, 255, 150))
        draw.text((x2 - label_size, y2 - label_size), str(label), fill=color, font=font)

    def draw_text(self, img, p1, p2, text, direction):
        direction = 'ltr' if direction == 'h' else 'ttb'
        draw = ImageDraw.Draw(img)
        x1, y1 = p1
        x2, y2 = p2
        w, h = x2 - x1, y2 - y1
        border = 2
        
        font_size_start, font_size_end, font_size_step = 32, 6, 3
        font_size = font_size_start
        border = 2
        font = ImageFont.truetype(self.font_path, font_size)
        while font_size > font_size_end:
            font = font.font_variant(size=font_size)
            cur_text = ""
            for ch in text:
                cur_text += ch
                bbox = draw.multiline_textbbox([0, 0], cur_text, font=font, direction=direction)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                if tw + border * 2 > w:
                    cur_text = cur_text[:-1] + "\n" + ch
            bbox = draw.multiline_textbbox([0, 0], cur_text, font=font, direction=direction)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if th + border * 2 <= h:
                break
            font_size -= font_size_step
        draw.rectangle([x1, y1, x2, y2], outline='black', fill='white')
        draw.text((x1 + border, y1 + border), cur_text, font=font, fill='black', direction=direction)

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

    async def translate(self, ctx: HandlerContext, img: Image.Image, lang=None, debug=False) -> TranslationResult:
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
            w, h = img.size
            if w * h > self.max_resolution:
                max_size = self.max_resolution // min(w, h)
                img = resize_keep_ratio(img, max_size)
                logger.info(f'翻译任务{tid}缩放图片从({w},{h})到{img.size}')

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
                if debug:
                    logger.info(f'{tid}OCR框{i+1}: {box} | {text} | score={score}')
                x1, y1 = box[0]
                x2, y2 = box[2] 
                self.draw_box_with_label(img_w_ocr_boxes, (x1, y1), (x2, y2), i + 1)
            if debug:
                img_w_ocr_boxes.save("sandbox/img_w_ocr_boxes.png")
            logger.info(f'翻译任务{tid}OCR框绘制完成')

            # merge
            with Timer() as t_merge:
                if self.merge_method == 'llm':
                     # query llm to merge
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

                elif self.merge_method == 'alg':
                    # use algorithm to merge
                    merge_result = {}
                    n = len(ocr_result)
                    dist = [[self.calc_box_dist(ocr_result[i][0], ocr_result[j][0]) for j in range(n)] for i in range(n)]
                    visited = [False] * n
                    def dfs(u, idx):
                        merge_result[idx].append(u+1)
                        visited[u] = True
                        for v in range(n):
                            if visited[v]: continue
                            d = max(dist[u][v])
                            if d < 5:
                                dfs(v, idx)
                    for i in range(n):
                        if not visited[i]:
                            idx = str(len(merge_result) + 1)
                            merge_result[idx] = []
                            dfs(i, idx)
                    merge_result = {
                        'data': merge_result,
                        'cost': None,
                    }

            if debug:
                logger.info(f'翻译任务{tid}合并结果: {merge_result}')

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
                if debug:
                    logger.info(f'{tid}合并框{idx}: {merged_boxes[-1]}')
            
            img_w_merged_boxes = img.copy()
            for i, box in enumerate(merged_boxes):
                self.draw_box_with_label(img_w_merged_boxes, box[0], box[1], i + 1)
            if debug:
                img_w_merged_boxes.save("sandbox/img_w_merged_boxes.png")
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
                    if debug:
                        logger.info(f'翻译任务{tid}LLM翻译结果: {response["data"]}')
                    for idx, item in response['data'].items():
                        idx = int(idx) - 1
                        assert idx >= 0 and idx < len(merged_boxes)
                    return response
                
                logger.info(f'翻译任务{tid}开始向LLM请求翻译结果')
                try:
                    trans_result = await query_trans()
                except Exception as e:
                    raise Exception(f'向LLM请求翻译失败: {e}')
                logger.info(f'翻译任务{tid}LLM翻译结果请求完成')

            # query llm to correct
            with Timer() as t_correct:
                @retry(reraise=True, stop=stop_after_attempt(3), wait=wait_fixed(3))
                async def query_correct():
                    session = ChatSession()
                    session.append_user_content(
                        Path(self.correct_prompt_path).read_text().strip().format(last=trans_result['result']),
                        [get_image_b64(img_w_merged_boxes)],
                        verbose=False
                    )
                    response = await session.get_response(
                        model_name=self.model_name,
                        usage='translator_correct',
                        user_id=user_id,
                        group_id=group_id,
                    )
                    response['data'] = self.load_json_from_response(response['result'])
                    if debug:
                        logger.info(f'翻译任务{tid}LLM校对结果: {response["data"]}')
                    for idx, item in response['data'].items():
                        idx = int(idx) - 1
                        assert idx >= 0 and idx < len(merged_boxes)
                    return response
                
                logger.info(f'翻译任务{tid}开始向LLM请求校对结果')
                try:
                    correct_result = await query_correct()
                    data = correct_result['data']
                except Exception as e:
                    logger.warning(f'向LLM请求校对失败: {e}')
                    correct_result = { "cost": None }
                    data = trans_result['data']
                logger.info(f'翻译任务{tid}LLM校对结果请求完成')

            # draw translated text
            for idx, item in data.items():
                idx = int(idx) - 1
                text, direction = item, 'h'
                if debug:
                    logger.info(f'{tid}最终结果{idx+1}: ({direction}) {text}')
                box = merged_boxes[idx]
                self.draw_text(img, box[0], box[1], text, direction)
            logger.info(f'翻译任务{tid}最终结果绘制完成')

        total_cost = 0
        if merge_result['cost'] is not None:   total_cost += merge_result['cost']
        if trans_result['cost'] is not None:   total_cost += trans_result['cost']
        if correct_result['cost'] is not None: total_cost += correct_result['cost']

        return TranslationResult(
            img=img,

            total_time=t_total.get(),
            total_cost=total_cost,

            ocr_time=t_ocr.get(),

            merge_model=self.model_name,
            merge_cost=merge_result['cost'],
            merge_time=t_merge.get(),

            trans_model=self.model_name,
            trans_cost=trans_result['cost'],
            trans_time=t_trans.get(),

            correct_model=self.model_name,
            correct_cost=correct_result['cost'],
            correct_time=t_correct.get(),
        )

