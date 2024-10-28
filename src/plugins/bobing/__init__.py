from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.message import Message
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.params import CommandArg
import random
from ..utils import *

config = get_config('bobing')
logger = get_logger("Bobing")
file_db = get_file_db("data/bobing/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'bobing')

use_image_dice = True
DICE_SIZE = 32
dice_images = [f"data/bobing/dice/{i}.png" for i in range(1, 7)]
dice_images = [Image.open(d).resize((DICE_SIZE, DICE_SIZE)) for d in dice_images]
dice_rule_image = Image.open("data/bobing/dice_rule.jpg")

    
bing = on_command("/bing", aliases={"/bobing", "/博饼", "/饼"}, priority=100, block=False)
@bing.handle()
async def handle_function(bot: Bot, event: MessageEvent):
    if not gbl.check(event, allow_private=True): return
    if not (await cd.check(event)): return
    dices = [random.randint(1, 6) for _ in range(6)]
    try:
        if not use_image_dice:
            dices = [chr(0x267F + dice) for dice in dices]
            msg = " ".join(dices)
            logger.info(f"send: {msg}")
            return await send_reply_msg(bing, event.message_id, msg)
        else:
            image = Image.new('RGBA', (DICE_SIZE * 6, DICE_SIZE * 2), (255, 255, 255, 0))
            for i, dice in enumerate(dices):
                image.paste(dice_images[dice - 1], (i * DICE_SIZE, DICE_SIZE // 2))
            tmp_save_path = f"data/bobing/{rand_filename('gif')}"
            create_transparent_gif(image, tmp_save_path)
            image_cq = await get_image_cq(tmp_save_path)
            await send_reply_msg(bing, event.message_id, image_cq)
            os.remove(tmp_save_path)
    except Exception as e:
        logger.print_exc("bing失败")
        return await send_reply_msg(bing, event.message_id, "发送失败")
    

bing_rule = on_command("/bingrule", priority=100, block=False, aliases={
    "/bing_rule", "/bing rule", "/bobing_rule", "/bobingrule", "/bobing rule",
    "/博饼规则", "/博饼 规则", "/饼 规则", "/饼规则"})
@bing_rule.handle()
async def handle_function(bot: Bot, event: MessageEvent):
    if not gbl.check(event, allow_private=True): return
    if not (await cd.check(event)): return
    return await send_reply_msg(bing_rule, event.message_id, await get_image_cq(dice_rule_image))


rand = on_command("/rand", priority=100, block=False, aliases={'/roll'})
@rand.handle()
async def handle_function(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not gbl.check(event, allow_private=True): return
    if not (await cd.check(event)): return
    l, r = 0, 100
    try:
        l, r = map(int, args.extract_plain_text().split())
        assert l <= r
    except:
        pass
    msg = f'{random.randint(l, r)}'
    logger.info(f"send: {msg}")
    return await send_reply_msg(rand, event.message_id, msg)


choice = on_command("/choice", priority=100, block=False, aliases={'/choose'})
@choice.handle()
async def handle_function(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not gbl.check(event, allow_private=True): return
    if not (await cd.check(event)): return
    choices = args.extract_plain_text().split()
    if len(choices) <= 1:
        msg = '至少需要两个选项'
    else:
        msg = f'选择: {random.choice(choices)}'
    logger.info(f"send: {msg}")
    return await send_reply_msg(choice, event.message_id, msg)


shuffle = on_command("/shuffle", priority=100, block=False)
@shuffle.handle()
async def handle_function(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not gbl.check(event, allow_private=True): return
    if not (await cd.check(event)): return
    choices = args.extract_plain_text().split()
    if len(choices) <= 1:
        msg = '至少需要两个选项'
    else:
        random.shuffle(choices)
        msg = f'{", ".join(choices)}'
    logger.info(f"send: {msg}")
    return await send_reply_msg(shuffle, event.message_id, msg)


randuser = on_command("/randuser", priority=100, block=False, aliases={'/rolluser'})
@randuser.handle()
async def handle_function(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not gbl.check(event, allow_private=False): return
    if not (await cd.check(event)): return

    num = 1
    try:
        num = int(args.extract_plain_text())
        if num <= 0 or num > 5:
            raise Exception()
    except:
        pass
    
    group_members = await get_group_users(bot, event.group_id)

    if num > len(group_members):
        return await send_reply_msg(randuser, event.message_id, '群成员数不足')

    random.shuffle(group_members)
    
    msg = ""

    for user in group_members[:num]:
        user_id = int(user['user_id'])
        icon_url = get_avatar_url(user_id)
        nickname = await get_group_member_name(bot, event.group_id, user_id)
        msg += f"{await get_image_cq(icon_url)}\n{nickname}({user_id})\n"

    return await send_reply_msg(randuser, event.message_id, msg.strip())
