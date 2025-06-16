from ..utils import *
from .common import *
from .handler import *

# ======================= 群聊订阅 ======================= #

GROUP_SUB_COMMANDS = [
    "/pjsk_group_sub_{id}",
    "/pjsk_sub_group_{id}",
    "/pjsk group sub {id}",
    "/pjsk sub group {id}",
    "/pjsk开启 {id}",
    "/pjsk 开启 {id}",
    "/pjsk开启{id}",
    "/pjsk 开启{id}",
]
GROUP_UNSUB_COMMANDS = [
    "/pjsk_group_unsub_{id}",
    "/pjsk_unsub_group_{id}",
    "/pjsk group unsub {id}",
    "/pjsk unsub group {id}",
    "/pjsk关闭 {id}",
    "/pjsk 关闭 {id}",
    "/pjsk关闭{id}",
    "/pjsk 关闭{id}",
]

class SekaiGroupSubHelper:
    all_subs: List['SekaiGroupSubHelper'] = []

    def __init__(self, id: str, name: str, regions: List[str]):
        self.id = id
        self.name = name
        self.regions = regions
        self.subs = {
            region: SubHelper(
                f"{name}({region_name})_群聊",
                file_db,
                logger,
                key_fn=lambda gid: str(gid),
                val_fn=lambda x: int(x)
            ) for region, region_name in zip(regions, ALL_SERVER_REGION_NAMES)
        }
        self._register_handlers()
        SekaiGroupSubHelper.all_subs.append(self)

    def _register_handlers(self):
        sub_commands = [cmd.format(id=self.id) for cmd in GROUP_SUB_COMMANDS]
        sub = SekaiCmdHandler(sub_commands, regions=self.regions, priority=101)
        sub.check_cdrate(cd).check_wblist(gbl).check_superuser()
        @sub.handle()
        async def _(ctx: SekaiHandlerContext):
            self.subs[ctx.region].sub(ctx.group_id)
            return await ctx.asend_reply_msg(f"开启本群 {self.name}({get_region_name(ctx.region)})")
        
        unsub_commands = [cmd.format(id=self.id) for cmd in GROUP_UNSUB_COMMANDS]
        unsub = SekaiCmdHandler(unsub_commands, regions=self.regions, priority=101)
        unsub.check_cdrate(cd).check_wblist(gbl).check_superuser()
        @unsub.handle()
        async def _(ctx: SekaiHandlerContext):
            self.subs[ctx.region].unsub(ctx.group_id)
            return await ctx.asend_reply_msg(f"关闭本群 {self.name}({get_region_name(ctx.region)})")

    def _check_region(self, region):
        if region not in self.regions:
            raise Exception(f"群聊订阅 {self.name} 不支持服务器 {region}")

    def is_subbed(self, region, group_id):
        self._check_region(region)
        return self.subs[region].is_subbed(group_id)

    def sub(self, region, group_id):
        self._check_region(region)
        return self.subs[region].sub(group_id)

    def unsub(self, region, group_id):
        self._check_region(region)
        return self.subs[region].unsub(group_id)

    def get_all(self, region):
        self._check_region(region)
        return self.subs[region].get_all()

    def clear(self, region):
        self._check_region(region)
        return self.subs[region].clear()

group_sub_list = CmdHandler([
    "/pjsk_group_sub_list",
    "/pjsk group sub list",
    "/pjsk_group_subs",
    "/pjsk group subs",
    "/pjsk群订阅",
    "/pjsk 群订阅",
    "/pjsk群聊订阅",
    "/pjsk 群聊订阅",
    "/pjsk开启",
], logger, priority=100)
group_sub_list.check_cdrate(cd).check_wblist(gbl)
@group_sub_list.handle()
async def _(ctx: HandlerContext):
    msg = "当前群聊开启:\n"
    for sub in SekaiGroupSubHelper.all_subs:
        sub_regions = []
        for region in sub.regions:
            if sub.is_subbed(region, ctx.group_id):
                sub_regions.append(region)
        if sub_regions:
            msg += f"{sub.name}({', '.join(sub_regions)})\n"
    
    msg += "---\n"
    msg += "使用 /pjsk开启{英文项目名} 开启订阅\n"
    msg += "所有可开启项目:\n"
    for sub in SekaiGroupSubHelper.all_subs:
        msg += f"{sub.id}: {sub.name}({', '.join(sub.regions)})\n"

    return await ctx.asend_reply_msg(msg.strip())


# ======================= 用户订阅 ======================= #

USER_SUB_COMMANDS = [
    "/pjsk_sub_{id}",
    "/pjsk sub {id}",
    "/pjsk订阅 {id}",
    "/pjsk 订阅 {id}",
    "/pjsk订阅{id}",
    "/pjsk 订阅{id}",
]
USER_UNSUB_COMMANDS = [
    "/pjsk_unsub_{id}",
    "/pjsk unsub {id}",
    "/pjsk取消 {id}",
    "/pjsk 取消 {id}",
    "/pjsk取消{id}",
    "/pjsk 取消{id}",
    "/pjsk取消订阅 {id}",
    "/pjsk 取消订阅 {id}",
    "/pjsk取消订阅{id}",
    "/pjsk 取消订阅{id}",
]

