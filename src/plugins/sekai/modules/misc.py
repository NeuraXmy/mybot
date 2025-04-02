from ...utils import *
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *

# ======================= 指令处理 ======================= #

pjsk_update = SekaiCmdHandler([
    "/pjsk update", "/pjsk update",
])
pjsk_update.check_cdrate(cd).check_wblist(gbl).check_superuser()
@pjsk_update.handle()
async def _(ctx: SekaiHandlerContext):
    mgr = RegionMasterDbManager.get(ctx.region)
    source = await mgr.get_latest_source()
    return await ctx.asend_reply_msg(f"{get_region_name(ctx.region)} 最新 MasterData 数据源:\n{source.name} - {source.version}")


ngword = SekaiCmdHandler([
    "/pjsk ng", "/pjsk ngword", "/pjsk ng word",
    "/pjsk屏蔽词", "/pjsk屏蔽", "/pjsk敏感", "/pjsk敏感词",
])
ngword.check_cdrate(cd).check_wblist(gbl)
@ngword.handle()
async def _(ctx: SekaiHandlerContext):
    text = ctx.get_args()
    assert_and_reply(text, "请输入要查询的文本")
    words = await ctx.md.ng_words.get()
    def check():
        ret = []
        for word in words:
            if word in text:
                ret.append(word)
        return ret
    ret = await run_in_pool(check)
    if ret:
        await ctx.asend_reply_msg(f"检测到屏蔽词：{', '.join(ret)}")
    else:
        await ctx.asend_reply_msg("未检测到屏蔽词")
