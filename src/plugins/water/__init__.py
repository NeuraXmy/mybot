from ..utils import *
from ..record import before_record_hook, after_record_hook
from .sql import insert_hash, query_by_hash, query_by_unique_id
from asyncio import CancelledError, Queue

config = get_config("water")
logger = get_logger("Water")
file_db = get_file_db("data/water/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'water')

autowater_gwls = {
    t: get_group_white_list(file_db, logger, f'autowater_{t}', is_service=False)
    for t in ['text', 'image', 'stamp', 'json', 'video', 'forward']
}
autowater_type_desc = {
    'text': '文本',
    'image': '图片',
    'stamp': '表情',
    'json': '分享消息',
    'video': '视频',
    'forward': '聊天记录',
}
autowater_levels = {
    'none': [],
    'all': ['text', 'image', 'stamp', 'json', 'video', 'forward'],
    'low': ['forward', 'json'],
    'med': ['video', 'forward', 'json'],
    'high': ['image', 'video', 'forward', 'json'],
}

# 计算图片的phash
async def calc_phash(image_url):
    # 从网络下载图片
    image = await download_image(image_url)
    def calc(image):
        # 缩小尺寸
        image = image.resize((8, 8)).convert('L')
        # 计算平均值
        avg = sum(list(image.getdata())) / 64
        # 比较像素的灰度
        hash = 0
        for i, a in enumerate(list(image.getdata())):
            hash += 1 << i if a >= avg else 0
        return str(hash)
    return await run_in_pool(calc, image)

# 图片phash到字符画
def phash_to_strmap(phash):
    phash = int(phash)
    phash_map = [[0 for _ in range(8)] for _ in range(8)]
    for i in range(8):
        for j in range(8):
            phash_map[i][j] = (phash >> (i * 8 + j)) & 1
    phash_map = "\n".join(["".join([str(x) for x in row]) for row in phash_map])
    return phash_map

# 计算消息中的所有hash
async def get_hash_from_msg(group_id, msg, types=None):
    def check_type(t):
        return not types or t in types

    # 消除at和reply
    msg = [seg for seg in msg if seg['type'] not in ['at', 'reply']]

    # 纯文本
    if len(msg) == 1 and msg[0]['type'] == 'text':
        if not check_type('text'): return []
        return [{
            'type': 'text', 
            'hash': get_md5(msg[0]['data']['text']), 
            'brief': f"\"{truncate(msg[0]['data']['text'], 10)}\"",
            "original": msg[0],
        }]

    ret = []
    type_total = {}

    for seg in msg:
        stype, sdata = seg['type'], seg['data']
        if stype not in type_total:
            type_total[stype] = 0
        type_total[stype] += 1

        # 图片
        if stype == 'image':
            subtype = sdata.get('sub_type', 0)
            if 'summary' in sdata:
                subtype = 1
            if subtype == 0 and not check_type('image'): continue
            if subtype == 1 and not check_type('stamp'): continue

            # 查找之前有没有计算过phash
            file_unique = sdata.get('file_unique', "")
            phash = None
            if file_unique:
                if rec := await query_by_unique_id(group_id, 'image', file_unique):
                    phash = rec[0]['hash']
            # 没有计算过则计算phash
            if not phash:
                phash = await calc_phash(sdata['url'])
            ret.append({
                'type': 'image', 
                'hash': phash, 
                'sub_type': subtype, 
                'file_unique': file_unique,
                'brief': f"图片#{type_total[stype]}",
                'original': seg,
            })
        # 视频
        elif stype == 'video':
            if not check_type('video'): continue
            ret.append({
                'type': 'video', 
                'hash': sdata['file'],
                'brief': f"视频#{type_total[stype]}",
                'original': seg,
            })
        # 转发
        elif stype == 'forward':
            if not check_type('forward'): continue
            try:
                bot = get_bot()
                raw = ""
                for forward_msg in (await get_forward_msg(bot, sdata['id']))['messages']:
                    raw += f"{forward_msg['user_id']} {forward_msg['time']}: "
                    for fmseg in forward_msg['message']:
                        ftype, fdata = fmseg['type'], fmseg['data']
                        if ftype == 'text':
                            raw += fdata['text']
                        else:
                            raw += f"[{ftype}]"
                    raw += "\n"
                ret.append({
                    'type': 'forward', 
                    'hash': get_md5(raw),
                    'brief': f"聊天记录#{type_total[stype]}",
                    'original': seg,
                })
            except Exception as e:
                logger.warning(f'获取转发消息hash失败: {e}')
        # json
        elif stype == 'json':
            if not check_type('json'): continue
            data = json.loads(sdata['data'])

            # 属于转发消息的json
            if data.get('app') == 'com.tencent.multimsg':
                type_total['json'] -= 1
                if 'forward' not in type_total:
                    type_total['forward'] = 0
                type_total['forward'] += 1

                uniseq = data['meta']['detail']['uniseq']
                ret.append({
                    'type': 'forward', 
                    'hash': uniseq,
                    'brief': f"聊天记录#{type_total['forward']}",
                    'original': seg,
                })

            elif 'prompt' in data:
                prompt = data['prompt']
                if '张图片至群相册' in prompt:
                    continue
                view = data.get('view', "")
                meta = data.get('meta', "")
                ret.append({
                    'type': 'json', 
                    'hash': get_md5(prompt + view + str(meta)),
                    'brief': f"分享消息#{type_total[stype]}",
                    'original': seg,
                })
    return ret

# 获取消息的水果数据
async def get_hashes_water_info(group_id, msg_id, hashes):
    ret = []
    for h in hashes:
        recs = await query_by_hash(group_id, h['type'], h['hash'])
        recs = [rec for rec in sorted(recs, key=lambda x: x['time']) if rec['msg_id'] != msg_id]    # 排序并去掉查询的消息本身
        fst, lst, topk_users = None, None, None
        if recs:
            fst, lst = recs[0], recs[-1]
            # 统计水果用户比例
            TOP_K = 5
            user_count, user_nickname = {}, {}
            for rec in recs:
                uid, nickname = rec['user_id'], rec['nickname']
                user_nickname[uid] = nickname
                if uid not in user_count:
                    user_count[uid] = 0
                user_count[uid] += 1
            topk_uids = sorted(user_count.items(), key=lambda x: x[1], reverse=True)[:TOP_K]
            topk_users = [{
                'uid': uid,
                'nickname': user_nickname[uid],
                'cnt': cnt,
                'ratio': cnt/len(recs)*100,
            } for uid, cnt in topk_uids]
        ret.append({
            'hash': h,
            'recs': recs,
            'topk_users': topk_users,
            'fst': fst,
            'lst': lst,
        })
    return ret


# ------------------------------------------ 聊天逻辑 ------------------------------------------ #

water = CmdHandler(['/water', '/watered', '/水果'], logger)
water.check_group().check_wblist(gbl).check_cdrate(cd)
@water.handle()
async def _(ctx: HandlerContext):
    reply_msg_obj = await ctx.aget_reply_msg_obj()
    assert_and_reply(reply_msg_obj, "请回复一条消息")
    reply_msg_id = reply_msg_obj['message_id']
    reply_msg = reply_msg_obj['message']
    group_id = ctx.group_id

    hashes = await get_hash_from_msg(group_id, reply_msg)
    water_info = await get_hashes_water_info(group_id, reply_msg_id, hashes)
    res = ''
    for item in water_info:
        hash, recs, topk_users, fst, lst = item['hash'], item['recs'], item['topk_users'], item['fst'], item['lst']
        logger.info(f"水果查询: {hash['brief']} 匹配到 {len(recs)} 条记录")

        if not recs:
            res += f"{hash['brief']} 没有水果\n"
            continue
        
        if len(recs) > 1:
            res = f"{hash['brief']} 水果总数：{len(recs)}\n"
            res += f"[最早水果]\n{get_readable_datetime(fst['time'])}\nby {fst['nickname']}({fst['user_id']})\n"
            res += f"[上次水果]\n{get_readable_datetime(lst['time'])}\nby {lst['nickname']}({lst['user_id']})\n"
            res += f"[水果比例]\n"
            for u in topk_users:
                res += f"{u['nickname']}({u['uid']}) {u['ratio']:.2f}%\n"
        else:
            res = f"{hash['brief']} 水果总数：{len(recs)}\n"
            res += f"上次：{get_readable_datetime(fst['time'])}\nby {fst['nickname']}({fst['user_id']})\n"

    return await ctx.asend_reply_msg(res.strip())


query_hash = CmdHandler(['/hash'], logger)
query_hash.check_group().check_cdrate(cd).check_wblist(gbl)
@query_hash.handle()
async def _(ctx: HandlerContext):
    reply_msg = await ctx.aget_reply_msg()
    assert_and_reply(reply_msg, "请回复一条消息")
    hashes = await get_hash_from_msg(ctx.group_id, reply_msg)
    msg = ''
    for h in hashes:
        if h['type'] != 'text':
            msg += f"【{h['brief']}】\n"
        msg += f"type={h['type']}\n"
        msg += f"hash={h['hash']}\n"
        if h['type'] == 'image':
            msg += f"sub_type={'图片' if h['sub_type'] == 0 else '表情'}\n"
            msg += f"file_unique={h['file_unique']}\n"
            msg += phash_to_strmap(h['hash'])+ '\n'
    return await ctx.asend_fold_msg_adaptive(msg.strip())

autowater = CmdHandler(['/autowater', '/自动水果'], logger)
autowater.check_group().check_wblist(gbl).check_superuser()
@autowater.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    types = None
    for level, ts in autowater_levels.items():
        if args == level:
            types = ts
            break
    if types is None:
        types = args.split()
    group_id = ctx.group_id
    for t, gwl in autowater_gwls.items():
        if t in types:
            gwl.add(group_id)
        else:
            gwl.remove(group_id)   
    if types:
        return await ctx.asend_reply_msg(f"设置本群的自动水果检测目标:\n{' '.join([autowater_type_desc[t] for t in types])}")
    else:
        return await ctx.asend_reply_msg("关闭本群的自动水果检测")

water_exclude = CmdHandler(['/water_exclude', '/watered_exclude', '/水果排除'], logger)
water_exclude.check_group().check_wblist(gbl)
@water_exclude.handle()
async def _(ctx: HandlerContext):
    reply_msg = await ctx.aget_reply_msg()
    group_id = ctx.group_id
    if reply_msg:
        hashes = await get_hash_from_msg(group_id, reply_msg)

        ret = "在当前群聊排除以下hash的自动水果检测:\n"
        excluded_hashes = file_db.get('excluded_hashes', {})
        if str(group_id) not in excluded_hashes:
            excluded_hashes[str(group_id)] = []
        for h in hashes:
            hs = f"[{h['type']}] {h['hash']}"
            excluded_hashes[str(group_id)].append(hs)
            ret += hs + '\n'
        file_db.set('excluded_hashes', excluded_hashes)

        return await ctx.asend_reply_msg(ret.strip())
    else:
        cqs = extract_cq_code(reply_msg)
        ats = cqs.get('at', [])
        assert_and_reply(ats, "请回复一条消息或者at用户")

        ret = "在当前群聊排除以下用户的自动水果检测:\n"
        excluded_users = file_db.get('excluded_users', {})
        if str(group_id) not in excluded_users:
            excluded_users[str(group_id)] = []
        for at in ats:
            uid = at['qq']
            if uid not in excluded_users[str(group_id)]:
                excluded_users[str(group_id)].append(uid)
                ret += f"{uid}\n"
        file_db.set('excluded_users', excluded_users)
    

# ------------------------------------------ Hash记录 ------------------------------------------ #

task_queue = Queue()
MAX_TASK_NUM = 50

# 添加HASH记录任务
@before_record_hook
async def record_new_message(bot, event):
    if not is_group_msg(event): return
    group_id = event.group_id
    msg_obj = await get_msg_obj(bot, event.message_id)
    nickname = await get_group_member_name(bot, group_id, event.user_id)
    task_queue.put_nowait({
        'msg_id': event.message_id,
        'time': event.time,
        'group_id': group_id,
        'user_id': event.user_id,
        'nickname': nickname,
        'msg': msg_obj['message'],
    })

# HASH记录任务任务处理
@async_task('Hash记录', logger)
async def handle_task():
    while True:
        while task_queue.qsize() > MAX_TASK_NUM:
            task_queue.get_nowait()
            logger.info(f'任务队列大小超过限制: {task_queue.qsize()}>{MAX_TASK_NUM} 丢弃任务')
        try:
            task = await task_queue.get()
        except CancelledError:
            break
        if not task: break 

        try:
            hashes = await get_hash_from_msg(task['group_id'], task['msg'])
            for hash in hashes:
                await insert_hash(
                    group_id=task['group_id'],
                    type=hash['type'],
                    hash=hash['hash'],
                    msg_id=task['msg_id'],
                    user_id=task['user_id'],
                    nickname=task['nickname'],
                    time=task['time'],
                    unique_id=hash.get('file_unique', ""),
                )
                logger.debug(f'添加hash记录: {task["msg_id"]} {hash["type"]} {hash["hash"]}')

        except Exception as e:
            logger.print_exc(f'记录消息 {task["msg_id"]} 的Hash失败')


# ------------------------------------------ 自动水果 ------------------------------------------ #

@after_record_hook
async def check_auto_water(bot: Bot, event: MessageEvent):
    if not is_group_msg(event): return

    if event.user_id == int(bot.self_id): return
    excluded_users = set(file_db.get('excluded_users', {}).get(str(event.group_id), []))
    if event.user_id in excluded_users: return

    await asyncio.sleep(1)

    group_id = event.group_id
    check_types = {t for t, gwl in autowater_gwls.items() if gwl.check_id(group_id)}
    if not check_types: return

    msg = await get_msg(bot, event.message_id)
    hashes = await get_hash_from_msg(group_id, msg, check_types)
    all_water_info = await get_hashes_water_info(group_id, event.message_id, hashes)

    # 过滤没有水果和排除的hash
    excluded_hashes = set(file_db.get('excluded_hashes', {}).get(str(group_id), []))
    water_info = []
    for item in all_water_info:
        hash = item['hash']
        if not item['recs']: continue
        if f"[{hash['type']}] {hash['hash']}" in excluded_hashes: continue
        water_info.append(item)

    if not water_info: return
    logger.info(f"自动水果检测: 群聊 {group_id} 消息 {event.message_id} 的 {len(water_info)} 个片段检测到水果")

    res = ""
    for item in water_info:
        hash, recs, topk_users, fst, lst = item['hash'], item['recs'], item['topk_users'], item['fst'], item['lst']
        htype, brief, original_seg = hash['type'], hash['brief'], hash['original']
        if len(water_info) > 1:
            res += brief
        nickname = await get_group_member_name(bot, group_id, int(fst['user_id']))
        res += f"已经水果{len(recs)}次！最早于{get_readable_datetime(fst['time'], show_original_time=False)}被 @{nickname} 水果\n"
    
    if res:
        res = f"[CQ:reply,id={event.message_id}]{res.strip()}"
        await send_group_msg_by_bot(bot, group_id, res)

    