class SekaiUserSubHelper:
    all_subs: List['SekaiUserSubHelper'] = []

    def __init__(self, id: str, name: str, regions: List[str], related_group_sub: SekaiGroupSubHelper = None, only_one_group=False):
        self.id = id
        self.name = name
        self.regions = regions
        self.related_group_sub = related_group_sub
        self.subs = {
            region: SubHelper(
                f"{name}({region_name})_用户",
                file_db,
                logger,
                key_fn=lambda uid, gid: f"{uid}@{gid}", 
                val_fn=lambda x: list(map(int, x.split("@")))
            ) for region, region_name in zip(regions, ALL_SERVER_REGION_NAMES)
        }
        self.only_one_group = only_one_group
        self._register_handlers()
        SekaiUserSubHelper.all_subs.append(self)

    def _register_handlers(self):
        sub_commands = [cmd.format(id=self.id) for cmd in USER_SUB_COMMANDS]
        sub = SekaiCmdHandler(sub_commands, regions=self.regions, priority=101)
        sub.check_cdrate(cd).check_wblist(gbl)
        @sub.handle()
        async def _(ctx: SekaiHandlerContext):
            has_other_group_sub = False
            if self.only_one_group:
                # 检测是否在其他群聊订阅
                for uid, gid in self.subs[ctx.region].get_all():
                    if uid == ctx.user_id and gid != ctx.group_id:
                        has_other_group_sub = True
                        self.subs[ctx.region].unsub(uid, gid)
            self.subs[ctx.region].sub(ctx.user_id, ctx.group_id)
            msg = f"成功订阅 {self.name}({get_region_name(ctx.region)})\n"
            if has_other_group_sub:
                msg += "已自动取消你在其他群聊的订阅\n"
            # 对应群聊功能未开启
            if self.related_group_sub and ctx.group_id not in self.related_group_sub.get_all(ctx.region):
                msg += f"该订阅对应的群聊功能 {self.related_group_sub.name}({get_region_name(ctx.region)}) 在本群未开启！"
                msg += "如需使用请联系BOT超管"
            return await ctx.asend_reply_msg(msg.strip())
        
        unsub_commands = [cmd.format(id=self.id) for cmd in USER_UNSUB_COMMANDS]
        unsub = SekaiCmdHandler(unsub_commands, regions=self.regions, priority=101)
        unsub.check_cdrate(cd).check_wblist(gbl)
        @unsub.handle()
        async def _(ctx: SekaiHandlerContext):
            self.subs[ctx.region].unsub(ctx.user_id, ctx.group_id)
            return await ctx.asend_reply_msg(f"取消订阅 {self.name}({get_region_name(ctx.region)})")

    def _check_region(self, region):
        if region not in self.regions:
            raise Exception(f"用户订阅 {self.name} 不支持服务器 {region}")

    def is_subbed(self, region, user_id, group_id):
        self._check_region(region)
        return self.subs[region].is_subbed(user_id, group_id)

    def sub(self, region, user_id, group_id):
        self._check_region(region)
        return self.subs[region].sub(user_id, group_id)

    def unsub(self, region, user_id, group_id):
        self._check_region(region)
        return self.subs[region].unsub(user_id, group_id)
    
    def get_all(self, region, group_id) -> List[int]:
        self._check_region(region)
        ret = self.subs[region].get_all()
        return [x[0] for x in ret if x[1] == group_id]
    
    def get_all_gid_uid(self, region) -> List[Tuple[int, int]]:
        self._check_region(region)
        return self.subs[region].get_all()

    def clear(self, region):
        self._check_region(region)
        return self.subs[region].clear()
    

user_sub_list = CmdHandler([
    "/pjsk_sub_list",
    "/pjsk sub list",
    "/pjsk_subs",
    "/pjsk subs",
    "/pjsk订阅",
    "/pjsk 订阅",
    "/pjsk用户订阅",
    "/pjsk 用户订阅",
], logger, priority=100)
user_sub_list.check_cdrate(cd).check_wblist(gbl)
@user_sub_list.handle()
async def _(ctx: HandlerContext):
    msg = "你在当前群聊的订阅:\n"
    has_related_not_on = False
    for sub in SekaiUserSubHelper.all_subs:
        sub_regions = []
        for region in sub.regions:
            if sub.is_subbed(region, ctx.user_id, ctx.group_id):
                # 标记对应群聊功能未开启的订阅
                if sub.related_group_sub and ctx.group_id not in sub.related_group_sub.get_all(region):
                    has_related_not_on = True
                    region = region + "*"
                sub_regions.append(region)
        if sub_regions:
            msg += f"{sub.name}({', '.join(sub_regions)})\n"
    if has_related_not_on:
        msg += "---\n"
        msg += "带*的订阅对应的群聊功能在本群未开启！"
        msg += "如需使用请联系BOT超管\n"

    msg += "---\n"
    msg += "使用 /pjsk订阅{英文项目名} 开启订阅\n"
    msg += "所有可订阅项目:\n"
    for sub in SekaiUserSubHelper.all_subs:
        msg += f"{sub.id}: {sub.name}({', '.join(sub.regions)})\n"
        
    return await ctx.asend_reply_msg(msg.strip())