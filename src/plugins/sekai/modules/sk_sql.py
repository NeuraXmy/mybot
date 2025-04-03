from ...utils import *
from ..common import *
import aiosqlite
import asyncio

RANKING_NAME_LEN_LIMIT = 32

DB_PATH = SEKAI_DATA_DIR + "/db/sk_{region}/{event_id}_ranking.db"

conns: Dict[str, aiosqlite.Connection] = {}
table_created: Dict[str, bool] = {}


async def get_conn(region, event_id) -> aiosqlite.Connection:
    path = DB_PATH.format(region=region, event_id=event_id)
    create_parent_folder(path)

    global conns
    if conns.get(path) is None:
        conns[path] = await aiosqlite.connect(path)
        logger.info(f"连接sqlite数据库 {path} 成功")

    conn = conns[path]
    if not table_created.get(f"{region}_{event_id}"):
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ranking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid TEXT,
                name TEXT,
                score INTEGER,
                rank INTEGER,
                ts INTEGER
            )
        """)    
        await conn.commit()
        table_created[f"{region}_{event_id}"] = True

    return conn


@dataclass
class Ranking:
    uid: str
    name: str
    score: int
    rank: int
    time: datetime
    id: Optional[int] = None

    @classmethod
    def from_row(cls, row):
        return cls(
            id=row[0],
            uid=row[1],
            name=row[2],
            score=row[3],
            rank=row[4],
            time=datetime.fromtimestamp(row[5])
        )


async def insert_rankings(region: str, event_id: int, rankings: List[Ranking]):
    conn = await get_conn(region, event_id)

    for ranking in rankings:
        ranking.name = ranking.name[:RANKING_NAME_LEN_LIMIT]
        await conn.execute("""
            INSERT INTO ranking (uid, name, score, rank, ts) VALUES (?, ?, ?, ?, ?)
        """, (ranking.uid, ranking.name, ranking.score, ranking.rank, ranking.time.timestamp()))

    await conn.commit()


async def query_ranking(
    region: str, 
    event_id: int, 
    uid: str = None,
    name: str = None,
    start_time: datetime = None,
    end_time: datetime = None,
    limit: int = None,
    order_by: str = None,
) -> List[Ranking]:
    conn = await get_conn(region, event_id)

    sql = "SELECT * FROM ranking WHERE 1=1"
    args = []

    if uid:
        sql += " AND uid = ?"
        args.append(uid)

    if name:
        name = name[:RANKING_NAME_LEN_LIMIT]
        sql += " AND name = ?"
        args.append(name)

    if start_time:
        sql += " AND ts >= ?"
        args.append(start_time.timestamp())

    if end_time:
        sql += " AND ts <= ?"
        args.append(end_time.timestamp())

    if order_by:
        sql += f" ORDER BY {order_by}"

    if limit:
        sql += f" LIMIT {limit}"

    cursor = await conn.execute(sql, args)
    rows = await cursor.fetchall()

    return [Ranking.from_row(row) for row in rows]


async def query_latest_ranking(region: str, event_id: int, ranks: List[int] = None) -> List[Ranking]:
    if ranks:
        # 对于ranks中的每一个rank，找到最新的一条记录
        conn = await get_conn(region, event_id)
        ret = []
        for rank in ranks:
            cursor = await conn.execute("""
                SELECT * FROM ranking WHERE rank = ? ORDER BY ts DESC LIMIT 1
            """, (rank,))
            row = await cursor.fetchone()
            if row:
                ret.append(Ranking.from_row(row))
        return ret
    else:
        # 对于表中的每一个rank，找到最新的一条记录
        conn = await get_conn(region, event_id)
        cursor = await conn.execute("""
            SELECT * FROM ranking WHERE id IN (
                SELECT MAX(id) FROM ranking GROUP BY rank
            ) ORDER BY rank
        """)
        rows = await cursor.fetchall()
        return [Ranking.from_row(row) for row in rows]


async def query_latest_ranking_before(
    region: str, 
    event_id: int, 
    before_time: datetime,
    ranks: List[int] = None,
) -> List[Ranking]:
    if ranks:
        # 对于ranks中的每一个rank，找到最新的一条记录
        conn = await get_conn(region, event_id)
        ret = []
        for rank in ranks:
            cursor = await conn.execute("""
                SELECT * FROM ranking WHERE rank = ? AND ts < ? ORDER BY ts DESC LIMIT 1
            """, (rank, before_time.timestamp()))
            row = await cursor.fetchone()
            if row:
                ret.append(Ranking.from_row(row))
        return ret
    else:
        # 对于表中的每一个rank，找到最新的一条记录
        conn = await get_conn(region, event_id)
        cursor = await conn.execute("""
            SELECT * FROM ranking WHERE id IN (
                SELECT MAX(id) FROM ranking WHERE ts < ? GROUP BY rank
            ) ORDER BY rank
        """, (before_time.timestamp(),))
        rows = await cursor.fetchall()
        return [Ranking.from_row(row) for row in rows]