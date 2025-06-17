from datetime import datetime, timedelta
import orjson
import time
import os
from glob import glob
from tenacity import retry, stop_after_attempt, wait_fixed
from typing import List, Dict, Any, Union, Optional, Tuple, Set
from os.path import join as pjoin
from dataclasses import dataclass, field
import asyncio
import yaml
from fastapi import FastAPI, HTTPException, Request, Response
import asyncio
from sekai_deck_recommend import (
    SekaiDeckRecommend, 
    DeckRecommendOptions, 
    DeckRecommendCardConfig, 
    DeckRecommendResult,
    DeckRecommendSaOptions,
    RecommendDeck,
)


def load_json(file_path: str) -> dict:
    with open(file_path, 'rb') as file:
        return orjson.loads(file.read())
    
def dump_json(data: dict, file_path: str, indent: bool = True) -> None:
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'wb') as file:
        buffer = orjson.dumps(data, option=orjson.OPT_INDENT_2 if indent else 0)
        file.write(buffer)

def loads_json(s: str | bytes) -> dict:
    return orjson.loads(s)

def dumps_json(data: dict, indent: bool = True) -> str:
    return orjson.dumps(data, option=orjson.OPT_INDENT_2 if indent else 0).decode('utf-8')

async def aload_json(path: str) -> Dict[str, Any]:
    return await asyncio.to_thread(load_json, path)

async def asave_json(data: Dict[str, Any], path: str):
    return await asyncio.to_thread(dump_json, data, path)

def get_exc_desc(e: Exception) -> str:
    et = type(e).__name__
    e = str(e)
    if et in ['AssertionError', 'HTTPException', 'Exception']:
        return e
    if et and e:
        return f"{et}: {e}"
    return et or e

def log(*args, **kwargs):
    time_str = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    pname = f"[{os.getpid()}] "
    print(time_str, pname, *args, **kwargs)

def error(*args, **kwargs):
    log(*args, **kwargs)
    import traceback
    traceback.print_exc()

def print_headers(headers: Dict[str, str]):
    headers = dict(headers)
    print("=" * 20)
    for k, v in headers.items():
        print(f"{k}: {v}")
    print("=" * 20)

def create_parent_folder(path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path

def options_to_str(options: DeckRecommendOptions) -> str:
    def cardconfig2str(cfg: DeckRecommendCardConfig):
        return f"{(int)(cfg.disable)}{(int)(cfg.level_max)}{(int)(cfg.episode_read)}{(int)(cfg.master_max)}{(int)(cfg.skill_max)}"
    log = "Options=("
    log += f"type={options.live_type}, "
    log += f"mid={options.music_id}, "
    log += f"mdiff={options.music_diff}, "
    log += f"eid={options.event_id}, "
    log += f"wl_cid={options.world_bloom_character_id}, "
    log += f"challenge_cid={options.challenge_live_character_id}, "
    log += f"limit={options.limit}, "
    log += f"member={options.member}, "
    log += f"rarity1={cardconfig2str(options.rarity_1_config)}, "
    log += f"rarity2={cardconfig2str(options.rarity_2_config)}, "
    log += f"rarity3={cardconfig2str(options.rarity_3_config)}, "
    log += f"rarity4={cardconfig2str(options.rarity_4_config)}, "
    log += f"rarity_bd={cardconfig2str(options.rarity_birthday_config)}, "
    log += f"fixed_cards={options.fixed_cards})"
    return log


# =========================== API =========================== #

recommender = SekaiDeckRecommend()
last_masterdata_update_ts = {}
last_musicmetas_update_ts = {}

app = FastAPI()

@app.post("/recommend")
async def recommend_deck(request: Request):
    try:
        data = await request.json()
        create_time = datetime.fromtimestamp(data['create_ts'])
        wait_time = datetime.now() - create_time
        region = data['region']
        masterdata_path         = data['masterdata_path']
        musicmetas_path         = data['musicmetas_path']
        masterdata_update_ts    = data['masterdata_update_ts']
        musicmetas_update_ts    = data['musicmetas_update_ts']
        options = DeckRecommendOptions.from_dict(data['options'])

        log(f"收到 {create_time.strftime('%Y-%m-%d %H:%M:%S')} 的组卡请求 region={region}, {options_to_str(options)}")

        # 更新 masterdata 和 musicmeta
        global last_masterdata_update_ts, last_musicmetas_update_ts
        if last_masterdata_update_ts.get(region) != masterdata_update_ts:
            log(f"更新 {region} MasterData: {datetime.fromtimestamp(masterdata_update_ts).strftime('%Y-%m-%d %H:%M:%S')}")
            recommender.update_masterdata(masterdata_path, region)
            last_masterdata_update_ts[region] = masterdata_update_ts
        if last_musicmetas_update_ts.get(region) != musicmetas_update_ts:
            log(f"更新 {region} MusicMetas: {datetime.fromtimestamp(musicmetas_update_ts).strftime('%Y-%m-%d %H:%M:%S')}")
            recommender.update_musicmetas(musicmetas_path, region)
            last_musicmetas_update_ts[region] = musicmetas_update_ts

        # 执行组卡
        log(f"开始组卡")
        start_time = datetime.now()
        result: DeckRecommendResult = recommender.recommend(options)
        cost_time = datetime.now() - start_time
        log(f"组卡完成, 耗时 {cost_time.total_seconds()} 秒")

        return {
            "status": "success",
            "result": result.to_dict(),
            "alg": options.algorithm,
            "cost_time": cost_time.total_seconds(),
            "wait_time": wait_time.total_seconds(),
        }

    except Exception as e:
        error("组卡请求处理失败")
        return {
            "status": "error",
            "exception": get_exc_desc(e),
        }
