from ..utils import *
from datetime import datetime, timedelta
import matplotlib
import matplotlib.pyplot as plt
from .sql import get_range

config = get_config('chat')
logger = get_logger("Chat")

PER_USER_USAGE_TOPK = config['per_user_usage_topk']

PLT_SAVE_PATH = "data/chat/tmp/usage.jpg"

plt.switch_backend('agg')
matplotlib.rcParams['font.sans-serif']=[get_config('font_name')]
matplotlib.rcParams['axes.unicode_minus']=False   


def draw(start_time, end_time):
    if start_time is None:  start_time = datetime(1970, 1, 1)
    if end_time is None:    end_time = datetime.now()
    logger.info(f"开始绘制token使用统计图: {start_time} - {end_time}")
    recs = get_range(start_time, end_time)

    if len(recs) == 0: return None, "无使用记录"

    query_total, autochat_total = 0, 0
    per_user_usage, per_group_usage, autochat_usage = Counter(), Counter(), Counter()

    for rec in recs:
        cost = rec['cost']
        if rec['type'] == 'chat_auto':
            autochat_usage.inc(str(rec['group_id']), cost)
            autochat_total += cost
        else:
            if rec['user_id'] is not None:
                per_user_usage.inc(str(rec['user_id']), cost)
            if rec['group_id'] is not None:
                per_group_usage.inc(str(rec['group_id']), cost)
            query_total += cost
        
    per_user_usage = sorted(per_user_usage.items(), key=lambda x: x[1], reverse=True)
    per_user_usage_x = [x[0] for x in per_user_usage[:PER_USER_USAGE_TOPK]] + ['其他']
    per_user_usage_y = [x[1] for x in per_user_usage[:PER_USER_USAGE_TOPK]] + [sum([x[1] for x in per_user_usage[PER_USER_USAGE_TOPK:]])]
    for i in range(len(per_user_usage_y)):
        per_user_usage_x[i] += f"\n({per_user_usage_y[i]:.4f})"

    per_group_usage = sorted(per_group_usage.items(), key=lambda x: x[1], reverse=True)
    per_group_usage_x = [x[0] for x in per_group_usage]
    per_group_usage_y = [x[1] for x in per_group_usage]
    for i in range(len(per_group_usage_y)):
        per_group_usage_x[i] += f"\n({per_group_usage_y[i]:.4f})"

    autochat_usage = sorted(autochat_usage.items(), key=lambda x: x[1], reverse=True)
    autochat_usage_x = [x[0] for x in autochat_usage]
    autochat_usage_y = [x[1] for x in autochat_usage]
    for i in range(len(autochat_usage_y)):
        autochat_usage_x[i] += f"\n({autochat_usage_y[i]:.4f})"

    # 绘制三个饼图，分别是群组使用，用户使用，自动聊天使用
    fig, axs = plt.subplots(1, 3, figsize=(15, 5))
    axs[0].pie(per_group_usage_y, labels=per_group_usage_x, autopct='%1.1f%%') 
    axs[1].pie(per_user_usage_y, labels=per_user_usage_x, autopct='%1.1f%%') 
    axs[2].pie(autochat_usage_y, labels=autochat_usage_x, autopct='%1.1f%%') 
    axs[0].set_title('群组使用')
    axs[1].set_title('用户使用')
    axs[2].set_title('自动聊天使用')

    plt.tight_layout()
    # 保存图片
    os.makedirs(os.path.dirname(PLT_SAVE_PATH), exist_ok=True)
    plt.savefig(PLT_SAVE_PATH)

    logger.info(f"token使用统计图绘制完成: {PLT_SAVE_PATH}")

    total = query_total + autochat_total
    desc = f"总使用量: {total:.4f}\n"
    if total > 0:
        desc += f"询问使用量: {query_total:.4f}({int(query_total/total*100)}%)\n"
        desc += f"自动聊天使用量: {autochat_total:.4f}({int(autochat_total/total*100)}%)\n"

    return PLT_SAVE_PATH, desc



