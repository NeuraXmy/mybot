from matplotlib import pyplot as plt
from datetime import datetime, timedelta
import matplotlib.dates as mdates
import matplotlib
import jieba
import jieba.posseg as pseg
import wordcloud
import random
import colorsys
import io
from ..utils import *

config = get_config("statistics")
logger = get_logger("Sta")
file_db = get_file_db("data/statistics/db.json", logger)

FONT_NAME = "Source Han Sans CN"
FONT_PATH = "data/utils/fonts/SourceHanSansCN-Regular.otf"

plt.switch_backend('agg')
matplotlib.rcParams['font.family'] = [FONT_NAME]
matplotlib.rcParams['axes.unicode_minus'] = False   


def get_colors():
    cmap = plt.get_cmap('Set3')
    colors = [cmap(i) for i in range(cmap.N) if i not in [9]]
    return colors


# 获取群聊-日期的主题颜色
def get_theme_color_info(gid, date):
    rng = random.Random(f"{gid}-{date}")
    hue = rng.uniform(0, 1)
    h1 = (hue + 0.05) % 1.0
    h2 = (hue - 0.05 + 1.0) % 1.0
    if rng.random() < 0.5:
        h1, h2 = h2, h1
    s, l = 0.85, 0.85
    c1 = colorsys.hls_to_rgb(h1, l, s)
    c2 = colorsys.hls_to_rgb(h2, l, s)
    c1 = [int(255*c) for c in c1] + [255]
    c2 = [int(255*c) for c in c2] + [255]
    return {
        "hue": hue,
        "colors": [c1, c2],
        "rng": rng
    }

# 获取图标配色
def get_cmap(gid, date, n=10, hue_range=0.2):
    info = get_theme_color_info(gid, date)
    hue = info["hue"]
    ret = []
    for i in range(n):
        s, l = 0.8, 0.9
        if i % 2 == 0:
            s, l = 0.8, 0.8
        h_delta = hue_range * (i / n - 0.5)
        h = (hue + h_delta + 1.0) % 1.0
        c = colorsys.hls_to_rgb(h, l, s)
        ret.append(c)
    return ret

