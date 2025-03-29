from ..utils import *
from .common import *
from .asset import (
    RegionMasterDataCollection, 
    RegionRipAssetManger,
    StaticImageRes,
)

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
    
    def block_region(self, timeout=3*60):
        if not self.create_from_region:
            return self.block(f"region_{self.region}", timeout=timeout)


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

        params = context.__dict__.copy()
        params['region'] = cmd_region
        params['original_trigger_cmd'] = original_trigger_cmd
        params['md'] = RegionMasterDataCollection(cmd_region)
        params['rip'] = RegionRipAssetManger.get(cmd_region)
        params['static_imgs'] = StaticImageRes()

        return SekaiHandlerContext(**params)


