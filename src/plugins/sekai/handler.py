from ..utils import *
from .common import *
from .asset import (
    RegionMasterDataCollection, 
    RegionRipAssetManger,
    StaticImageRes,
)

HELP_DOC_PATH = "helps/sekai.md"


def get_user_default_region(user_id: int, fallback: str) -> str:
    """
    获取用户不填指令区服时的默认区服
    """
    user_id = str(user_id)
    default_regions = file_db.get("default_region", {})
    return default_regions.get(user_id, fallback)

def set_user_default_region(user_id: int, region: str):
    """
    设置用户不填指令区服时的默认区服
    """
    user_id = str(user_id)
    default_regions = file_db.get("default_region", {})
    default_regions[user_id] = region
    file_db.set("default_region", default_regions)


@dataclass
class SekaiHandlerContext(HandlerContext):
    region: str = None
    original_trigger_cmd: str = None
    md: RegionMasterDataCollection = None
    rip: RegionRipAssetManger = None
    static_imgs: StaticImageRes = None
    create_from_region: bool = False
    prefix_arg: str = None

    @classmethod
    def from_region(cls, region: str) -> 'SekaiHandlerContext':
        ctx = SekaiHandlerContext()
        ctx.region = region
        ctx.md = RegionMasterDataCollection(region)
        ctx.rip = RegionRipAssetManger.get(region)
        ctx.static_imgs = StaticImageRes()
        ctx.create_from_region = True
        ctx.prefix_arg = None
        return ctx
    
    def block_region(self, key="", timeout=3*60, err_msg: str = None):
        if not self.create_from_region:
            return self.block(f"{self.region}_{key}", timeout=timeout, err_msg=err_msg)


class SekaiCmdHandler(CmdHandler):
    DEFAULT_AVAILABLE_REGIONS = ALL_SERVER_REGIONS

    def __init__(
        self, 
        commands: List[str],
        regions: List[str] = None, 
        prefix_args: List[str] = None,
        **kwargs
    ):
        self.available_regions = regions or self.DEFAULT_AVAILABLE_REGIONS
        self.prefix_args = sorted(prefix_args or [''], key=lambda x: len(x), reverse=True)
        all_region_commands = []
        for prefix in self.prefix_args:
            for region in ALL_SERVER_REGIONS:
                for cmd in commands:
                    assert not cmd.startswith(f"/{region}{prefix}")
                    all_region_commands.append(cmd)
                    all_region_commands.append(cmd.replace("/", f"/{prefix}"))
                    all_region_commands.append(cmd.replace("/", f"/{region}{prefix}"))
        all_region_commands = list(set(all_region_commands))
        super().__init__(all_region_commands, logger, **kwargs)

    async def additional_context_process(self, context: HandlerContext):
        # 处理指令区服前缀
        cmd_region = None
        original_trigger_cmd = context.trigger_cmd
        for region in ALL_SERVER_REGIONS:
            if context.trigger_cmd.strip().startswith(f"/{region}"):
                cmd_region = region
                context.trigger_cmd = context.trigger_cmd.replace(f"/{region}", "/")
                break
        
        # 处理前缀参数
        prefix_arg = None
        for prefix in self.prefix_args:
            if context.trigger_cmd.startswith(f"/{prefix}"):
                prefix_arg = prefix
                context.trigger_cmd = context.trigger_cmd.replace(f"/{prefix}", "/")
                break

        user_default_region = get_user_default_region(context.user_id, None)
        cmd_default_region = self.available_regions[0]

        # 如果没有指定区服，并且用户有默认区服，并且用户默认区服在可用区服列表中，则使用用户的默认区服
        if not cmd_region and user_default_region and user_default_region in self.available_regions:
            cmd_region = user_default_region
        # 如果没有指定区服，并且用户没有默认区服，则使用指令的默认区服
        elif not cmd_region:
            cmd_region = cmd_default_region

        assert_and_reply(
            cmd_region in self.available_regions, 
            f"该指令不支持 {cmd_region} 服务器，可用的服务器有: {', '.join(self.available_regions)}"
        )

        # 帮助文档
        HELP_TRIGGER_WORDS = ['help', '帮助']
        if any(word in context.arg_text for word in HELP_TRIGGER_WORDS):
            if help_doc := await self.get_help_doc_part():
                help_doc += f"\n>使用`@{BOT_NAME} /help sekai`查看完整帮助"
                msg = await get_image_cq(await markdown_to_image(help_doc), low_quality=True)
            else:
                msg += "没有找到该指令的帮助\n使用\"@{BOT_NAME}/help sekai\"查看完整帮助"
            raise ReplyException(msg)

        # 构造新的上下文
        params = context.__dict__.copy()
        params['region'] = cmd_region
        params['original_trigger_cmd'] = original_trigger_cmd
        params['md'] = RegionMasterDataCollection(cmd_region)
        params['rip'] = RegionRipAssetManger.get(cmd_region)
        params['static_imgs'] = StaticImageRes()
        params['create_from_region'] = False
        params['prefix_arg'] = prefix_arg

        return SekaiHandlerContext(**params)
    
    async def get_help_doc_part(self) -> Optional[str]:
        try:
            help_doc = Path(HELP_DOC_PATH).read_text(encoding="utf-8")
            parts = help_doc.split("---")[2:-2]
            cmd_parts = []
            for part in parts:
                start = part.find("### ")
                part = part[start:]
                cmd_parts.extend(part.split("### "))

            for cmd_part in cmd_parts:
                if any(cmd in cmd_part for cmd in self.commands):
                    cmd_part = "### " + cmd_part
                    return cmd_part
            
            raise Exception(f"没有找到 {self.commands[0]} 的帮助文档")

        except Exception as e:
            logger.error(f"获取 {self.commands[0]} 的帮助文档失败")
            return None



# 设置默认指令区服
default_region = CmdHandler([
    "/pjsk默认服务器", "/pjsk default region", "/pjsk默认区服",
    "/pjsk服务器", "/pjsk区服",
], logger)
default_region.check_cdrate(cd).check_wblist(gbl)
@default_region.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()

    SET_HELP = f"""
---
使用\"{ctx.trigger_cmd} 区服\"设置默认区服，可用的区服有: {', '.join(ALL_SERVER_REGIONS)}
""".strip()

    if not args:
        region = get_user_default_region(ctx.user_id, None)
        if not region:
            return await ctx.asend_reply_msg(f"""
你还没有设置默认区服。
不加区服前缀发送指令时，会自动选用指令的默认区服(大部分为jp)
{SET_HELP}
""".strip())
        
        else:
            return await ctx.asend_reply_msg(f"""
你的默认区服是: {region}
{SET_HELP}
""".strip())
        
    assert_and_reply(args in ALL_SERVER_REGIONS, SET_HELP)
    set_user_default_region(ctx.user_id, args)

    return await ctx.asend_reply_msg(f"""
已设置你的默认区服为: {args}
""".strip())