# 绘制饼图
def draw_pie(gid, date_str, recs, topk_user, topk_name):
    logger.info(f"开始绘制饼图")

    # 统计数量
    topk_user_set = set(topk_user)
    user_count, user_image_count = Counter(), Counter()
    other_count, other_image_count = 0, 0
    for rec in recs:
        if rec['user_id'] not in topk_user_set:
            other_count += 1
            if has_image(rec['msg']):
                other_image_count += 1
        else:
            user_count.inc(rec['user_id'])
            if has_image(rec['msg']):
                user_image_count.inc(rec['user_id'])

    topk_user_count = [user_count.get(user) for user in topk_user]
    topk_user_image_count = [user_image_count.get(user) for user in topk_user]
    total_count = sum(topk_user_count) + other_count
    
    # 计算其他数量（比例小于多少的用户并入其他）
    rate_threshold = 0.03
    while topk_user_count and topk_user_count[-1] / total_count < rate_threshold:
        other_count += topk_user_count.pop()
        other_image_count += topk_user_image_count.pop()
        topk_user.pop()
        topk_name.pop()

    if other_count > 0:
        topk_user_count.append(other_count)
        topk_user_image_count.append(other_image_count)
        topk_user.append("其他")
        topk_name.append("其他")
    
    rates = [count/total_count for count in topk_user_count]
    start_angles, end_angles, cur_angle = [], [], -90
    for i in range(len(rates)):
        start_angles.append(cur_angle)
        end_angles.append(cur_angle - rates[i] * 360)
        cur_angle -= rates[i] * 360

    canvas_w, canvas_h = 800, 400
    with Canvas(w=canvas_w, h=canvas_h) as canvas:
        cx, cy = int(canvas_w / 2), int(canvas_h / 2)
        radius = int(canvas_h * 0.8 / 2)
        cmap = get_cmap(gid, date_str)

        # 绘制饼图扇形
        for i in range(len(topk_user)):
            pos, size = (0, 0), (radius * 2, radius * 2)
            color = tuple([int(255*c) for c in cmap[i]] + [255])
            p = Painter(Image.new('RGBA', size, TRANSPARENT))
            p.pieslice(pos, size, end_angles[i], start_angles[i], color, stroke=None, stroke_width=0)
            img = p.get()
            ImageBox(img).set_offset((cx, cy)).set_offset_anchor('c')

        # 添加百分比
        for i in range(len(topk_user)):
            if topk_user[i] == "其他" and rates[i] < 0.03 and rates[i - 1] < 0.03:
                continue
            mid_angle = (start_angles[i] + end_angles[i]) / 2
            x = int(cx + radius * 0.6 * math.cos(math.radians(mid_angle)))
            y = int(cy + radius * 0.6 * math.sin(math.radians(mid_angle)))
            text1 = f"{int(rates[i]*100+0.5)}%"
            text2 = f"({topk_user_count[i]})"
            if abs(x - cx) > abs(y - cy):
                text = text1 + ' ' + text2
                line_count = 1
            else:
                text = text1 + '\n' + text2
                line_count = 2
            TextBox(text, style=TextStyle(size=16, font=DEFAULT_FONT, color=(50, 50, 50, 255)), line_count=line_count).set_offset((x, y)).set_offset_anchor('c')

        # 添加标签
        for i in range(len(topk_user) - 1, -1, -1):
            mid_angle = (start_angles[i] + end_angles[i]) / 2
            x = int(cx + (radius + 20) * math.cos(math.radians(mid_angle)))
            y = int(cy + (radius + 20) * math.sin(math.radians(mid_angle)))
            if x >= cx:
                offset_anchor = 'lt'
                x -= 20
                y -= 20
            else:
                offset_anchor = 'rb'
                x += 20
                y += 20

            with HSplit().set_offset_anchor(offset_anchor).set_offset((x, y)).set_sep(0) as hs:
                if topk_user[i] != "其他":
                    try:
                        ImageBox(download_avatar(topk_user[i], circle=True), size=(None, 40))
                    except:
                        logger.print_exc(f"获取{topk_user[i]}头像失败")
                with Frame().set_bg(RoundRectBg(fill=(240, 240, 240, 170), radius=4)).set_padding(5).set_content_align('l'):
                    color = cmap[i]
                    h, l, s = colorsys.rgb_to_hls(*color)
                    r, g, b = colorsys.hls_to_rgb(h, l * 0.7, s)
                    color = (int(r * 255), int(g * 255), int(b * 255), 255)
                    TextBox(f"{truncate(topk_name[i], 16)}", style=TextStyle(size=20, font=DEFAULT_BOLD_FONT, color=color)).set_offset((0, -2))
                if offset_anchor == 'rb':
                    hs.items.reverse()

    return canvas.get_img()


# 绘制折线图
def draw_plot(gid, date_str, ax, recs, interval, topk_user, topk_name):
    logger.log(f"开始绘制折线图")
    topk = len(topk_user)
    cnts = [[0] * int(24*60/interval) for _ in range(topk + 1)]
    all = [0] * int(24*60/interval)
    img_all = [0] * int(24*60/interval)

    for rec in recs:
        time = rec['time']
        minute = time.hour * 60 + time.minute
        index = int(minute / interval)
        if rec['user_id'] in topk_user:
            cnts[topk_user.index(rec['user_id'])][index] += 1
        else:
            cnts[-1][index] += 1
        all[index] += 1
        if has_image(rec['msg']):
            img_all[index] += 1

    x = [datetime.strptime("00:00", "%H:%M") + timedelta(minutes=interval*i) for i in range(int(24*60/interval))]

    ax.bar(x[1:-1], all[1:-1], width=timedelta(minutes=interval), align='edge', color='#bbbbbb', label='消息数')
    ax.bar(x[1:-1], img_all[1:-1], width=timedelta(minutes=interval), align='edge', color='#dddddd', label='图片消息数')

    # cmap = get_cmap(gid, date_str)
    # for i in range(0, topk):
    #     offset = timedelta(minutes=interval) / 2
    #     tx = [xi + offset for xi in x[1:-1]]
    #     ax.plot(tx, cnts[i][1:-1], label=topk_name[i], linewidth=0.7, color=cmap[i])

    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%k'))
    plt.xticks(fontsize=8)
    plt.yticks(fontsize=8)
    plt.legend(fontsize=8)

last_userwords = []
jieba_inited = False

