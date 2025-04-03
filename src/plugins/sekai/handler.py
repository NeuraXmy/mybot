from ..utils import *
from .common import *
from .asset import (
    RegionMasterDataCollection, 
    RegionRipAssetManger,
    StaticImageRes,
)

HELP_DOC_PATH = "helps/sekai.md"


@dataclass
class SekaiHandlerContext(HandlerContext):
    region: str = None
    original_trigger_cmd: str = None
    md: RegionMasterDataCollection = None
    rip: RegionRipAssetManger = None
    static_imgs: StaticImageRes = None
    create_from_region: bool = False

    @classmethod
    def from_region(cls, region: str) -> 'SekaiHandlerContext':
        ctx = SekaiHandlerContext()
        ctx.region = region
        ctx.md = RegionMasterDataCollection(region)
        ctx.rip = RegionRipAssetManger.get(region)
        ctx.static_imgs = StaticImageRes()
        ctx.create_from_region = True
        return ctx
    
    def block_region(self, key="", timeout=3*60):
        if not self.create_from_region:
            return self.block(f"{self.region}_{key}", timeout=timeout)


class SekaiCmdHandler(CmdHandler):
    DEFAULT_AVAILABLE_REGIONS = ALL_SERVER_REGIONS

    def __init__(
        self, 
        commands: List[str],
        regions: List[str] = None, 
        **kwargs
    ):
        self.available_regions = regions or self.DEFAULT_AVAILABLE_REGIONS
        all_region_commands = []
        for region in ALL_SERVER_REGIONS:
            for cmd in commands:
                assert not cmd.startswith(f"/{region}")
                all_region_commands.append(cmd)
                all_region_commands.append(cmd.replace("/", f"/{region}"))
        super().__init__(all_region_commands, logger, **kwargs)

    async def additional_context_process(self, context: HandlerContext):
        # 处理指令区服前缀
        cmd_region = self.available_regions[0]
        original_trigger_cmd = context.trigger_cmd
        for region in ALL_SERVER_REGIONS:
            if context.trigger_cmd.strip().startswith(f"/{region}"):
                cmd_region = region
                context.trigger_cmd = context.trigger_cmd.replace(f"/{region}", "/")
                break

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


