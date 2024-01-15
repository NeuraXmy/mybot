import yaml
from ..utils import *
from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

config = get_config('helper')
logger = get_logger('Helper')
file_db = get_file_db('data/helper/db.json', logger)
gbl = get_group_black_list(file_db, logger, 'helper')
cds = []

# 帮助
HELPER_PATH = 'helper.yaml'
def init_helper():
    logger.info(f'初始化帮助')
    with open(HELPER_PATH, 'r') as f:
        helps = yaml.load(f, Loader=yaml.FullLoader)
    help_keys = helps.keys()
    logger.info(f'可用的帮助: {",".join(help_keys)}')
    
    # 如果没有全局帮助, 则自动添加
    if '_global' not in helps:
        global_help = "使用以下指令查看各服务的详细帮助\n"
        for key, val in helps.items():
            global_help += f"/help {key} - {val['name']}\n"
        if global_help.endswith('\n'):
            global_help = global_help[:-1]
        helps['_global'] = {
            'name': '',
            'help': global_help
        }

    for key, val in helps.items():
        cd = ColdDown(file_db, logger, config['cd'], cold_down_name=key)
        cds.append(cd)
        cd_index = len(cds) - 1
        help_text = f'【{val["name"]}帮助】\n{val["help"]}'
        help_text = help_text.strip()
        # 注册指令
        cmd = "/help" if key == '_global' else f"/help {key}"
        help = on_command(cmd, block=False, priority=100)
        @help.handle()
        async def _(event: MessageEvent, help_text=help_text, cd_index=cd_index):
            fake_event = deepcopy(event)
            fake_event.user_id = 1
            if not gbl.check(fake_event, allow_private=True): return
            if not cds[cd_index].check(event): return
            await help.finish(help_text)

    logger.info(f'初始化帮助完成')
    
    

init_helper()