# jieba重置（用户词典）
def reset_jieba():
    global last_userwords, jieba_inited
    jieba.initialize()
    # 清空上次添加的用户词
    for word in last_userwords: jieba.del_word(word)
    # 读取用户词和停用词并且规范处理
    userwords = file_db.get("userwords", [])
    stopwords = file_db.get("stopwords", [])
    userwords = [word.strip() for word in userwords if word not in stopwords and word.strip() != ""]
    stopwords = [word.strip() for word in stopwords if word.strip() != ""]
    userwords = list(set(userwords))
    stopwords = list(set(stopwords))
    userwords_str = "\n".join([f'{word} n' for word in userwords])
    file_db.set("stopwords", stopwords)
    file_db.set("userwords", userwords)
    # 用户词设置给jieba
    userwords_file = io.StringIO(userwords_str)
    jieba.load_userdict(userwords_file)
    last_userwords = userwords
    jieba_inited = True
    logger.info(f'jieba已重置 用户词数:{len(userwords)} 停用词数:{len(stopwords)}')

# jieba初始化
def init_jieba():
    global jieba_inited
    if not jieba_inited: reset_jieba()

# 绘制词云图 返回图片和前WORD_TOPK个词的前WORD_USER_TOPK个用户以及他们的比例文本
def draw_wordcloud(gid, date_str, recs, users, names) -> Tuple[Image.Image, str]:
    logger.info(f"开始绘制词云图")
    init_jieba()

    userwords = set(file_db.get("userwords", []))
    stopwords = set(file_db.get("stopwords", []))

    all_words = { " ": 1 }
    word_user_count = {} # word_user_count[word][user] = count

    for rec in recs:
        msg = extract_text(rec['msg'])
        words = pseg.cut(msg)
        nouns = []
        for word, flag in words:
            if word in userwords:
                nouns.append(word)
            elif flag.startswith('n') and word not in stopwords and len(word) > 1:  
                nouns.append(word)
        for noun in nouns:
            if noun not in all_words:
                all_words[noun] = 0
                word_user_count[noun] = {}
            all_words[noun] += 1
            user = rec['user_id']
            if user not in word_user_count[noun]:
                word_user_count[noun][user] = 0
            word_user_count[noun][user] += 1

    WORD_TOPK = 3
    WORD_USER_TOPK = 5    

    # 统计前WORD_TOPK个词的前WORD_USER_TOPK个用户以及他们的比例(结果为topk_word_user=[[(user, rate), ...], ...])
    topk_words = sorted(all_words.items(), key=lambda x: x[1], reverse=True)[:WORD_TOPK]
    topk_words = [word for word, _ in topk_words if word != " "]
    topk_word_user = {}
    for word in topk_words:
        topk_word_user[word] = sorted(word_user_count[word].items(), key=lambda x: x[1], reverse=True)[:WORD_USER_TOPK]
        topk_word_user[word] = [(user, count/all_words[word]) for user, count in topk_word_user[word]]

    FONT_SIZE_MAX = 50
    FONT_SIZE_MIN = 10
    WC_W = 400
    WC_H = 200

    main_h = get_theme_color_info(gid, date_str)["hue"]

    # 随机颜色
    def random_color(word, font_size, position, orientation, random_state=None, **kwargs):
        l = 1.0 - (font_size - FONT_SIZE_MIN) / (FONT_SIZE_MAX - FONT_SIZE_MIN)
        l = 0.4 + l * 0.5
        h = main_h + random.uniform(-0.05, 0.05)
        h = h % 1.0
        s = 1.0 - l
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        r = int(r * 255)
        g = int(g * 255)
        b = int(b * 255)
        return f'rgb({r}, {g}, {b})'

    wc = wordcloud.WordCloud(
        font_path=FONT_PATH,
        background_color=None,
        width=WC_W,
        height=WC_H,
        max_words=100,
        max_font_size=FONT_SIZE_MAX,
        min_font_size=FONT_SIZE_MIN,
        random_state=42,
        color_func=random_color,
        mode='RGBA',
    )

    wc.generate_from_frequencies(all_words)
    img = wc.to_image()

    # 前WORD_TOPK个词的前WORD_USER_TOPK个用户以及他们的比例
    text = ""
    for i in range(len(topk_words)):
        word = topk_words[i]
        text += f"[{word}]  "
        fst = True
        for j in range(WORD_USER_TOPK):
            if j >= len(topk_word_user[word]):
                break
            user, rate = topk_word_user[word][j]
            name = ""
            for k in range(len(users)):
                if users[k] == user:
                    name = names[k]
                    break
            if name == "": continue
            name = truncate(name, 6)
            if fst: fst = False
            else: text += " | "
            text += f"{name}({int(rate * 100)}%)"
        if i != len(topk_words) - 1: text += "\n"

    return img, text


