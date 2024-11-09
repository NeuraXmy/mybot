from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.message import Message
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.params import CommandArg
from ..utils import *


config = get_config('broadcast')
logger = get_logger("Broadcast")
file_db = get_file_db("data/broadcast/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'broadcast')


def get_guid(ctx: HandlerContext) -> str:
    if ctx.group_id:
        return f"group_{ctx.group_id}"
    else:
        return f"private_{ctx.user_id}"

async def get_desc_by_guid(ctx: HandlerContext, guid: str) -> str:
    if guid.startswith('group_'):
        group_id = int(guid.split('_')[1])
        group_info = await get_group_name(ctx.bot, group_id)
        return f"[群聊]{group_info}({group_id})"
    else:
        user_id = int(guid.split('_')[1])
        user_info = await get_stranger_info(ctx.bot, user_id).get('nickname', f'unknown')
        return f"[用户]{user_info}({user_id})"

async def send_msg_to(ctx: HandlerContext, guid: str, msg: str):
    if guid.startswith('group_'):
        group_id = int(guid.split('_')[1])
        return await send_group_msg_by_bot(ctx.bot, group_id, msg)
    else:
        user_id = int(guid.split('_')[1])
        return await send_private_msg_by_bot(ctx.bot, user_id, msg)


bc_list = CmdHandler(['/broadcast list', '/bc list'], logger)
bc_list.check_cdrate(cd).check_wblist(gbl)
@bc_list.handle()
async def _(ctx: HandlerContext):
    bc = file_db.get('bc', {})
    if not bc:
        return await ctx.asend_reply_msg('没有可订阅的广播')
    names = ' | '.join(sorted(list(bc.keys())))
    return await ctx.asend_reply_msg(f'可订阅的广播:\n{names}')


bc_sub = CmdHandler(['/broadcast sub', '/bc sub'], logger)
bc_sub.check_cdrate(cd).check_wblist(gbl)
@bc_sub.handle()
async def _(ctx: HandlerContext):
    if is_group_msg(ctx.event):
        assert_and_reply(check_superuser(ctx.event), '只有超级管理员才能在群聊中订阅广播')
    bc = file_db.get('bc', {})
    name = ctx.get_args().strip()
    assert_and_reply(name, '请输入要订阅的广播名称')
    assert_and_reply(name in bc, f'没有名为 {name} 的广播')
    guid = get_guid(ctx)
    if guid in bc[name]:
        return await ctx.asend_reply_msg(f'已经订阅过广播 {name}')
    bc[name].append(guid)
    file_db.set('bc', bc)
    return await ctx.asend_reply_msg(f'订阅广播 {name} 成功')


bc_unsub = CmdHandler(['/broadcast unsub', '/bc unsub'], logger)
bc_unsub.check_cdrate(cd).check_wblist(gbl)
@bc_unsub.handle()
async def _(ctx: HandlerContext):
    if is_group_msg(ctx.event):
        assert_and_reply(check_superuser(ctx.event), '只有超级管理员才能在群聊中取消订阅广播')
    bc = file_db.get('bc', {})
    name = ctx.get_args().strip()
    assert_and_reply(name, '请输入要取消订阅的广播名称')
    assert_and_reply(name in bc, f'没有名为 {name} 的广播')
    guid = get_guid(ctx)
    if guid not in bc[name]:
        return await ctx.asend_reply_msg(f'没有订阅过广播 {name}')
    bc[name].remove(guid)
    file_db.set('bc', bc)
    return await ctx.asend_reply_msg(f'取消订阅广播 {name} 成功')


bc_unsuball = CmdHandler(['/broadcast unsuball', '/bc unsuball'], logger)
bc_unsuball.check_cdrate(cd).check_wblist(gbl)
@bc_unsuball.handle()
async def _(ctx: HandlerContext):
    if is_group_msg(ctx.event):
        assert_and_reply(check_superuser(ctx.event), '只有超级管理员才能在群聊中取消订阅所有广播')
    bc = file_db.get('bc', {})
    guid = get_guid(ctx)
    unsub_list = []
    for name in bc:
        if guid in bc[name]:
            bc[name].remove(guid)
            unsub_list.append(name)
    file_db.set('bc', bc)
    unsub_list = " | ".join(unsub_list)
    if unsub_list:
        return await ctx.asend_reply_msg(f'取消订阅广播 {unsub_list} 成功')
    else:
        return await ctx.asend_reply_msg('没有订阅任何广播')


bc_sublist = CmdHandler(['/broadcast sublist', '/bc sublist'], logger)
bc_sublist.check_cdrate(cd).check_wblist(gbl)
@bc_sublist.handle()
async def _(ctx: HandlerContext):
    bc = file_db.get('bc', {})
    guid = get_guid(ctx)
    sub_list = []
    for name in bc:
        if guid in bc[name]:
            sub_list.append(name)
    if not sub_list:
        return await ctx.asend_reply_msg('没有订阅任何广播')
    sub_list = " | ".join(sub_list)
    return await ctx.asend_reply_msg(f'已订阅的广播:\n{sub_list}')


bc_add = CmdHandler(['/broadcast add', '/bc add'], logger)
bc_add.check_cdrate(cd).check_wblist(gbl).check_superuser()
@bc_add.handle()
async def _(ctx: HandlerContext):
    bc = file_db.get('bc', {})
    name = ctx.get_args().strip()
    assert_and_reply(name, '请输入要添加的广播名称')
    assert_and_reply(name not in bc, f'广播 {name} 已存在')
    bc[name] = []
    file_db.set('bc', bc)
    return await ctx.asend_reply_msg(f'添加广播 {name} 成功')


bc_del = CmdHandler(['/broadcast del', '/bc del'], logger)
bc_del.check_cdrate(cd).check_wblist(gbl).check_superuser()
@bc_del.handle()
async def _(ctx: HandlerContext):
    bc = file_db.get('bc', {})
    name = ctx.get_args().strip()
    assert_and_reply(name, '请输入要删除的广播名称')
    assert_and_reply(name in bc, f'没有名为 {name} 的广播')
    bc.pop(name)
    file_db.set('bc', bc)
    return await ctx.asend_reply_msg(f'删除广播 {name} 成功')


bc_send = CmdHandler(['/broadcast send', '/bc send'], logger)
bc_send.check_cdrate(cd).check_wblist(gbl).check_superuser()
@bc_send.handle()
async def _(ctx: HandlerContext):
    bc = file_db.get('bc', {})
    reply_msg = await ctx.aget_reply_msg()
    if reply_msg:
        smsg = reply_msg
        name = ctx.get_args().strip()
    else:
        name, smsg = ctx.get_args().strip().split(None, 1)
    assert_and_reply(name, '请输入要发送的广播名称')
    assert_and_reply(name in bc, f'没有名为 {name} 的广播')
    assert_and_reply(smsg, '请输入要发送的消息')
    sended_list = []
    failed_list = []
    if reply_msg:
        smsg.insert(0, {'type': 'text', 'data': {'text': f'【广播组{name}的消息】\n'}})
    else:
        smsg = f"【广播组{name}的消息】\n{smsg.strip()}"
    for guid in bc[name]:
        try:
            await send_msg_to(ctx, guid, smsg)
            sended_list.append(guid)
        except Exception as e:
            logger.error(f"发送广播 {name} 失败: {e}")
            failed_list.append((guid, str(e)))

    if reply_msg:
        msg = f"在广播组{name}中广播回复的消息\n"
    else:
        msg = f"在广播组{name}中广播消息\n"
    if sended_list:
        msg += f"以下发送成功:\n"
        for guid in sended_list:
            msg += f"{await get_desc_by_guid(ctx, guid)}\n"
    if failed_list:
        msg += f"以下发送失败:\n"
        for guid, err in failed_list:
            msg += f"{await get_desc_by_guid(ctx, guid)}: {err}\n"
    return await ctx.asend_reply_msg(msg.strip())


bc_listsub = CmdHandler(['/broadcast listsub', '/bc listsub'], logger)
bc_listsub.check_cdrate(cd).check_wblist(gbl).check_superuser()
@bc_listsub.handle()
async def _(ctx: HandlerContext):
    bc = file_db.get('bc', {})
    name = ctx.get_args().strip()
    assert_and_reply(name, '请输入要查询的广播名称')
    assert_and_reply(name in bc, f'没有名为 {name} 的广播')
    sub_list = bc[name]
    if not sub_list:
        return await ctx.asend_reply_msg(f'广播 {name} 没有订阅者')
    msg = f"广播 {name} 订阅者:\n"
    for guid in sub_list:
        msg += f"{await get_desc_by_guid(ctx, guid)}\n"
    return await ctx.asend_reply_msg(msg.strip())

