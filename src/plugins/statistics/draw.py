from matplotlib import pyplot as plt
from datetime import datetime, timedelta
import matplotlib.dates as mdates
import matplotlib
import jieba
import jieba.posseg as pseg
import wordcloud
import re
import random
import colorsys
import io
from ..utils import *

config = get_config("statistics")
logger = Logger("Sta")
file_db = FileDB("data/statistics/db.json", logger)

IMG_STR = "[CQ:image,"
FONT_PATH = config['font_path'] 

plt.switch_backend('agg')
matplotlib.rcParams['font.sans-serif']=[config['font_name']]
matplotlib.rcParams['axes.unicode_minus']=False   


# 绘制饼图
def draw_pie(ax, rows, topk_user, topk_name):
    logger.log(f"开始绘制饼图")
    topk = len(topk_user)
    user_count, user_image_count = Counter(), Counter()
    for row in rows:
        msg_id, user = row[0], row[1]
        user_count.inc(user)
        if IMG_STR in row[4]: user_image_count.inc(user)
    sorted_user_count = sorted(user_count.items(), key=lambda x: x[1], reverse=True)

    topk_user = [user for user, _ in sorted_user_count[:topk]]
    topk_user_count = [count for _, count in sorted_user_count[:topk]]
    topk_user.append("其他")
    topk_user_count.append(sum([count for _, count in sorted_user_count[topk:]]))
    other_image_count = sum([user_image_count.get(user) for user in user_count.keys() if user not in topk_user])
    labels = [f'{topk_name[i]} ({topk_user_count[i]},{user_image_count.get(topk_user[i])})' for i in range(topk)] 
    labels += [f'其他 ({topk_user_count[topk]},{other_image_count})']

    current_date = datetime.now().strftime("%Y-%m-%d")
    ax.text(-0.4, 0.98, f"{current_date} 今日消息总数：{len(rows)}", fontsize=12, transform=ax.transAxes)
    ax.pie(topk_user_count, labels=labels, autopct='%1.1f%%', shadow=False, startangle=90)


# 绘制折线图
def draw_plot(ax, rows, interval, topk_user, topk_name):
    logger.log(f"开始绘制折线图")
    topk = len(topk_user)
    cnts = [[0] * int(24*60/interval) for _ in range(topk + 1)]
    all = [0] * int(24*60/interval)
    img_all = [0] * int(24*60/interval)

    for row in rows:
        date = row[3]
        time = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        minute = time.hour * 60 + time.minute
        index = int(minute / interval)
        if row[1] in topk_user:
            cnts[topk_user.index(row[1])][index] += 1
        else:
            cnts[-1][index] += 1
        all[index] += 1
        if IMG_STR in row[4]:
            img_all[index] += 1

    x = [datetime.strptime("00:00", "%H:%M") + timedelta(minutes=interval*i) for i in range(int(24*60/interval))]

    ax.bar(x[1:-1], all[1:-1], width=timedelta(minutes=interval), align='edge', color='#bbbbbb')
    ax.bar(x[1:-1], img_all[1:-1], width=timedelta(minutes=interval), align='edge', color='#dddddd')

    for i in range(0, topk):
        offset = timedelta(minutes=interval) / 2
        tx = [xi + offset for xi in x[1:-1]]
        ax.plot(tx, cnts[i][1:-1], label=topk_name[i], linewidth=0.7)

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
    logger.log(f'jieba已重置 用户词数:{len(userwords)} 停用词数:{len(stopwords)}')

# jieba初始化
def init_jieba():
    global jieba_inited
    if not jieba_inited: reset_jieba()


# 绘制词云图
def draw_wordcloud(ax, rows, users, names):
    logger.log(f"开始绘制词云图")
    init_jieba()

    userwords = set(file_db.get("userwords", []))
    stopwords = set(file_db.get("stopwords", []))

    all_words = { " ": 1 }
    word_user_count = {} # word_user_count[word][user] = count

    for row in rows:
        msg = row[4]
        msg = re.sub(r'\[CQ:.*?\]', '', msg)
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
            user = row[1]
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

    main_h = random.uniform(0.0, 1.0)

    # 随机颜色
    def random_color(word, font_size, position, orientation, random_state=None, **kwargs):
        l = 1.0 - (font_size - FONT_SIZE_MIN) / (FONT_SIZE_MAX - FONT_SIZE_MIN)
        l = 0.4 + l * 0.6
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
        background_color='white',
        width=WC_W,
        height=WC_H,
        max_words=100,
        max_font_size=FONT_SIZE_MAX,
        min_font_size=FONT_SIZE_MIN,
        random_state=42,
        color_func=random_color,
    )

    wc.generate_from_frequencies(all_words)
    ax.imshow(wc)
    ax.axis('off')

    # 左下角写出前WORD_TOPK个词的前WORD_USER_TOPK个用户以及他们的比例
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
            name = get_shortname(name, 6)
            if fst: fst = False
            else: text += " | "
            text += f"{name}({int(rate * 100)}%)"
        if i != len(topk_words) - 1: text += "\n"
    ax.text(0.0, -0.18, text, fontsize=12, transform=ax.transAxes, color='#bbbbbb')


# 绘制所有图
def draw_all(rows, interval, topk1, topk2, user, name, path):
    logger.log(f"开始绘制所有图到{path}")
    plt.subplots_adjust(wspace=0.0, hspace=0.0)
    fig, ax = plt.subplots(figsize=(8, 15), nrows=3, ncols=1)
    fig.tight_layout()

    draw_pie(ax[0], rows, user[:topk1], name[:topk1])
    draw_plot(ax[2], rows, interval, user[:topk2], name[:topk2])
    draw_wordcloud(ax[1], rows, user, name)

    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.savefig(path)
    logger.log(f"绘制完成")