# 绘制所有图
def draw_all(gid, recs, interval, topk1, topk2, user, name, path, date_str):
    logger.info(f"开始绘制所有图到{path}")
    plt.subplots_adjust(wspace=0.0, hspace=0.0)

    pie_image = draw_pie(gid, date_str, recs, user[:topk1], name[:topk1])

    fig, ax = plt.subplots(figsize=(8, 4), nrows=1, ncols=1)
    fig.tight_layout()
    draw_plot(gid, date_str, ax, recs, interval, user[:topk2], name[:topk2])
    plot_image = plt_fig_to_image(fig)

    wordcloud_image, word_rank_text = draw_wordcloud(gid, date_str, recs, user, name)

    c1, c2 = get_theme_color_info(gid, date_str)["colors"]
    bg_color = LinearGradient(c1=c1, c2=c2, p1=(1, 1), p2=(0, 0))
    with Canvas(bg=FillBg(bg_color)).set_padding(10) as canvas:
        with VSplit().set_sep(10).set_padding(10):
            bg = RoundRectBg(fill=(255, 255, 255, 200), radius=10)

            title = TextBox(f"{date_str} 群聊消息统计 总消息数: {len(recs)}条")
            title.set_bg(bg).set_padding(10).set_w(850)
            title.set_style(TextStyle(size=24, color=(0, 0, 0, 255), font=DEFAULT_FONT))

            ImageBox(pie_image, image_size_mode='fit', use_alphablend=True).set_bg(bg).set_w(850)
            ImageBox(wordcloud_image, image_size_mode='fit', use_alphablend=True).set_bg(bg).set_padding(32).set_w(850)

            wrt = TextBox(word_rank_text, line_count=3)
            wrt.set_bg(bg).set_padding(16).set_w(850)
            wrt.set_style(TextStyle(size=20, color=(100, 100, 100, 255), font=DEFAULT_FONT))

            ImageBox(plot_image, image_size_mode='fit', use_alphablend=True).set_bg(bg).set_padding(16).set_w(850)

    canvas.get_img().save(path)
    logger.info(f"绘制完成")


# 绘制群总聊天数关于时间的折线图 
def draw_date_count_plot(dates, counts, path, user_counts=None):
    logger.info(f"开始绘制群总聊天数关于时间的折线图到{path}")
    plt.figure(figsize=(8, 4))
    plt.bar(dates, counts, label='其他消息数', color='#bbbbbb', width=1)
    if user_counts is not None:
        plt.bar(dates, user_counts, label='用户消息数', color='#dddddd', width=1)
    plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    plt.xlabel('日期')
    plt.ylabel('消息总数')
    plt.xticks(fontsize=8)
    plt.yticks(fontsize=8)
    plt.legend(fontsize=8)
    plt.savefig(path)
    plt.close()
    logger.info(f"绘制完成")
    

# 绘制词汇统计
def draw_word_count_plot(dates, topk_user, topk_name, user_counts, user_date_counts, word, path):
    logger.info(f"开始绘制词汇统计到{path}")

    k, n = len(topk_user), len(dates)
    other_users = [user for user in user_counts.keys() if user not in topk_user]

    plt.figure(figsize=(8, 8))
    ax1 = plt.subplot(211)
    ax2 = plt.subplot(212)

    topk_user_count = [user_counts[user_id] for user_id in topk_user]
    topk_user_count += [sum([user_counts[user_id] for user_id in other_users])]
    labels = [f'{topk_name[i]} ({topk_user_count[i]})' for i in range(k)]
    labels += [f'其他 ({topk_user_count[k]})']
    ax1.pie(topk_user_count, labels=labels, autopct='%1.1f%%', shadow=False, startangle=90)

    date_topk_count = [[user_date_counts[i][user_id] for i in range(n)] for user_id in topk_user]
    date_topk_count += [[sum([user_date_counts[i][user_id] for user_id in other_users]) for i in range(n)]]
    bottom = [0] * n
    for i in range(k):
        ax2.bar(dates, date_topk_count[i], label=topk_name[i], bottom=bottom, width=1)
        bottom = [bottom[j] + date_topk_count[i][j] for j in range(n)]
    ax2.bar(dates, date_topk_count[k], label='其他', bottom=bottom, width=1)
    ax2.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax2.legend(fontsize=8)
    ax2.set_xlabel('日期')
    ax2.set_ylabel(f'消息数')
    plt.xticks(fontsize=8)
    plt.yticks(fontsize=8)
    plt.tight_layout()
    plt.savefig(path)
    plt.close()
    logger.info(f"绘制完成")


