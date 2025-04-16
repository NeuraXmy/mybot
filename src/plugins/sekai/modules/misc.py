from ...utils import *
from ...record import after_record_hook
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from .music import add_music_alias


ALIAS_CRAWLER_TIMEOUT = timedelta(seconds=10)
ALIAS_CRAWLER_RECENT_FAIL_LIMIT = 30

# ======================= 逻辑处理 ======================= #

class AliasCrawler:
    def __init__(self, name: str, cmd: str, get_alias_func: Any):
        self.name: str = name
        self.cmd: str = cmd
        self.get_alias_func: Any = get_alias_func
        self.listen_gid: Optional[int] = None
        self.listen_uid: Optional[int] = None
        self.resp_queue: Optional[asyncio.Queue[List[str]]] = None

        @after_record_hook
        async def get_resp_func(bot: Bot, event: GroupMessageEvent):
            if not is_group_msg(event): return
            if event.group_id != self.listen_gid: return
            if event.user_id != self.listen_uid: return
            if not self.resp_queue: return
            logger.info(f"收到 {self.name} bot的别名响应")
            text = event.get_plaintext()
            self.resp_queue.put_nowait(self.get_alias_func(text))
            
    async def start(self, ctx: SekaiHandlerContext, uid: int, start_idx: int):
        ok_count, fail_count, recent_fail_count = 0, 0, 0
        self.listen_gid = ctx.group_id
        self.listen_uid = uid
        self.resp_queue = asyncio.Queue(maxsize=1)
        try:
            musics = await ctx.md.musics.get()
            await ctx.asend_msg(f"开始爬取 {self.name} 别名库共 {len(musics) - start_idx} 首，目标bot为 [CQ:at,qq={uid}]")
            for idx, music in enumerate(musics):
                if idx < start_idx:
                    continue
                if not all([self.listen_gid, self.listen_uid, self.resp_queue]):
                    raise Exception("已停止")
                try:
                    # 开始前先清空响应队列
                    while not self.resp_queue.empty():
                        self.resp_queue.get_nowait()
                    # 发送查询指令
                    await ctx.asend_msg(self.cmd.format(title=music['title']))
                    # 等待回复
                    resp = await asyncio.wait_for(self.resp_queue.get(), timeout=ALIAS_CRAWLER_TIMEOUT.total_seconds())
                    assert resp, f"响应别名为空"
                    # 添加别名
                    ok_alias, failed_alias = [], []
                    for alias in resp:
                        ok, _ = await add_music_alias(music['id'], alias, region=ctx.region, db=self.name)
                        if ok: ok_alias.append(alias)
                        else: failed_alias.append(alias)
                    # 发送成功消息
                    msg = f"#{idx}/{len(musics)} 爬取【{music['id']}】{music['title']} 别名: "
                    if ok_alias:
                        msg += "，".join(ok_alias)
                    if failed_alias:
                        msg += "\n添加失败的别名: "
                        msg += "，".join(failed_alias)
                    await ctx.asend_msg(msg)
                    ok_count += 1
                    recent_fail_count = 0
                except Exception as e:
                    await ctx.asend_msg(f"#{idx}/{len(musics)} 爬取 {music['title']} 别名失败: {get_exc_desc(e)}")
                    fail_count += 1
                    recent_fail_count += 1
                    assert recent_fail_count < ALIAS_CRAWLER_RECENT_FAIL_LIMIT, f"连续失败超过{ALIAS_CRAWLER_RECENT_FAIL_LIMIT}次，停止爬取"
                finally:
                    await asyncio.sleep(5)
        finally:
            self.listen_gid = None
            self.listen_uid = None
            self.resp_queue = None
            await ctx.asend_reply_msg(f"爬取 {self.name} 别名库完成，成功 {ok_count} 条，失败 {fail_count} 条")

    def stop(self):
        self.listen_gid = None
        self.listen_uid = None
        self.resp_queue = None
        

def get_haruki_alias(s: str) -> List[str]:
    lines = s.splitlines()
    if len(lines) < 2:
        return []
    return [a for a in lines[2].split("，") if a]

crawler = {
    "haruki": AliasCrawler(
        name="haruki",
        cmd="musicalias {title}",
        get_alias_func=get_haruki_alias,
    ),
}


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


pjsk_crawl_alias = SekaiCmdHandler([
    "/PCA"
])
pjsk_crawl_alias.check_cdrate(cd).check_wblist(gbl).check_superuser().check_group()
@pjsk_crawl_alias.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip().split()
    assert_and_reply(1 <= len(args) <= 2, "请指定要爬取的别名库")
    if len(args) == 1:
        db = args[0]
        start = 0
    else:
        db = args[0]
        start = int(args[1])
    assert_and_reply(db in crawler, "请指定要爬取的别名库")
    uid = None
    if at_qqs := extract_at_qq(await ctx.aget_msg()):
        uid = at_qqs[0]
    assert_and_reply(uid, "请@指定要爬取的bot号")
    await ctx.block(timeout=0)
    await crawler[db].start(ctx, uid, start)


pjsk_crawl_alias_stop = SekaiCmdHandler([
    "/PCAS"
])
pjsk_crawl_alias_stop.check_cdrate(cd).check_wblist(gbl).check_superuser().check_group()
@pjsk_crawl_alias_stop.handle()
async def _(ctx: SekaiHandlerContext):
    for name, c in crawler.items():
        c.stop()


