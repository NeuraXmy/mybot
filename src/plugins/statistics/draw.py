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

FONT_PATH = get_config('font_path')
FONT_NAME = get_config('font_name')

plt.switch_backend('agg')
matplotlib.rcParams['font.sans-serif']=[FONT_NAME]
matplotlib.rcParams['axes.unicode_minus']=False   


# 绘制饼图
def draw_pie(ax, recs, topk_user, topk_name):
    logger.info(f"开始绘制饼图")
    topk = len(topk_user)
    user_count, user_image_count = Counter(), Counter()
    for rec in recs:
        user_count.inc(rec['user_id'])
        if has_image(rec['msg']):
            user_image_count.inc(rec['user_id'])
    sorted_user_count = sorted(user_count.items(), key=lambda x: x[1], reverse=True)

    topk_user = [user for user, _ in sorted_user_count[:topk]]
    topk_user_count = [count for _, count in sorted_user_count[:topk]]
    topk_user.append("其他")
    topk_user_count.append(sum([count for _, count in sorted_user_count[topk:]]))
    other_image_count = sum([user_image_count.get(user) for user in user_count.keys() if user not in topk_user])
    labels = [f'{topk_name[i]} ({topk_user_count[i]},{user_image_count.get(topk_user[i])})' for i in range(topk)] 
    labels += [f'其他 ({topk_user_count[topk]},{other_image_count})']

    current_date = datetime.now().strftime("%Y-%m-%d")
    ax.text(-0.4, 0.98, f"{current_date} 今日消息总数：{len(recs)}", fontsize=12, transform=ax.transAxes)
    ax.pie(topk_user_count, labels=labels, autopct='%1.1f%%', shadow=False, startangle=90)


# 绘制折线图
def draw_plot(ax, recs, interval, topk_user, topk_name):
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
    logger.info(f'jieba已重置 用户词数:{len(userwords)} 停用词数:{len(stopwords)}')

# jieba初始化
def init_jieba():
    global jieba_inited
    if not jieba_inited: reset_jieba()


# 绘制词云图
def draw_wordcloud(ax, recs, users, names):
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
            name = truncate(name, 6)
            if fst: fst = False
            else: text += " | "
            text += f"{name}({int(rate * 100)}%)"
        if i != len(topk_words) - 1: text += "\n"
    ax.text(0.0, -0.18, text, fontsize=12, transform=ax.transAxes, color='#bbbbbb')


# 绘制所有图
def draw_all(recs, interval, topk1, topk2, user, name, path):
    logger.info(f"开始绘制所有图到{path}")
    plt.subplots_adjust(wspace=0.0, hspace=0.0)
    fig, ax = plt.subplots(figsize=(8, 15), nrows=3, ncols=1)
    fig.tight_layout()

    draw_pie(ax[0], recs, user[:topk1], name[:topk1])
    draw_plot(ax[2], recs, interval, user[:topk2], name[:topk2])
    draw_wordcloud(ax[1], recs, user, name)

    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.savefig(path)
    plt.close()
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