# 绘制长时间统计的群总聊天数关于时间的折线图
def draw_long_sta_date_count_plot(gid, date_str, ax: plt.Axes, topk_user, topk_name, recs):
    logger.info(f"开始绘制长时间统计的群总聊天数关于时间的折线图")

    # 计算起止时间
    start_date = recs[0]['time']
    end_date = recs[-1]['time']
    dates = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]

    # 计算每日消息数
    counts = [0] * len(dates)
    for rec in recs:
        date = rec['time']
        index = (date - start_date).days
        counts[index] += 1

    # 计算topk用户的每日消息数
    user_counts = [[0] * len(dates) for _ in range(len(topk_user))]
    for rec in recs:
        user_id = rec['user_id']
        if user_id not in topk_user: continue
        date = rec['time']
        index = (date - start_date).days
        user_counts[topk_user.index(user_id)][index] += 1

    # 绘制图
    # cmap = get_cmap(gid, date_str)
    ax.bar(dates, counts, label='日消息数', color='#bbbbbb', width=1)
    # for i in range(len(topk_user)):
    #     ax.plot(dates, user_counts[i], label=topk_name[i], color=cmap[i])

    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax.legend(fontsize=8)


# 绘制所有图（长时间统计版本）
def draw_all_long(gid, recs, interval, topk1, topk2, user, name, path, date_str):
    logger.info(f"开始绘制所有图到{path}")
    plt.subplots_adjust(wspace=0.0, hspace=0.0)

    pie_image = draw_pie(gid, date_str, recs, user[:topk1], name[:topk1])

    fig, ax = plt.subplots(figsize=(8, 4), nrows=1, ncols=1)
    fig.tight_layout()
    draw_plot(gid, date_str, ax, recs, interval, user[:topk2], name[:topk2])
    plot_image = plt_fig_to_image(fig)

    fig, ax = plt.subplots(figsize=(8, 5), nrows=1, ncols=1)
    fig.tight_layout()
    draw_long_sta_date_count_plot(gid, date_str, ax, user[:topk2], name[:topk2], recs)
    date_count_image = plt_fig_to_image(fig)

    wordcloud_image, word_rank_text = draw_wordcloud(gid, date_str, recs, user, name)

    c1, c2 = get_theme_color_info(gid, date_str)["colors"]
    bg_color = LinearGradient(c1=c1, c2=c2, p1=(1, 1), p2=(0, 0))
    with Canvas(bg=FillBg(bg_color)).set_padding(10) as canvas:
        with VSplit().set_sep(10).set_padding(10):
            bg = RoundRectBg(fill=(255, 255, 255, 200), radius=10)

            title = TextBox(f"{date_str} 群聊消息统计 总消息数: {len(recs)}条")
            title.set_bg(bg).set_padding(10).set_w(850 + 850 + 10)
            title.set_style(TextStyle(size=24, color=(0, 0, 0, 255), font=DEFAULT_FONT))

            with HSplit().set_sep(10):
                with VSplit().set_sep(10):
                    ImageBox(pie_image, image_size_mode='fit', use_alphablend=True).set_bg(bg).set_w(850)
                    ImageBox(wordcloud_image, image_size_mode='fit', use_alphablend=True).set_bg(bg).set_padding(32).set_w(850)

                    wrt = TextBox(word_rank_text, line_count=3)
                    wrt.set_bg(bg).set_padding(16).set_w(850)
                    wrt.set_style(TextStyle(size=20, color=(100, 100, 100, 255), font=DEFAULT_FONT))
                
                with VSplit().set_sep(10):
                    ImageBox(plot_image, image_size_mode='fit', use_alphablend=True).set_bg(bg).set_padding(16).set_w(850)
                    ImageBox(date_count_image, image_size_mode='fit', use_alphablend=True).set_bg(bg).set_padding(16).set_w(850)

    canvas.get_img().save(path)
    logger.info(f"绘制完成")
