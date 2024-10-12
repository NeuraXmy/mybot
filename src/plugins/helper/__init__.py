import yaml
from ..utils import *
from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from nonebot.rule import to_me
import glob

config = get_config('helper')
logger = get_logger('Helper')
file_db = get_file_db('data/helper/db.json', logger)
gbl = get_group_black_list(file_db, logger, 'helper')
cd = ColdDown(file_db, logger, config['cd'])


HELP_DOCS_WEB_URL = "https://github.com/NeuraXmy/mybot/blob/master/helps/{name}.md"
HELP_DOCS_PATH = "helps/{name}.md"

help = CmdHandler(['/help', '/帮助', 'help', '帮助'], logger, block=True, only_to_me=True, priority=99999)
help.check_wblist(gbl).check_cdrate(cd)
@help.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()

    help_doc_paths = glob.glob(HELP_DOCS_PATH.format(name='*'))
    help_names = []
    help_decs = []
    for path in help_doc_paths:
        try:
            if path.endswith('main.md'): continue
            with open(path, 'r') as f:
                first_line = f.readline().strip()
            help_decs.append(first_line.split()[1])
            help_names.append(Path(path).stem)
        except:
            pass

    if not args or args not in help_names:
        msg = "使用 \"/help 英文服务名\" 查看各服务的详细帮助\n"
        msg += "\n可查询的服务列表:\n"
        for name, desc in zip(help_names, help_decs):
            msg += f"【{name}】{desc}\n"
        msg += f"\n或前往网页查看帮助文档:\n"
        msg += HELP_DOCS_WEB_URL.format(name='main')
        return await ctx.asend_fold_msg_adaptive(msg, threshold=0, need_reply=False)
    else:
        doc_path = HELP_DOCS_PATH.format(name=args)
        doc_text = Path(doc_path).read_text()
        try:
            image = await run_in_pool(markdown_to_image, doc_text)
        except Exception as e:
            logger.print_exc(f"渲染{doc_path}帮助文档失败")
            return await ctx.asend_reply_msg(f"帮助文档渲染失败, 前往网页获取帮助文档:\n{HELP_DOCS_WEB_URL.format(name=args)}")
        return await ctx.asend_reply_msg(await get_image_cq(image))