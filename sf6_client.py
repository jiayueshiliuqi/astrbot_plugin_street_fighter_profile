"""
Street Fighter 6 玩家数据查询工具

支持两种认证方式:
1. Cookie 模式: 从浏览器登录后复制 Cookie，通过 Buckler Web API 查询
2. Token 模式: 提供 rebe_token，直接调用 Capcom 游戏 API
"""
import os
import base64
import json
import time
import re
from dataclasses import dataclass, field
from typing import Optional, Union

import requests


CAPI_URL = "https://production-us-central1-capi.sf6.streetfighter.com"
WEB_BASE = "https://www.streetfighter.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
CAPI_USER_AGENT = "Capcom Web Client/3.0 (develop)"
CLIENT_VERSION = {"major": 2, "minor": 301, "patch": 10, "battle": 20003000}
PROXIES = None
DEBUG_SF6 = False

RANK_NAMES = {
    1: "新手 I",
    2: "新手 II",
    3: "新手 III",
    4: "新手 IV",
    5: "新手 V",

    6: "黑铁 I",
    7: "黑铁 II",
    8: "黑铁 III",
    9: "黑铁 IV",
    10: "黑铁 V",

    11: "青铜 I",
    12: "青铜 II",
    13: "青铜 III",
    14: "青铜 IV",
    15: "青铜 V",

    16: "白银 I",
    17: "白银 II",
    18: "白银 III",
    19: "白银 IV",
    20: "白银 V",

    21: "黄金 I",
    22: "黄金 II",
    23: "黄金 III",
    24: "黄金 IV",
    25: "黄金 V",

    26: "白金 I",
    27: "白金 II",
    28: "白金 III",
    29: "白金 IV",
    30: "白金 V",

    31: "钻石 I",
    32: "钻石 II",
    33: "钻石 III",
    34: "钻石 IV",
    35: "钻石 V",

    36: "大师",
}
RANK_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}
CHARACTER_NAMES = {
    "luke": "卢克",
    "jamie": "杰米",
    "chunli": "春丽",
    "ryu": "隆",
    "honda": "本田",
    "blanka": "布兰卡",
    "guile": "古烈",
    "ken": "肯",
    "zangief": "桑吉尔夫",
    "dhalsim": "达尔西姆",
    "cammy": "嘉米",
    "deejay": "迪杰",
    "lily": "莉莉",
    "jp": "JP",
    "juri": "朱莉",
    "kimberly": "金佰利",
    "manon": "曼侬",
    "marisa": "玛丽莎",
    "rashid": "拉希德",
    "aki": "阿鬼",
    "ed": "艾德",
    "gouki": "豪鬼",
    "vega": "维加",
    "terry": "特瑞",
    "mai": "舞",
    "elena": "艾琳娜",
    "sagat": "沙加特",
    "cviper": "毒蛇",
    "alex": "亚历克斯",
    "ingrid": "英格丽德",
    "all": "全部",
    "random": "随机",
}

CHARACTER_ID_MAP = {
    1: "ryu",
    2: "luke",
    3: "kimberly",
    4: "chunli",
    5: "manon",
    6: "zangief",
    7: "jp",
    8: "dhalsim",
    9: "cammy",
    10: "ken",

    11: "deejay",
    12: "lily",
    13: "aki",
    14: "rashid",
    15: "blanka",
    16: "juri",
    17: "marisa",
    18: "guile",
    19: "ed",
    20: "honda",
    21: "jamie",
    22: "gouki",
    25: "sagat",
    26: "vega",
    27: "terry",
    28: "mai",
    29: "elena",
    30: "cviper",
    31: "alex",
    32: "ingrid",
    253: "all",
    254: "random",
}

def _to_int(value, default=0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _walk_dicts(value):
    """递归遍历 Buckler JSON 中所有字典。"""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)

    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)

def _get_character_id(data: dict) -> int:
    if not isinstance(data, dict):
        return 0

    for key in (
        "character_id",
        "characterId",
        "character_no",
        "characterNo",
        "character_id_number",
    ):
        if key in data:
            character_id = _to_int(data.get(key), 0)
            if character_id > 0:
                return character_id

    # 有些结构会把角色信息放到 character_info 中。
    for key in (
        "character_info",
        "characterInfo",
        "fighter_info",
        "fighterInfo",
    ):
        child = data.get(key)

        if isinstance(child, dict):
            character_id = _get_character_id(child)
            if character_id > 0:
                return character_id

    return 0


def _get_stat_value(data: dict, keys: tuple) -> int:
    for key in keys:
        if key in data:
            return _to_int(data.get(key), 0)

    return 0

def _get_rank_number(league_info: dict) -> int:
    """
    league=0 不代表没有段位。
    当前数据中 league_rank=19 才是实际段位编号。
    """
    return _to_int(
        league_info.get("league_rank")
        or league_info.get("rank_id")
        or league_info.get("rank")
        or 0
    )


def _get_lp(league_info: dict) -> int:
    return _to_int(
        league_info.get("league_point")
        or league_info.get("league_points")
        or league_info.get("lp")
        or 0
    )
def set_proxy(http_proxy: str = None, https_proxy: str = None):
    global PROXIES
    if http_proxy:
        PROXIES = {"http": http_proxy, "https": https_proxy or http_proxy}



def _decode_jwt_payload(jwt_str: str) -> Optional[dict]:
    try:
        payload = jwt_str.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None


def _first_value(data: dict, keys: tuple, default=None):
    """
    从一个字典中按候选字段名取值。
    Buckler 接口字段在不同版本中可能有变化。
    """
    if not isinstance(data, dict):
        return default

    for key in keys:
        if key in data and data[key] is not None:
            return data[key]

    return default

def _is_jwt_expired(jwt_str: str, skew: int = 60) -> bool:
    if not jwt_str:
        return True
    data = _decode_jwt_payload(jwt_str)
    if not data or "exp" not in data:
        return True
    return data["exp"] <= time.time() + skew


@dataclass
class PlayerProfile:
    name: str = ""
    short_id: str = ""
    platform: str = ""

    league: int = 0
    league_rank: int = 0
    lp: int = 0
    mr: int = 0
    mr_ranking: int = 0

    total_wins: int = 0
    total_losses: int = 0
    total_matches: int = 0
    win_streak: int = 0

    ranked_wins: int = 0
    ranked_losses: int = 0
    ranked_matches: int = 0

    # Buckler 资料页 favorite_character_id，不代表最近实际使用角色
    favorite_character_id: int = 0
    favorite_character_name: str = ""

    # 真正从全角色段位数据中选出的最高段位角色
    highest_character_id: int = 0
    highest_character_name: str = ""

    character_usage: list = field(default_factory=list)
    character_ranked_usage: list = field(default_factory=list)
    character_ranks: list = field(default_factory=list)
    last_play_at: int = 0
    raw: dict = field(default_factory=dict)


class SF6Client:
    """Street Fighter 6 数据查询客户端"""

    def __init__(self, cookie_str: str = "", rebe_token: str = "", proxy: str = None):
        if proxy:
            set_proxy(proxy, proxy)

        self._http = requests.Session()
        self._http.headers.update({"User-Agent": USER_AGENT})

        if cookie_str:
            self.set_cookies(cookie_str)

        self._rebe_token = rebe_token
        self._session_id = ""
        self._nonce = ""
        self._build_id = None
        self._authenticated = False
        self._my_short_id = None
        self._friend_cache = None

    @classmethod
    def _find_character_usage(cls, *sources) -> list[dict]:
        """
        查找按角色统计的胜场和总场次。

        只有同一个对象中同时存在：
        - character_id
        - win_count
        - battle_count

        才将其视为角色战绩，避免把角色成就中的 win_count
        误认为角色胜场。
        """
        found = {}

        character_keys = (
            "character_id",
            "characterId",
            "character_no",
            "characterNo",
            "character_id_number",
        )

        win_keys = (
            "win_count",
            "winCount",
            "wins",
            "total_wins",
            "totalWins",
        )

        loss_keys = (
            "lose_count",
            "loseCount",
            "loss_count",
            "lossCount",
            "losses",
            "total_losses",
            "totalLosses",
        )

        match_keys = (
            "battle_count",
            "battleCount",
            "match_count",
            "matchCount",
            "total_matches",
            "totalMatches",
        )

        def first_present(data: dict, keys: tuple):
            for key in keys:
                if key in data:
                    return data.get(key)
            return None

        def direct_character_id(data: dict) -> int:
            # 只读取当前统计对象自己的角色 ID。
            # 不从父级继承，避免把子级成就计数绑定到角色。
            value = first_present(data, character_keys)

            if value is not None:
                return _to_int(value, 0)

            for key in (
                "character_info",
                "characterInfo",
                "fighter_info",
                "fighterInfo",
            ):
                child = data.get(key)

                if not isinstance(child, dict):
                    continue

                value = first_present(child, character_keys)

                if value is not None:
                    return _to_int(value, 0)

            return 0

        def walk(value, path=()):
            if isinstance(value, dict):
                character_id = direct_character_id(value)
                raw_wins = first_present(value, win_keys)
                raw_losses = first_present(value, loss_keys)
                raw_matches = first_present(value, match_keys)

                # 关键限制：
                # 没有明确总场次时，不能把 win_count 当角色战绩。
                if (
                    character_id > 0
                    and character_id not in (253, 254)
                    and raw_wins is not None
                    and raw_matches is not None
                ):
                    wins = _to_int(raw_wins, 0)
                    matches = _to_int(raw_matches, 0)

                    if raw_losses is None:
                        losses = matches - wins
                    else:
                        losses = _to_int(raw_losses, 0)

                    # 拒绝明显不成立的数据。
                    valid = (
                        matches > 0
                        and wins >= 0
                        and losses >= 0
                        and wins <= matches
                    )

                    if valid:
                        # 如果接口同时给了胜、负、总场次，
                        # 以明确总场次为准，但要求误差合理。
                        if raw_losses is not None:
                            counted_matches = wins + losses

                            if counted_matches > matches:
                                valid = False

                        if valid:
                            item = {
                                "character_id": character_id,
                                "win_count": wins,
                                "lose_count": losses,
                                "battle_count": matches,
                                "path": "/".join(
                                    str(part) for part in path
                                ),
                            }

                            old = found.get(character_id)

                            # 同一角色可能出现多组统计，
                            # 保留总场次最多、最完整的一组。
                            if (
                                old is None
                                or matches > old["battle_count"]
                            ):
                                found[character_id] = item

                for key, child in value.items():
                    walk(child, path + (key,))

            elif isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, path + (index,))

        for source_index, source in enumerate(sources):
            if source:
                walk(
                    source,
                    path=(f"source_{source_index}",),
                )

        result = list(found.values())

        result.sort(
            key=lambda item: (
                item["battle_count"],
                item["character_id"],
            ),
            reverse=True,
        )

        cls._debug_print(
            "严格识别到的角色战绩",
            result,
        )

        return result

    @staticmethod
    def _character_name(character_id: int) -> str:
        if character_id <= 0:
            return ""

        tool_name = CHARACTER_ID_MAP.get(character_id)

        if not tool_name:
            return f"未知角色(ID={character_id})"

        return CHARACTER_NAMES.get(
            tool_name,
            tool_name,
        )

    @staticmethod
    def _debug_print(title: str, value):
        """在 AstrBot 控制台打印格式化调试信息。"""
        if not DEBUG_SF6:
            return

        print("\n" + "=" * 80)
        print(f"[SF6 DEBUG] {title}")
        print("-" * 80)

        try:
            print(
                json.dumps(
                    value,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
        except Exception:
            print(repr(value))

        print("=" * 80 + "\n")


    @classmethod
    def _parse_character_ranks(
        cls,
        play_props: dict,
    ) -> list[dict]:
        play = play_props.get("play", {})

        if not isinstance(play, dict):
            return []

        league_infos = play.get(
            "character_league_infos",
            [],
        )

        if not isinstance(league_infos, list):
            return []

        result = []

        for item in league_infos:
            if not isinstance(item, dict):
                continue

            character_id = _to_int(
                item.get("character_id"),
                0,
            )

            if character_id in (0, 253, 254):
                continue

            league_info = item.get("league_info", {})

            if not isinstance(league_info, dict):
                continue

            rank = _to_int(
                league_info.get("league_rank"),
                0,
            )
            lp = _to_int(
                league_info.get("league_point"),
                0,
            )
            mr = _to_int(
                league_info.get("master_rating"),
                0,
            )
            mr_ranking = _to_int(
                league_info.get(
                    "master_rating_ranking"
                ),
                0,
            )

            # league_rank=39 且 LP=-1 表示未定级角色。
            if rank == 39 and lp < 0 and mr <= 0:
                continue

            if rank <= 0 and lp <= 0 and mr <= 0:
                continue

            result.append({
                "character_id": character_id,
                "rank": rank,
                "lp": max(lp, 0),
                "mr": max(mr, 0),
                "mr_ranking": max(mr_ranking, 0),
            })

        return result

    @classmethod
    def _compact_debug_value(
        cls,
        value,
        path: tuple = (),
        depth: int = 0,
    ):
        """
        只保留排查 SF6 数据解析所需的字段。
        不保存完整接口响应，避免 debug 文件过大。
        """
        if depth > 8:
            if isinstance(value, dict):
                return {
                    "_type": "dict",
                    "_keys": list(value.keys()),
                }

            if isinstance(value, list):
                return {
                    "_type": "list",
                    "_length": len(value),
                }

            return value

        interesting_words = (
            "character",
            "fighter",
            "player",
            "personal",
            "short",
            "id",
            "round",
            "result",
            "win",
            "lose",
            "loss",
            "battle",
            "match",
            "rank",
            "league",
            "point",
            "rating",
            "mode",
            "type",
            "replay",
            "record",
            "user",
            "name",
            "info",
        )

        current_path = "/".join(
            str(part) for part in path
        ).lower()

        path_is_interesting = any(
            word in current_path
            for word in interesting_words
        )

        if isinstance(value, dict):
            result = {
                "_keys": list(value.keys()),
            }

            for key, child in value.items():
                key_text = str(key).lower()

                key_is_interesting = any(
                    word in key_text
                    for word in interesting_words
                )

                # 相关字段继续递归；无关字段只保留类型信息。
                if key_is_interesting or path_is_interesting:
                    result[str(key)] = cls._compact_debug_value(
                        child,
                        path=path + (key,),
                        depth=depth + 1,
                    )

            return result

        if isinstance(value, list):
            # Battlelog 通常是 replay_list 或类似列表。
            # 只保留前 3 条，足够确认真实字段结构。
            items = value[:3]

            return {
                "_type": "list",
                "_length": len(value),
                "_items": [
                    cls._compact_debug_value(
                        item,
                        path=path + (index,),
                        depth=depth + 1,
                    )
                    for index, item in enumerate(items)
                ],
            }

        if isinstance(value, (str, int, float, bool)) or value is None:
            return value

        return str(value)

    @classmethod
    def _compact_page_debug(cls, page: dict) -> dict:
        if not isinstance(page, dict):
            return {
                "_type": type(page).__name__,
            }

        page_props = page.get("pageProps")

        result = {
            "page_keys": list(page.keys()),
        }

        if isinstance(page_props, dict):
            result["pageProps_keys"] = list(
                page_props.keys()
            )
            result["pageProps"] = cls._compact_debug_value(
                page_props,
                path=("pageProps",),
            )
        else:
            result["pageProps"] = cls._compact_debug_value(
                page_props,
                path=("pageProps",),
            )

        return result
    @staticmethod
    def _save_debug_json(short_id: str, data: dict) -> str:
        """
        将完整接口响应保存到插件目录下的 debug 文件夹。
        不会包含请求 Cookie，但不要公开发送整个文件。
        """
        debug_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "debug",
        )
        os.makedirs(debug_dir, exist_ok=True)

        file_path = os.path.join(
            debug_dir,
            f"{short_id}.json",
        )

        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
                default=str,
            )

        print(f"[SF6 DEBUG] 精简调试数据已保存: {file_path}")
        return file_path

    @classmethod
    def _debug_character_candidates(cls, *sources):
        """
        打印程序找到的所有角色段位候选。

        重点检查：
        - character_id
        - rank
        - lp
        - path
        - 原始 data
        """
        if not DEBUG_SF6:
            return []

        candidates = []

        for source_index, source in enumerate(sources):
            if not source:
                continue

            found = cls._collect_character_ranks(
                source,
                path=(f"source_{source_index}",),
            )

            candidates.extend(found)

        result = []

        for item in candidates:
            character_id = _to_int(
                item.get("character_id"),
                0,
            )

            tool_name = CHARACTER_ID_MAP.get(
                character_id,
                "",
            )

            character_name = CHARACTER_NAMES.get(
                tool_name,
                f"未知角色(ID={character_id})",
            )

            rank = _to_int(item.get("rank"), 0)
            lp = _to_int(item.get("lp"), 0)
            mr = _to_int(item.get("mr"), 0)

            result.append({
                "character_id": character_id,
                "tool_name": tool_name,
                "character_name": character_name,
                "rank": rank,
                "rank_name": RANK_NAMES.get(
                    rank,
                    f"未知段位({rank})",
                ),
                "lp": lp,
                "mr": mr,
                "mr_ranking": _to_int(
                    item.get("mr_ranking"),
                    0,
                ),
                "path": item.get("path", ""),
                "raw_data": item.get("data", {}),
            })

        # 按段位、LP、MR从高到低排序，方便观察。
        result.sort(
            key=lambda item: (
                item["rank"],
                item["lp"],
                item["mr"],
            ),
            reverse=True,
        )

        cls._debug_print(
            "识别到的全部角色段位候选",
            result,
        )

        return result


    @classmethod
    def _debug_scan_rank_fields(
        cls,
        value,
        path: tuple = (),
        result: Optional[list] = None,
    ) -> list:
        """
        扫描 JSON 中所有疑似角色/段位字段。

        即使当前解析器没有识别成功，也可以从这里看到真实字段名。
        """
        if result is None:
            result = []

        interesting_words = (
            "character",
            "fighter",
            "league",
            "rank",
            "point",
            "rating",
            "favorite",
        )

        if isinstance(value, dict):
            matched = {}

            for key, child in value.items():
                key_lower = str(key).lower()

                if any(word in key_lower for word in interesting_words):
                    # 避免把巨大列表完整打印到控制台。
                    if isinstance(child, list):
                        matched[key] = {
                            "_type": "list",
                            "_length": len(child),
                        }
                    elif isinstance(child, dict):
                        matched[key] = {
                            "_type": "dict",
                            "_keys": list(child.keys()),
                        }
                    else:
                        matched[key] = child

            if matched:
                result.append({
                    "path": "/".join(
                        str(item) for item in path
                    ),
                    "fields": matched,
                })

            for key, child in value.items():
                cls._debug_scan_rank_fields(
                    child,
                    path + (key,),
                    result,
                )

        elif isinstance(value, list):
            for index, child in enumerate(value):
                cls._debug_scan_rank_fields(
                    child,
                    path + (index,),
                    result,
                )

        return result

    @classmethod
    def _collect_character_ranks(
        cls,
        value,
        inherited_character_id: int = 0,
        path: tuple = (),
    ) -> list[dict]:
        """
        从 profile 和 play 的完整 JSON 中递归寻找角色段位数据。

        会把父级 character_id 传递给子级 league_info，
        同时排除 favorite_character_league_info，防止把当前角色
        误认为最高段位角色。
        """
        result = []

        if isinstance(value, dict):
            current_path = "/".join(str(x) for x in path).lower()

            # 这里是当前展示角色的段位，不是全角色列表，必须排除。
            if (
                "favorite_character_league_info" in current_path
                or "favoritecharacterleagueinfo" in current_path
            ):
                return result

            character_id = inherited_character_id

            for key in (
                "character_id",
                "characterId",
                "character_no",
                "characterNo",
                "character_id_number",
            ):
                if key in value:
                    candidate_id = _to_int(value.get(key), 0)
                    if candidate_id > 0:
                        character_id = candidate_id
                        break

            rank = _to_int(
                value.get("league_rank")
                or value.get("leagueRank")
                or value.get("rank_id")
                or value.get("rankId")
                or 0
            )

            lp = _to_int(
                value.get("league_point")
                or value.get("leaguePoint")
                or value.get("league_points")
                or value.get("lp")
                or 0
            )

            mr = _to_int(
                value.get("master_rating")
                or value.get("masterRating")
                or value.get("mr")
                or 0
            )

            mr_ranking = _to_int(
                value.get("master_rating_ranking")
                or value.get("masterRatingRanking")
                or value.get("mr_ranking")
                or 0
            )

            # 必须同时能确定角色 ID，不能把玩家总段位或无关 rank
            # 字段当成角色段位。
            if (
                    character_id > 0
                    and character_id != 253
                    and (
                    1 <= rank <= 36
                    or lp > 0
                    or mr > 0
            )
            ):
                result.append({
                    "character_id": character_id,
                    "rank": rank,
                    "lp": lp,
                    "mr": mr,
                    "mr_ranking": mr_ranking,
                    "path": "/".join(str(x) for x in path),
                    "data": value,
                })

            for key, child in value.items():
                result.extend(
                    cls._collect_character_ranks(
                        child,
                        inherited_character_id=character_id,
                        path=path + (key,),
                    )
                )

        elif isinstance(value, list):
            for index, child in enumerate(value):
                result.extend(
                    cls._collect_character_ranks(
                        child,
                        inherited_character_id=inherited_character_id,
                        path=path + (index,),
                    )
                )

        return result

    @classmethod
    def _find_highest_character_rank(cls, *sources) -> Optional[dict]:
        """
        同时从 profile、play 等数据源中寻找最高段位角色。
        """
        all_candidates = []

        for index, source in enumerate(sources):
            if source:
                all_candidates.extend(
                    cls._collect_character_ranks(
                        source,
                        path=(f"source_{index}",),
                    )
                )

        if not all_candidates:
            return None

        # 同一角色可能在 JSON 中重复出现，保留该角色最高的一条。
        best_by_character = {}

        for item in all_candidates:
            character_id = item["character_id"]
            old = best_by_character.get(character_id)

            if old is None:
                best_by_character[character_id] = item
                continue

            old_key = (
                1 if old["rank"] >= 36 else 0,
                old["rank"],
                old["mr"],
                old["lp"],
            )
            new_key = (
                1 if item["rank"] >= 36 else 0,
                item["rank"],
                item["mr"],
                item["lp"],
            )

            if new_key > old_key:
                best_by_character[character_id] = item

        # 大师优先比较 MR；非大师优先比较段位编号，再比较 LP。
        def rank_key(item):
            rank = item["rank"]

            if rank >= 36:
                return (
                    1,
                    item["mr"],
                    item["lp"],
                )

            return (
                0,
                rank,
                item["lp"],
            )

        return max(
            best_by_character.values(),
            key=rank_key,
        )
    def set_cookies(self, cookie_str: str):
        if os.path.exists(cookie_str):
            with open(cookie_str, "r", encoding="utf-8") as f:
                cookie_str = f.read().strip()
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                self._http.cookies.set(k.strip(), v.strip())

    def set_proxy(self, proxy: str):
        set_proxy(proxy, proxy)

    # ---- Web API 方法 ----

    def _get_build_id(self) -> str:
        if self._build_id:
            return self._build_id
        r = self._http.get(WEB_BASE + "/6/buckler/zh-hans", timeout=15, proxies=PROXIES)
        r.raise_for_status()
        m = re.search(r'buildId["\']?\s*:\s*["\']([^"\']+)["\']', r.text)
        if m:
            self._build_id = m.group(1)
            return self._build_id
        raise RuntimeError("无法获取 Next.js buildId")

    def _web_get_json(self, path: str) -> dict:
        r = self._http.get(WEB_BASE + path, headers={"Accept": "application/json"}, timeout=15, proxies=PROXIES)
        r.raise_for_status()
        return r.json()

    def get_my_info(self) -> dict:
        """获取当前登录用户信息"""
        return self._web_get_json("/6/buckler/api/auth/getlogindata")

    def get_my_short_id(self) -> str:
        if self._my_short_id:
            return self._my_short_id
        info = self.get_my_info()
        self._my_short_id = str(info.get("loginUser", {}).get("shortId", ""))
        return self._my_short_id

    def get_friend_list(self) -> list[dict]:
        """获取好友列表(含 short_id 和 fighter_id)"""
        if self._friend_cache:
            return self._friend_cache
        bid = self._get_build_id()
        data = self._web_get_json(f"/6/buckler/_next/data/{bid}/zh-hans/fighterslist/friend.json")
        friends = data.get("pageProps", {}).get("friend_list", [])
        self._friend_cache = []
        for f in friends:
            info = f.get("fighter_banner_info", {})
            personal = info.get("personal_info", {})
            self._friend_cache.append({
                "short_id": str(personal.get("short_id", "")),
                "fighter_id": personal.get("fighter_id", ""),
                "platform": personal.get("platform_name", ""),
                "favorite_character_id": info.get("favorite_character_id", 0),
                "lp": info.get("favorite_character_league_info", {}).get("league_point", 0),
                "mr": info.get("favorite_character_league_info", {}).get("master_rating", 0),
            })
        return self._friend_cache

    def search_friend(self, name: str) -> Optional[str]:
        """在好友列表中搜索，返回 short_id"""
        friends = self.get_friend_list()
        name_lower = name.strip().lower()
        for f in friends:
            if name_lower in f["fighter_id"].lower():
                return f["short_id"]
        return None

    def search_all_friends(self, name: str) -> list[dict]:
        """在好友列表中搜索，返回所有匹配（模糊匹配）"""
        friends = self.get_friend_list()
        name_lower = name.strip().lower()
        return [f for f in friends if name_lower in f["fighter_id"].lower()]

    @classmethod
    def _find_ranked_character_usage(cls, *sources) -> list[dict]:
        found = {}

        ranked_words = (
            "ranked",
            "rank_battle",
            "rankbattle",
            "rank_match",
            "rankmatch",
            "league_battle",
            "leaguebattle",
            "league_match",
            "leaguematch",
            "rankedbattle",
            "rankedmatch",
        )

        character_keys = (
            "character_id",
            "characterId",
            "character_no",
            "characterNo",
            "character_id_number",
        )

        win_keys = (
            "win_count",
            "winCount",
            "wins",
            "total_wins",
            "totalWins",
        )

        loss_keys = (
            "lose_count",
            "loseCount",
            "loss_count",
            "lossCount",
            "losses",
            "total_losses",
            "totalLosses",
        )

        match_keys = (
            "battle_count",
            "battleCount",
            "match_count",
            "matchCount",
            "total_matches",
            "totalMatches",
        )

        def first_present(data: dict, keys: tuple):
            for key in keys:
                if key in data:
                    return data.get(key)
            return None

        def direct_character_id(data: dict) -> int:
            value = first_present(data, character_keys)
            if value is not None:
                return _to_int(value, 0)

            for key in (
                "character_info",
                "characterInfo",
                "fighter_info",
                "fighterInfo",
            ):
                child = data.get(key)
                if not isinstance(child, dict):
                    continue
                value = first_present(child, character_keys)
                if value is not None:
                    return _to_int(value, 0)

            return 0

        def is_ranked(data: dict, path: tuple) -> bool:
            path_text = "/".join(str(p) for p in path).lower()
            key_text = " ".join(str(k).lower() for k in data.keys())
            return any(
                word in path_text or word in key_text
                for word in ranked_words
            )

        def walk(value, path=()):
            if isinstance(value, dict):
                if is_ranked(value, path):
                    character_id = direct_character_id(value)
                    raw_wins = first_present(value, win_keys)
                    raw_losses = first_present(value, loss_keys)
                    raw_matches = first_present(value, match_keys)

                    if (
                        character_id > 0
                        and character_id not in (253, 254)
                        and raw_wins is not None
                        and raw_matches is not None
                    ):
                        wins = _to_int(raw_wins, 0)
                        matches = _to_int(raw_matches, 0)

                        if raw_losses is None:
                            losses = matches - wins
                        else:
                            losses = _to_int(raw_losses, 0)

                        valid = (
                            matches > 0
                            and wins >= 0
                            and losses >= 0
                            and wins <= matches
                        )

                        if valid:
                            if raw_losses is not None:
                                counted_matches = wins + losses
                                if counted_matches > matches:
                                    valid = False

                            if valid:
                                item = {
                                    "character_id": character_id,
                                    "win_count": wins,
                                    "lose_count": losses,
                                    "battle_count": matches,
                                    "path": "/".join(
                                        str(part) for part in path
                                    ),
                                }

                                old = found.get(character_id)
                                if (
                                    old is None
                                    or matches > old["battle_count"]
                                ):
                                    found[character_id] = item

                for key, child in value.items():
                    walk(child, path + (key,))

            elif isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, path + (index,))

        for source_index, source in enumerate(sources):
            if source:
                walk(
                    source,
                    path=(f"source_{source_index}",),
                )

        result = list(found.values())
        result.sort(
            key=lambda item: (
                item["battle_count"],
                item["character_id"],
            ),
            reverse=True,
        )

        cls._debug_print(
            "识别到的排位角色战绩",
            result,
        )

        return result

    @classmethod
    def _parse_character_usage(
        cls,
        play_props: dict,
    ) -> list[dict]:
        play = play_props.get("play", {})

        if not isinstance(play, dict):
            return []

        win_rates = play.get("character_win_rates", [])

        if not isinstance(win_rates, list):
            return []

        result = []

        for item in win_rates:
            if not isinstance(item, dict):
                continue

            character_id = _to_int(
                item.get("character_id"),
                0,
            )

            if character_id in (0, 253, 254):
                continue

            win_count = _to_int(
                item.get("win_count"),
                0,
            )

            battle_count = _to_int(
                item.get("battle_count"),
                0,
            )

            if battle_count <= 0:
                continue

            if win_count < 0 or win_count > battle_count:
                continue

            result.append({
                "character_id": character_id,
                "win_count": win_count,
                "lose_count": battle_count - win_count,
                "battle_count": battle_count,
            })

        return result

    def get_profile(self, short_id: str) -> Optional[PlayerProfile]:
        """通过 short_id 获取玩家资料和游玩数据。"""
        bid = self._get_build_id()

        profile_page = self._web_get_json(
            f"/6/buckler/_next/data/{bid}/zh-hans/"
            f"profile/{short_id}.json"
        )

        pp = profile_page.get("pageProps", {})

        if not isinstance(pp, dict):
            return None

        if pp.get("errorMessage"):
            return None

        fb = pp.get("fighter_banner_info", {})

        if not isinstance(fb, dict) or not fb:
            return None

        personal = fb.get("personal_info", {})
        if not isinstance(personal, dict):
            personal = {}

        # 当前展示或最近游玩的角色。
        current_character_id = _to_int(
            fb.get("favorite_character_id")
            or fb.get("favoriteCharacterId")
            or 0
        )

        current_character_name = self._character_name(
            current_character_id
        )

        self._debug_print(
            "profile 中的 fighter_banner_info 关键数据",
            {
                "short_id": short_id,
                "personal_info": personal,
                "favorite_character_id": fb.get(
                    "favorite_character_id"
                ),
                "favoriteCharacterId": fb.get(
                    "favoriteCharacterId"
                ),
                "favorite_character_league_info": fb.get(
                    "favorite_character_league_info"
                ),
                "last_play_at": fb.get("last_play_at"),
                "fighter_banner_info_keys": list(fb.keys()),
            },
        )

        # 获取独立的 play 页面。
        try:
            play_page = self.get_play_data(short_id)
        except Exception as exc:
            play_page = {
                "_request_error": str(exc),
            }

        if not isinstance(play_page, dict):
            play_page = {}

        play_props = play_page.get("pageProps", {})
        if not isinstance(play_props, dict):
            play_props = {}


        self._debug_print(
            "play 页面基本结构",
            {
                "play_page_keys": (
                    list(play_page.keys())
                    if isinstance(play_page, dict)
                    else []
                ),
                "pageProps_keys": list(play_props.keys()),
                "request_errors": play_page.get(
                    "_request_errors"
                ),
                "request_error": play_page.get(
                    "_request_error"
                ),
            },
        )

        debug_candidates = self._debug_character_candidates(
            pp,
            play_props,
        )

        profile_rank_fields = self._debug_scan_rank_fields(
            pp,
            path=("profile",),
        )

        play_rank_fields = self._debug_scan_rank_fields(
            play_props,
            path=("play",),
        )

        self._debug_print(
            "profile 中所有疑似角色/段位字段",
            profile_rank_fields,
        )

        self._debug_print(
            "play 中所有疑似角色/段位字段",
            play_rank_fields,
        )

        # 同时搜索 profile 和 play。
        # 绝不回退到 favorite_character_league_info。
        highest = self._find_highest_character_rank(
            pp,
            play_props,
        )

        self._debug_print(
            "最终选中的最高段位候选",
            highest,
        )

        if highest is None:
            highest_rank = 0
            highest_lp = 0
            highest_mr = 0
            highest_mr_ranking = 0
            highest_character_id = 0
            highest_character_name = ""
        else:
            highest_rank = highest["rank"]
            highest_lp = highest["lp"]
            highest_mr = highest["mr"]
            highest_mr_ranking = highest["mr_ranking"]
            highest_character_id = highest["character_id"]
            highest_character_name = self._character_name(
                highest_character_id
            )

        character_ranks = self._parse_character_ranks(
            play_props,
        )

        stats_source = {
            "profile": pp,
            "play": play_props,
        }

        battle_stats = self._find_battle_stats(
            stats_source
        )

        # 首先尝试从 play/profile 中读取累计排位统计。
        ranked_battle_stats = self._find_ranked_battle_stats(
            stats_source
        )

        # rank.json 是独立的排位 Battlelog。
        try:
            rank_battlelog_page = (
                self.get_rank_battlelog_data(short_id)
            )
        except Exception as exc:
            rank_battlelog_page = {
                "_request_error": str(exc),
            }

        rank_page_props = rank_battlelog_page.get(
            "pageProps",
            {},
        )

        if not isinstance(rank_page_props, dict):
            rank_page_props = {}

        rank_replay_list = rank_page_props.get(
            "replay_list",
            [],
        )

        if not isinstance(rank_replay_list, list):
            rank_replay_list = []

        rank_replay_stats = self._parse_rank_replay_list(
            rank_replay_list,
            short_id,
        )

        # 如果 play/profile 没有提供完整的排位胜负统计，
        # 回退到 rank.json 当前返回页的排位记录。
        #
        # 注意：rank.json 的 replay_list 是近期记录，
        # 不能和 play.rank_match_play_count 的累计场次混用。
        if (
                ranked_battle_stats["matches"] <= 0
                and rank_replay_stats["matches"] > 0
        ):
            ranked_battle_stats = {
                "wins": rank_replay_stats["wins"],
                "losses": rank_replay_stats["losses"],
                "matches": rank_replay_stats["matches"],
                "path": (
                    "rank_battlelog/"
                    "pageProps/replay_list"
                ),
                "is_recent": True,
            }
        else:
            ranked_battle_stats["is_recent"] = False

        ranked_matches_from_play = (
            self._find_ranked_match_count(
                pp,
                play_props,
            )
        )

        # 只有 play/profile 已经提供了累计排位胜场时，
        # 才能用累计排位场次补全。
        #
        # 如果当前数据来自 rank.json 的近期记录，
        # 绝不能把近期胜场和累计场次拼在一起。
        if (
                not ranked_battle_stats.get("is_recent")
                and ranked_battle_stats["matches"] > 0
                and ranked_matches_from_play > 0
                and 0 <= ranked_battle_stats["wins"] <= ranked_matches_from_play
        ):
            ranked_battle_stats["matches"] = (
                ranked_matches_from_play
            )

            ranked_battle_stats["losses"] = (
                    ranked_matches_from_play
                    - ranked_battle_stats["wins"]
            )

        total_wins = battle_stats["wins"]
        total_losses = battle_stats["losses"]
        total_matches = battle_stats["matches"]

        ranked_wins = ranked_battle_stats["wins"]
        ranked_losses = ranked_battle_stats["losses"]
        ranked_matches = ranked_battle_stats["matches"]


        win_streak = 0

        for source in (play_props, pp):
            for item in _walk_dicts(source):
                value = _to_int(
                    item.get("win_streak")
                    or item.get("current_win_streak")
                    or 0
                )

                if value > win_streak:
                    win_streak = value

        last_play_at = _to_int(
            fb.get("last_play_at")
            or fb.get("last_played_at")
            or fb.get("last_play_time")
            or 0
        )

        try:
            battlelog_page = self.get_battlelog_data(short_id)
        except Exception as exc:
            battlelog_page = {
                "_request_error": str(exc),
            }

        character_usage = self._parse_character_usage(
            play_props,
        )

        if not character_usage:
            character_usage = (
                self._find_battlelog_character_usage(
                    battlelog_page,
                    short_id,
                )
            )

        season_id = 0
        play_data = play_props.get("play", {})
        if isinstance(play_data, dict):
            season_id = _to_int(
                play_data.get("current_season_id"),
                0,
            )

        character_ranked_usage = []
        if season_id > 0:
            try:
                ranked_response = self.get_character_winrates(
                    short_id,
                    season_id=season_id,
                    mode_id=2,
                )
                character_ranked_usage = (
                    self._parse_character_winrates_response(
                        ranked_response,
                    )
                )
            except Exception:
                pass

        if not character_ranked_usage:
            character_ranked_usage = self._find_ranked_character_usage(
                pp,
                play_props,
            )

        if not character_ranked_usage:
            character_ranked_usage = [
                {
                    "character_id": item["character_id"],
                    "win_count": item.get("wins", 0),
                    "lose_count": item.get("losses", 0),
                    "battle_count": item.get("matches", 0),
                }
                for item in rank_replay_stats["characters"].values()
            ]

        if character_ranked_usage:
            total_rw = sum(
                item.get("win_count", 0)
                for item in character_ranked_usage
            )
            total_rl = sum(
                item.get("lose_count", 0)
                for item in character_ranked_usage
            )
            total_rm = sum(
                item.get("battle_count", 0)
                for item in character_ranked_usage
            )
            if total_rm > ranked_matches:
                ranked_wins = total_rw
                ranked_losses = total_rl
                ranked_matches = total_rm

        self._debug_print(
            "提取到的角色使用统计",
            character_usage,
        )

        raw = dict(pp)

        # 把独立 play 页面也放进原始输出中。
        raw["_play_page"] = play_page
        raw["_battlelog_page"] = battlelog_page

        raw["_rank_battlelog_page"] = (
            rank_battlelog_page
        )

        # 加入解析调试结果，方便判断程序到底读到了什么。
        raw["_parsed_result"] = {
            "current_character": {
                "character_id": current_character_id,
                "character_name": current_character_name,
                "original_favorite_character_id": fb.get(
                    "favorite_character_id"
                ),
            },
            "highest_character": highest,
            "all_character_candidates": debug_candidates,
            "battle_stats": battle_stats,
            "ranked_battle_stats": ranked_battle_stats,
            "rank_replay_stats": rank_replay_stats,
            "character_usage": character_usage,
            "character_ranked_usage": character_ranked_usage,
        }

        character_rank_candidates = []

        for source_index, source in enumerate(
            (pp, play_props)
        ):
            character_rank_candidates.extend(
                self._collect_character_ranks(
                    source,
                    path=(f"source_{source_index}",),
                )
            )

        debug_data = {
            "short_id": short_id,

            "rank_battlelog_summary": (
                self._compact_page_debug(
                    rank_battlelog_page,
                )
            ),

            "profile_summary": self._compact_page_debug(
                profile_page,
            ),

            "play_summary": self._compact_page_debug(
                play_page,
            ),

            "battlelog_summary": self._compact_page_debug(
                battlelog_page,
            ),

            "parsed_result": raw["_parsed_result"],

            "character_rank_candidates": (
                character_rank_candidates
            ),

            "profile_rank_fields": profile_rank_fields,
            "play_rank_fields": play_rank_fields,
        }
        if DEBUG_SF6:
            self._save_debug_json(
                short_id,
                debug_data,
            )



        return PlayerProfile(
            name=str(personal.get("fighter_id", "")),
            short_id=str(personal.get("short_id", short_id)),
            platform=str(personal.get("platform_name", "")),

            league=0,
            league_rank=highest_rank,
            lp=highest_lp,
            mr=highest_mr,
            mr_ranking=highest_mr_ranking,

            total_wins=total_wins,
            total_losses=total_losses,
            total_matches=total_matches,
            win_streak=win_streak,

            ranked_wins=ranked_wins,
            ranked_losses=ranked_losses,
            ranked_matches=ranked_matches,

            favorite_character_id=current_character_id,
            favorite_character_name=current_character_name,

            highest_character_id=highest_character_id,
            highest_character_name=highest_character_name,

            character_usage=character_usage,
            character_ranked_usage=character_ranked_usage,
            character_ranks=character_ranks,
            last_play_at=last_play_at,
            raw=raw,
        )

    # ---- Game API 方法 (需要 rebe_token) ----

    def set_rebe_token(self, token: str):
        self._rebe_token = token
        self._authenticated = False

    def _capi_headers(self) -> dict:
        h = {
            "Content-Type": "application/msgpack",
            "User-Agent": CAPI_USER_AGENT,
            "version-major": str(CLIENT_VERSION["major"]),
            "version-minor": str(CLIENT_VERSION["minor"]),
            "version-patch": str(CLIENT_VERSION["patch"]),
            "version-battle": str(CLIENT_VERSION["battle"]),
            "x-rebe-token": self._rebe_token,
            "Cookie": "; ".join(f"{c.name}={c.value}" for c in self._http.cookies),
        }
        if self._session_id and self._nonce:
            h["Authorization"] = f'Session id="{self._session_id}",nonce="{self._nonce}"'
        return h

    def _capi_post(self, path: str, body: dict) -> dict:
        import msgpack
        url = CAPI_URL + path
        raw = msgpack.packb(body)
        r = self._http.post(url, data=raw, headers=self._capi_headers(), timeout=15, proxies=PROXIES)
        r.raise_for_status()
        data = msgpack.unpackb(r.content)
        nonce = r.headers.get("x-session-nonce")
        if nonce:
            self._nonce = nonce
        return data

    def login_with_token(self) -> bool:
        if not self._rebe_token:
            raise ValueError("rebe_token 未设置")
        if _is_jwt_expired(self._rebe_token):
            raise ValueError("rebe_token 已过期，请重新获取")

        result = self._capi_post("/auth/login", {
            "language_id": 1,
            "machine_detail": "PC",
            "main_language": 3,
            "os_version": "Windows 10(19044)",
            "privacy_policy_agreement": False,
            "rebe_token": self._rebe_token,
            "utc_offset_minutes": 480,
        })

        if not result.get("success"):
            raise RuntimeError(f"登录失败: {result.get('errmsg', '未知错误')}")

        login_info = result["data"]["login_info"]
        self._session_id = login_info["session_id"]
        self._nonce = login_info.get("nonce", "")
        self._my_short_id = str(login_info.get("short_id", ""))
        self._authenticated = True
        return True

    def search_player(self, name: str) -> Optional[dict]:
        """通过 CFN 名称搜索玩家，需要有效的 rebe_token。"""
        if not self._authenticated:
            self.login_with_token()

        result = self._capi_post(
            "/fighter/search/fighter_id",
            {"query": name.strip()},
        )

        if not result.get("success"):
            return None

        data = result.get("data") or {}
        fighters = (
            data.get("fighters")
            or data.get("fighter_list")
            or data.get("results")
            or []
        )

        if not fighters:
            return None

        return fighters[0]

    @staticmethod
    def _find_ranked_match_count(*sources) -> int:
        """
        读取 Buckler play.battle_stats.rank_match_play_count。
        """
        for source in sources:
            if not isinstance(source, dict):
                continue

            play = source.get("play")

            if not isinstance(play, dict):
                continue

            battle_stats = play.get("battle_stats")

            if not isinstance(battle_stats, dict):
                continue

            count = _to_int(
                battle_stats.get("rank_match_play_count"),
                0,
            )

            if count > 0:
                return count

        return 0


    @staticmethod
    def _find_battle_stats(value) -> dict:
        """
        递归寻找胜负统计。

        如果找到多组统计，优先选择 battle_count 最大的一组，
        它通常代表总体统计，而不是单角色统计。
        """
        candidates = []

        def walk(node, path=()):
            if isinstance(node, dict):
                wins = _to_int(
                    node.get("win_count")
                    or node.get("winCount")
                    or node.get("wins")
                    or node.get("total_wins")
                    or 0
                )

                loss_keys = (
                    "lose_count",
                    "loseCount",
                    "loss_count",
                    "lossCount",
                    "losses",
                    "total_losses",
                    "totalLosses",
                )

                raw_losses = None

                for key in loss_keys:
                    if key in node and node.get(key) is not None:
                        raw_losses = node.get(key)
                        break

                losses = _to_int(raw_losses, 0)

                matches = _to_int(
                    node.get("battle_count")
                    or node.get("battleCount")
                    or node.get("match_count")
                    or node.get("matchCount")
                    or node.get("total_matches")
                    or 0
                )

                if matches <= 0 and (wins > 0 or losses > 0):
                    matches = wins + losses

                # Buckler 的 character_win_rates 总记录只有：
                # battle_count + win_count，没有 lose_count。
                if raw_losses is None and matches >= wins:
                    losses = matches - wins

                if matches > 0:
                    candidates.append({
                        "wins": wins,
                        "losses": losses,
                        "matches": matches,
                        "path": "/".join(str(x) for x in path),
                        "data": node,
                    })

                for key, child in node.items():
                    walk(child, path + (key,))

            elif isinstance(node, list):
                for index, child in enumerate(node):
                    walk(child, path + (index,))

        walk(value)

        if not candidates:
            return {
                "wins": 0,
                "losses": 0,
                "matches": 0,
                "path": "",
            }

        return max(
            candidates,
            key=lambda item: (
                item["matches"],
                item["wins"] + item["losses"],
            ),
        )

    @staticmethod
    def _find_ranked_battle_stats(value) -> dict:
        """
        递归寻找排位赛胜负统计。

        只接受路径或字段名中明确包含 ranked/rank/league 的统计，
        避免把总胜率或休闲赛统计误认为排位胜率。
        """
        candidates = []

        ranked_words = (
            "ranked",
            "rank_battle",
            "rankbattle",
            "rank_match",
            "rankmatch",
            "league_battle",
            "leaguebattle",
            "league_match",
            "leaguematch",
            "rankedbattle",
            "rankedmatch",
        )

        win_keys = (
            "win_count",
            "winCount",
            "wins",
            "total_wins",
            "totalWins",
            "ranked_win_count",
            "rankedWinCount",
        )

        loss_keys = (
            "lose_count",
            "loseCount",
            "loss_count",
            "lossCount",
            "losses",
            "total_losses",
            "totalLosses",
            "ranked_lose_count",
            "rankedLoseCount",
            "ranked_loss_count",
            "rankedLossCount",
        )

        match_keys = (
            "battle_count",
            "battleCount",
            "match_count",
            "matchCount",
            "total_matches",
            "totalMatches",
            "ranked_battle_count",
            "rankedBattleCount",
            "ranked_match_count",
            "rankedMatchCount",
        )

        def get_first_number(node: dict, keys: tuple) -> int:
            for key in keys:
                if key in node and node.get(key) is not None:
                    return _to_int(node.get(key), 0)
            return 0

        def walk(node, path=()):
            if isinstance(node, dict):
                path_text = "/".join(
                    str(part) for part in path
                ).lower()

                key_text = " ".join(
                    str(key).lower()
                    for key in node.keys()
                )

                is_ranked = any(
                    word in path_text or word in key_text
                    for word in ranked_words
                )

                if is_ranked:
                    wins = get_first_number(node, win_keys)
                    losses = get_first_number(node, loss_keys)
                    matches = get_first_number(node, match_keys)

                    if matches <= 0 and (wins > 0 or losses > 0):
                        matches = wins + losses

                    if matches > 0:
                        candidates.append({
                            "wins": wins,
                            "losses": losses,
                            "matches": matches,
                            "path": "/".join(
                                str(part) for part in path
                            ),
                        })

                for key, child in node.items():
                    walk(child, path + (key,))

            elif isinstance(node, list):
                for index, child in enumerate(node):
                    walk(child, path + (index,))

        walk(value)

        if not candidates:
            return {
                "wins": 0,
                "losses": 0,
                "matches": 0,
                "path": "",
            }

        # 统计量最大的排位统计通常是总排位统计，
        # 而不是某个角色或某个子模式的统计。
        return max(
            candidates,
            key=lambda item: (
                item["matches"],
                item["wins"] + item["losses"],
            ),
        )
    def get_play_data(self, short_id: str) -> dict:
        bid = self._get_build_id()

        paths = [
            (
                f"/6/buckler/_next/data/{bid}/zh-hans/"
                f"profile/{short_id}/play.json?sid={short_id}"
            ),
            (
                f"/6/buckler/_next/data/{bid}/zh-hans/"
                f"profile/{short_id}/play.json"
            ),
        ]

        errors = []

        for path in paths:
            try:
                data = self._web_get_json(path)
                if isinstance(data, dict):
                    return data
            except Exception as exc:
                errors.append(f"{path}: {exc}")

        return {
            "_request_errors": errors,
        }

    def get_character_winrates(
        self,
        short_id: str,
        season_id: int = 0,
        mode_id: int = 2,
    ) -> dict:
        """
        调用 Buckler API 获取按角色统计的胜率数据。

        targetModeId:
          0 = 全部模式
          2 = 排位赛

        返回格式:
        {
            "response": {
                "character_win_rates": [
                    {
                        "battle_count": 74,
                        "character_id": 1,
                        "win_count": 44,
                        "character_name": "隆",
                        ...
                    },
                    ...
                ]
            }
        }
        """
        url = (
            f"{WEB_BASE}/6/buckler/api/"
            f"profile/play/act/characterwinrate"
        )

        payload = {
            "targetShortId": int(short_id),
            "targetSeasonId": season_id,
            "targetModeId": mode_id,
            "lang": "zh-hans",
        }

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": (
                f"{WEB_BASE}/6/buckler/zh-hans/"
                f"profile/{short_id}/play"
            ),
        }

        r = self._http.post(
            url,
            json=payload,
            headers=headers,
            timeout=15,
            proxies=PROXIES,
        )
        r.raise_for_status()

        return r.json()

    @staticmethod
    def _parse_character_winrates_response(
        api_response: dict,
    ) -> list[dict]:
        items = (
            api_response.get("response", {})
            .get("character_win_rates", [])
        )

        if not isinstance(items, list):
            return []

        result = []

        for item in items:
            if not isinstance(item, dict):
                continue

            character_id = _to_int(
                item.get("character_id"),
                0,
            )

            if character_id in (0, 253, 254):
                continue

            win_count = _to_int(
                item.get("win_count"),
                0,
            )
            battle_count = _to_int(
                item.get("battle_count"),
                0,
            )

            if battle_count <= 0:
                continue

            if win_count < 0 or win_count > battle_count:
                continue

            result.append({
                "character_id": character_id,
                "win_count": win_count,
                "lose_count": battle_count - win_count,
                "battle_count": battle_count,
            })

        return result

    SEARCH_PAGE_SIZE = 5

    def search_by_name(
        self,
        name: str,
        page: int = 1,
    ) -> dict:
        """
        按 CFN 名称搜索玩家。
        返回 {"results": [...], "page": int, "has_more": bool}
        """
        import urllib.parse

        search_name = name.strip()

        if len(search_name) < 4:
            return {
                "results": [],
                "page": page,
                "has_more": False,
                "error": "搜索词至少需要4个字符",
            }

        bid = self._get_build_id()

        encoded_name = urllib.parse.quote(search_name, safe="")
        path = (
            f"/6/buckler/_next/data/{bid}"
            f"/zh-hans/fighterslist/search/result.json"
            f"?fighter_id={encoded_name}"
            f"&page={page}"
        )

        data = self._web_get_json(path)

        pp = data.get("pageProps", {})

        if not isinstance(pp, dict):
            return {"results": [], "page": page, "has_more": False}

        raw_list = pp.get("fighter_banner_list", [])

        if not isinstance(raw_list, list):
            raw_list = []

        results = []

        for item in raw_list:
            if not isinstance(item, dict):
                continue

            personal = item.get("personal_info", {})
            league = item.get(
                "favorite_character_league_info",
                {},
            )

            results.append({
                "fighter_id": str(
                    personal.get("fighter_id", "")
                ),
                "short_id": str(
                    personal.get("short_id", "")
                ),
                "platform_name": str(
                    personal.get("platform_name", "")
                ),
                "favorite_character_id": _to_int(
                    item.get("favorite_character_id"),
                    0,
                ),
                "favorite_character_name": str(
                    item.get("favorite_character_name", "")
                ),
                "league_point": _to_int(
                    league.get("league_point"),
                    0,
                ),
                "league_rank": _to_int(
                    league.get("league_rank"),
                    0,
                ),
                "last_play_at": _to_int(
                    item.get("last_play_at"),
                    0,
                ),
                "play_time_zone": (
                    item.get("play_time_zone") or {}
                ),
            })

        has_more = len(raw_list) >= self.SEARCH_PAGE_SIZE

        return {
            "results": results,
            "page": page,
            "has_more": has_more,
        }

    def query_by_short_id(self, short_id: str, **params) -> str:
        """通过 short_id 直接查询"""
        profile = self.get_profile(short_id)
        if not profile:
            return f"未找到玩家 (short_id: {short_id})"
        return self._format(profile, **params)

    # ---- 格式化输出 ----

    def _format(self, p: PlayerProfile, **params) -> str:
        lines = [f"CFN: {p.name}"]

        show_all = not any(params.values())

        if params.get("rank") or show_all:
            lines.append(self._fmt_rank(p))

        if params.get("winrate") or show_all:
            lines.append(self._fmt_winrate(p))

        char_param = params.get("character")
        if char_param:
            lines.append(self._fmt_character(p, char_param))

        if params.get("history"):
            lines.append(self._fmt_history(p))

        if params.get("raw"):
            lines.append(json.dumps(p.raw, indent=2, ensure_ascii=False))

        return "\n".join(lines)

    @classmethod
    def _find_battlelog_character_usage(
        cls,
        battlelog_page: dict,
        short_id: str,
    ) -> list[dict]:
        """
        根据 Battlelog 中逐场记录，统计当前返回页的角色战绩。

        这是近期战绩，不是账号生涯累计数据。
        """
        usage = {}

        short_id_keys = (
            "short_id",
            "shortId",
            "player_id",
            "playerId",
        )

        winner_keys = (
            "result",
            "battle_result",
            "battleResult",
            "result_type",
            "resultType",
            "win",
            "is_win",
            "isWin",
        )

        def get_short_id(data: dict) -> str:
            if not isinstance(data, dict):
                return ""

            for key in short_id_keys:
                value = data.get(key)

                if value not in (None, ""):
                    return str(value)

            personal = (
                data.get("personal_info")
                or data.get("personalInfo")
            )

            if isinstance(personal, dict):
                return get_short_id(personal)

            return ""

        def get_result(data: dict) -> Optional[bool]:
            if not isinstance(data, dict):
                return None

            for key in winner_keys:
                if key not in data:
                    continue

                value = data.get(key)

                if isinstance(value, bool):
                    return value

                if isinstance(value, str):
                    normalized = value.strip().lower()

                    if normalized in (
                        "win",
                        "winner",
                        "won",
                        "true",
                        "1",
                    ):
                        return True

                    if normalized in (
                        "lose",
                        "loss",
                        "loser",
                        "lost",
                        "false",
                        "0",
                    ):
                        return False

                if isinstance(value, (int, float)):
                    # 常见表示：1=胜利，2=失败。
                    if int(value) == 1:
                        return True

                    if int(value) == 2:
                        return False

            return None

        def add(character_id: int, won: bool):
            if character_id <= 0:
                return

            item = usage.setdefault(
                character_id,
                {
                    "character_id": character_id,
                    "win_count": 0,
                    "lose_count": 0,
                    "battle_count": 0,
                },
            )

            item["battle_count"] += 1

            if won:
                item["win_count"] += 1
            else:
                item["lose_count"] += 1

        def inspect_player(data: dict):
            if not isinstance(data, dict):
                return

            player_short_id = get_short_id(data)

            if player_short_id != str(short_id):
                return

            character_id = _get_character_id(data)
            won = get_result(data)

            if character_id > 0 and won is not None:
                add(character_id, won)

        for data in _walk_dicts(battlelog_page):
            # 兼容玩家对象直接出现在 player1_info/player2_info 中。
            inspect_player(data)

            # 兼容一场对战对象中包含 player1/player2。
            for key in (
                "player1_info",
                "player1Info",
                "player2_info",
                "player2Info",
                "player1",
                "player2",
            ):
                player = data.get(key)

                if isinstance(player, dict):
                    inspect_player(player)

        return sorted(
            usage.values(),
            key=lambda item: (
                item["battle_count"],
                item["character_id"],
            ),
            reverse=True,
        )

    def get_battlelog_data(self, short_id: str) -> dict:
        bid = self._get_build_id()

        paths = [
            (
                f"/6/buckler/_next/data/{bid}/zh-hans/"
                f"profile/{short_id}/battlelog.json?sid={short_id}"
            ),
            (
                f"/6/buckler/_next/data/{bid}/zh-hans/"
                f"profile/{short_id}/battlelog.json"
            ),
        ]

        errors = []

        for path in paths:
            try:
                data = self._web_get_json(path)
                if isinstance(data, dict):
                    return data
            except Exception as exc:
                errors.append(f"{path}: {exc}")

        return {"_request_errors": errors}

    def get_rank_battlelog_data(
        self,
        short_id: str,
        page: int = 1,
    ) -> dict:
        """
        获取玩家排位 Battlelog。

        对应：
        /profile/{short_id}/battlelog/rank.json?sid={short_id}
        """
        bid = self._get_build_id()

        paths = [
            (
                f"/6/buckler/_next/data/{bid}/zh-hans/"
                f"profile/{short_id}/battlelog/rank.json"
                f"?sid={short_id}"
            ),
            (
                f"/6/buckler/_next/data/{bid}/zh-hans/"
                f"profile/{short_id}/battlelog/rank.json"
                f"?sid={short_id}&page={page}"
            ),
        ]

        errors = []

        for path in paths:
            try:
                data = self._web_get_json(path)

                if not isinstance(data, dict):
                    continue

                page_props = data.get("pageProps")

                if not isinstance(page_props, dict):
                    continue

                # Buckler 有时会在 200 响应中返回错误信息。
                error_message = (
                    page_props.get("errorMessage")
                    or page_props.get("error_message")
                )

                if error_message:
                    errors.append(
                        f"{path}: {error_message}"
                    )
                    continue

                return data

            except Exception as exc:
                errors.append(f"{path}: {exc}")

        raise RuntimeError(
            "无法获取排位数据："
            + (
                "；".join(errors)
                if errors
                else "接口未返回有效 JSON"
            )
        )


    @staticmethod
    def _find_short_id_in_player(player: dict) -> str:
        """
        从 replay_list 的玩家对象中读取 short_id。

        兼容：
        player.short_id
        player.personal_info.short_id
        player.fighter_banner_info.personal_info.short_id
        """
        if not isinstance(player, dict):
            return ""

        for key in (
            "short_id",
            "shortId",
            "player_id",
            "playerId",
        ):
            value = player.get(key)

            if value not in (None, ""):
                return str(value)

        for key in (
            "personal_info",
            "personalInfo",
            "player",
            "Player",
            "fighter_banner_info",
            "fighterBannerInfo",
            "player_info",
            "playerInfo",
            "player_1",
            "player_2",
        ):
            child = player.get(key)

            if isinstance(child, dict):
                result = SF6Client._find_short_id_in_player(
                    child
                )

                if result:
                    return result

        return ""

    @staticmethod
    def _normalize_battle_result(
        value,
    ) -> Optional[bool]:
        """
        将 Buckler 中常见的胜负值转换为：
        True  = 胜
        False = 负
        None  = 无法判断

        兼容两套编码：
        - result 字段：1 = 胜, 2 = 负
        - round_results：0 = 负, >0 = 胜（1=K.O., 5=CA, 6=时间到 等）
        """
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            normalized = value.strip().lower()

            if normalized in (
                "win",
                "winner",
                "won",
                "victory",
                "true",
                "w",
            ):
                return True

            if normalized in (
                "lose",
                "loss",
                "loser",
                "lost",
                "defeat",
                "false",
                "l",
            ):
                return False

            if normalized.isdigit():
                value = int(normalized)
            else:
                return None

        if isinstance(value, (int, float)):
            number = int(value)

            if number == 0:
                return False
            if number == 2:
                return False
            if number >= 1:
                return True

        return None

    @classmethod
    def _get_player_result(
        cls,
        player: dict,
    ) -> Optional[bool]:
        """
        从一方玩家的数据中判断胜负。

        优先读取明确的 result/is_win 字段；
        如果没有，则读取 round_results。
        """
        if not isinstance(player, dict):
            return None

        bool_result_keys = (
            "is_win",
            "isWin",
            "won",
            "winner",
        )

        normal_result_keys = (
            "result",
            "battle_result",
            "battleResult",
            "match_result",
            "matchResult",
            "win_lose",
            "winLose",
            "win_loss",
            "winLoss",
        )

        # is_win 允许使用 0/1。
        for key in bool_result_keys:
            if key not in player:
                continue

            value = player.get(key)

            if isinstance(value, bool):
                return value

            if isinstance(value, (int, float)):
                if int(value) == 1:
                    return True

                if int(value) == 0:
                    return False

            result = cls._normalize_battle_result(value)

            if result is not None:
                return result

        for key in normal_result_keys:
            if key not in player:
                continue

            result = cls._normalize_battle_result(
                player.get(key)
            )

            if result is not None:
                return result

        # 有些版本会把胜负放在子对象中。
        for key in (
            "battle_result_info",
            "battleResultInfo",
            "result_info",
            "resultInfo",
        ):
            child = player.get(key)

            if isinstance(child, dict):
                result = cls._get_player_result(child)

                if result is not None:
                    return result

        # 根据各回合结果判断整场胜负。
        round_results = (
            player.get("round_results")
            or player.get("roundResults")
            or player.get("round_result_list")
            or player.get("roundResultList")
        )

        if isinstance(round_results, list):
            round_wins = 0
            round_losses = 0

            for round_item in round_results:
                if isinstance(round_item, dict):
                    value = _first_value(
                        round_item,
                        (
                            "result",
                            "round_result",
                            "roundResult",
                            "battle_result",
                            "battleResult",
                        ),
                    )
                else:
                    value = round_item

                result = cls._normalize_battle_result(
                    value
                )

                if result is True:
                    round_wins += 1
                elif result is False:
                    round_losses += 1

            if round_wins > round_losses:
                return True

            if round_losses > round_wins:
                return False

        return None

    @classmethod
    def _get_replay_players(
        cls,
        replay: dict,
    ) -> tuple:
        """
        获取一条 Replay 中的 player1/player2。
        """
        if not isinstance(replay, dict):
            return None, None

        player1 = _first_value(
            replay,
            (
                "player1_info",
                "player1Info",
                "player_1_info",
                "player1",
                "player_1",
            ),
        )

        player2 = _first_value(
            replay,
            (
                "player2_info",
                "player2Info",
                "player_2_info",
                "player2",
                "player_2",
            ),
        )

        if not isinstance(player1, dict):
            player1 = None

        if not isinstance(player2, dict):
            player2 = None

        return player1, player2

    @classmethod
    def _get_replay_result(
        cls,
        replay: dict,
        short_id: str,
    ) -> tuple:
        """
        解析一条排位 Replay。

        返回：
        (won, character_id)

        won:
        True  = 查询玩家胜利
        False = 查询玩家失败
        None  = 无法识别
        """
        player1, player2 = cls._get_replay_players(
            replay
        )

        if player1 is None or player2 is None:
            return None, 0

        target_id = str(short_id)

        player1_id = cls._find_short_id_in_player(
            player1
        )
        player2_id = cls._find_short_id_in_player(
            player2
        )

        if player1_id == target_id:
            target_player = player1
            opponent_player = player2
            target_side = 1

        elif player2_id == target_id:
            target_player = player2
            opponent_player = player1
            target_side = 2

        else:
            return None, 0

        character_id = _get_character_id(
            target_player
        )

        # 第一优先级：查询玩家对象自身的胜负字段。
        won = cls._get_player_result(
            target_player
        )

        if won is not None:
            return won, character_id

        # 第二优先级：对手数据。
        opponent_result = cls._get_player_result(
            opponent_player
        )

        if opponent_result is not None:
            return not opponent_result, character_id

        # 第三优先级：Replay 顶层标记获胜方。
        for key in (
            "winner",
            "winner_side",
            "winnerSide",
            "winner_player",
            "winnerPlayer",
            "winner_player_number",
            "winnerPlayerNumber",
        ):
            if key not in replay:
                continue

            value = replay.get(key)

            if isinstance(value, str):
                normalized = value.strip().lower()

                if normalized in (
                    "player1",
                    "player_1",
                    "p1",
                ):
                    return target_side == 1, character_id

                if normalized in (
                    "player2",
                    "player_2",
                    "p2",
                ):
                    return target_side == 2, character_id

                if normalized.isdigit():
                    value = int(normalized)

            if isinstance(value, (int, float)):
                winner_side = int(value)

                if winner_side in (1, 2):
                    return (
                        winner_side == target_side,
                        character_id,
                    )

        # 第四优先级：比较双方回合胜场。
        score_keys = (
            "round_win_count",
            "roundWinCount",
            "win_round_count",
            "winRoundCount",
            "round_wins",
            "roundWins",
        )

        player1_score = _to_int(
            _first_value(
                player1,
                score_keys,
                0,
            ),
            0,
        )

        player2_score = _to_int(
            _first_value(
                player2,
                score_keys,
                0,
            ),
            0,
        )

        if player1_score != player2_score:
            winner_side = (
                1
                if player1_score > player2_score
                else 2
            )

            return (
                winner_side == target_side,
                character_id,
            )

        return None, character_id

    @classmethod
    def _parse_rank_replay_list(
        cls,
        replay_list: list,
        short_id: str,
    ) -> dict:
        """
        对 rank.json 当前页面的 replay_list 进行统计。

        注意：这是当前页面近期排位数据，
        不是玩家生涯累计排位数据。
        """
        result = {
            "wins": 0,
            "losses": 0,
            "matches": 0,
            "unknown": 0,
            "characters": {},
        }

        if not isinstance(replay_list, list):
            return result

        seen_replay_ids = set()

        for replay in replay_list:
            if not isinstance(replay, dict):
                continue

            replay_id = str(
                _first_value(
                    replay,
                    (
                        "replay_id",
                        "replayId",
                        "battle_id",
                        "battleId",
                    ),
                    "",
                )
            )

            # 防止接口中出现重复 Replay。
            if replay_id:
                if replay_id in seen_replay_ids:
                    continue

                seen_replay_ids.add(replay_id)

            won, character_id = cls._get_replay_result(
                replay,
                short_id,
            )

            if won is None:
                result["unknown"] += 1
                continue

            result["matches"] += 1

            if won:
                result["wins"] += 1
            else:
                result["losses"] += 1

            if character_id > 0:
                item = result["characters"].setdefault(
                    character_id,
                    {
                        "character_id": character_id,
                        "wins": 0,
                        "losses": 0,
                        "matches": 0,
                    },
                )

                item["matches"] += 1

                if won:
                    item["wins"] += 1
                else:
                    item["losses"] += 1

        return result

    @staticmethod
    def _rank_display_name(
        league_info: dict,
    ) -> str:
        if not isinstance(league_info, dict):
            return "未定级"

        rank = _get_rank_number(league_info)

        if rank in RANK_NAMES:
            return RANK_NAMES[rank]

        rank_info = league_info.get(
            "league_rank_info",
            {}
        )

        if isinstance(rank_info, dict):
            raw_name = str(
                rank_info.get("league_rank_name", "")
            ).strip()

            if raw_name:
                return raw_name

        if rank >= 36:
            return "大师"

        return "未定级"

    def query_rank_by_short_id(
        self,
        short_id: str,
    ) -> str:
        """
        查询玩家当前展示角色的段位，
        并统计 rank battlelog 当前页的近期排位胜率。
        """
        page = self.get_rank_battlelog_data(
            short_id
        )

        page_props = page.get("pageProps", {})

        if not isinstance(page_props, dict):
            return (
                f"未找到玩家排位数据 "
                f"(short_id: {short_id})"
            )

        fighter_banner = page_props.get(
            "fighter_banner_info",
            {}
        )

        if not isinstance(fighter_banner, dict):
            fighter_banner = {}

        personal = fighter_banner.get(
            "personal_info",
            {}
        )

        if not isinstance(personal, dict):
            personal = {}

        fighter_name = str(
            personal.get("fighter_id", "")
        ).strip()

        player_short_id = str(
            personal.get("short_id", short_id)
        )

        platform = str(
            personal.get("platform_name", "")
        ).strip()

        character_id = _to_int(
            fighter_banner.get(
                "favorite_character_id"
            ),
            0,
        )

        character_name = str(
            fighter_banner.get(
                "favorite_character_name",
                "",
            )
        ).strip()

        if not character_name:
            character_name = self._character_name(
                character_id
            )

        league_info = fighter_banner.get(
            "favorite_character_league_info",
            {},
        )

        if not isinstance(league_info, dict):
            league_info = {}

        rank_number = _get_rank_number(
            league_info
        )

        rank_name = self._rank_display_name(
            league_info
        )

        lp = _get_lp(league_info)

        mr = _to_int(
            league_info.get("master_rating"),
            0,
        )

        mr_ranking = _to_int(
            league_info.get(
                "master_rating_ranking"
            ),
            0,
        )

        replay_list = page_props.get(
            "replay_list",
            [],
        )

        rank_stats = self._parse_rank_replay_list(
            replay_list,
            player_short_id,
        )

        wins = rank_stats["wins"]
        losses = rank_stats["losses"]
        matches = rank_stats["matches"]
        unknown = rank_stats["unknown"]

        lines = [
            f"CFN: {fighter_name or '未知玩家'}",
            (
                f"Short ID: {player_short_id}"
                + (
                    f" | 平台: {platform}"
                    if platform
                    else ""
                )
            ),
        ]

        rank_parts = []

        if character_name:
            rank_parts.append(
                f"排位角色: {character_name}"
            )

        rank_parts.append(
            f"段位: {rank_name}"
        )

        if mr > 0:
            rank_parts.append(f"MR: {mr}")

            if mr_ranking > 0:
                rank_parts.append(
                    f"MR排名: #{mr_ranking}"
                )
        elif lp >= 0:
            rank_parts.append(f"LP: {lp}")

        lines.append(" | ".join(rank_parts))

        if matches > 0:
            win_rate = wins / matches * 100

            lines.append(
                f"近期排位: {win_rate:.1f}% "
                f"({wins}胜/{losses}负/{matches}场)"
            )
        else:
            lines.append(
                "近期排位: 暂无可解析的对战记录"
            )

        if unknown > 0:
            lines.append(
                f"另有 {unknown} 条记录无法识别胜负"
            )

        # 按角色输出当前页排位记录。
        character_stats = list(
            rank_stats["characters"].values()
        )

        character_stats.sort(
            key=lambda item: (
                item["matches"],
                item["wins"],
            ),
            reverse=True,
        )

        if character_stats:
            lines.append("近期角色战绩:")

            for item in character_stats:
                cid = item["character_id"]
                char_matches = item["matches"]
                char_wins = item["wins"]
                char_losses = item["losses"]

                char_rate = (
                    char_wins / char_matches * 100
                    if char_matches > 0
                    else 0
                )

                lines.append(
                    f"- {self._character_name(cid)}: "
                    f"{char_rate:.1f}% "
                    f"({char_wins}胜/"
                    f"{char_losses}负/"
                    f"{char_matches}场)"
                )

        current_page = _to_int(
            page_props.get("current_page"),
            1,
        )

        lines.append(
            f"数据范围: 排位记录第 {current_page} 页"
        )

        return "\n".join(lines)

    def _fmt_rank(self, p: PlayerProfile) -> str:
        rank_parts = []

        if p.league_rank >= 36:
            rank_parts.append("最高段位: 大师")

            if p.mr > 0:
                rank_parts.append(
                    f"MR: {p.mr}"
                )

            if p.mr_ranking > 0:
                rank_parts.append(
                    f"MR排名: #{p.mr_ranking}"
                )

        elif p.league_rank in RANK_NAMES:
            rank_parts.append(
                f"最高段位: "
                f"{RANK_NAMES[p.league_rank]}"
            )

            if p.lp > 0:
                rank_parts.append(
                    f"LP: {p.lp}"
                )

        else:
            rank_parts.append(
                "最高段位: 未获取到全角色段位数据"
            )

        if p.highest_character_name:
            rank_parts.append(
                f"最高段位角色: "
                f"{p.highest_character_name}"
            )

        profile_parts = []

        if p.favorite_character_name:
            profile_parts.append(
                f"资料页角色: "
                f"{p.favorite_character_name}"
            )
        else:
            profile_parts.append(
                "资料页角色: 暂无数据"
            )

        if p.last_play_at:
            import datetime

            timestamp = float(p.last_play_at)

            if timestamp > 10_000_000_000:
                timestamp /= 1000

            dt = datetime.datetime.fromtimestamp(
                timestamp
            )

            profile_parts.append(
                "最近游玩: "
                + dt.strftime("%Y-%m-%d %H:%M")
            )
        else:
            profile_parts.append(
                "最近游玩: 暂无数据"
            )

        return (
            " | ".join(rank_parts)
            + "\n"
            + " | ".join(profile_parts)
        )

    @staticmethod
    def _fmt_winrate(p: PlayerProfile) -> str:
        lines = []

        if p.total_matches > 0:
            total_rate = (
                p.total_wins
                / p.total_matches
                * 100
            )

            lines.append(
                f"总胜率: {total_rate:.1f}% "
                f"({p.total_wins}胜/"
                f"{p.total_matches}场)"
            )
        else:
            lines.append(
                "总胜率: 暂无数据"
            )

        if p.ranked_matches > 0:
            ranked_rate = (
                p.ranked_wins
                / p.ranked_matches
                * 100
            )

            lines.append(
                f"排位胜率: {ranked_rate:.1f}% "
                f"({p.ranked_wins}胜/"
                f"{p.ranked_matches}场)"
            )
        else:
            lines.append(
                "排位胜率: 暂无数据"
            )

        return "\n".join(lines)

    def _fmt_all_characters(
        self,
        p: PlayerProfile,
    ) -> str:
        rank_map = {
            _to_int(item.get("character_id"), 0): item
            for item in p.character_ranks
        }

        usage_map = {
            _to_int(item.get("character_id"), 0): item
            for item in p.character_usage
        }

        ids = sorted(
            set(rank_map) | set(usage_map)
        )

        if not ids:
            return "角色数据: 暂无数据"

        lines = ["角色数据:"]

        for character_id in ids:
            name = self._character_name(
                character_id
            )
            rank_item = rank_map.get(character_id)
            usage_item = usage_map.get(character_id)

            rank_text = "未定级"

            if rank_item:
                rank = _to_int(
                    rank_item.get("rank"),
                    0,
                )
                lp = _to_int(
                    rank_item.get("lp"),
                    0,
                )

                if rank in RANK_NAMES:
                    rank_text = RANK_NAMES[rank]

                    if lp > 0:
                        rank_text += f" | LP: {lp}"
                elif rank >= 36:
                    rank_text = "大师"

            win_text = "暂无战绩"

            if usage_item:
                wins = _to_int(
                    usage_item.get("win_count"),
                    0,
                )
                matches = _to_int(
                    usage_item.get("battle_count"),
                    0,
                )

                if matches > 0 and 0 <= wins <= matches:
                    rate = wins / matches * 100
                    win_text = (
                        f"{rate:.1f}% "
                        f"({wins}胜/{matches}场)"
                    )

            lines.append(
                f"{name}: {rank_text} | "
                f"胜率: {win_text}"
            )

        return "\n".join(lines)

    def _fmt_character(
        self,
        p: PlayerProfile,
        char_name: str,
    ) -> str:
        query_name = char_name.strip()

        if (
            query_name == "全部"
            or query_name.lower() == "all"
        ):
            return self._fmt_all_characters(p)

        character_id = self._resolve_character_id(
            query_name
        )

        if character_id is None:
            return f"无法识别角色：{query_name}"

        display_name = self._character_name(
            character_id
        )

        rank_item = next(
            (
                item
                for item in p.character_ranks
                if _to_int(
                    item.get("character_id"),
                    0,
                ) == character_id
            ),
            None,
        )

        usage_item = next(
            (
                item
                for item in p.character_usage
                if _to_int(
                    item.get("character_id"),
                    0,
                ) == character_id
            ),
            None,
        )

        lines = [f"角色 [{display_name}]"]

        if rank_item:
            rank = _to_int(
                rank_item.get("rank"),
                0,
            )
            lp = _to_int(
                rank_item.get("lp"),
                0,
            )
            mr = _to_int(
                rank_item.get("mr"),
                0,
            )
            mr_ranking = _to_int(
                rank_item.get("mr_ranking"),
                0,
            )

            rank_parts = []

            if rank >= 36:
                rank_parts.append(
                    "角色段位: 大师"
                )

                if mr > 0:
                    rank_parts.append(
                        f"MR: {mr}"
                    )

                if mr_ranking > 0:
                    rank_parts.append(
                        f"MR排名: #{mr_ranking}"
                    )

            elif rank in RANK_NAMES:
                rank_parts.append(
                    f"角色段位: {RANK_NAMES[rank]}"
                )
                if lp > 0:
                    rank_parts.append(
                        f"LP: {lp}"
                    )
            else:
                rank_parts.append(
                    "角色段位: 未定级"
                )

            lines.append(" | ".join(rank_parts))
        else:
            lines.append("角色段位: 暂无数据")

        if usage_item:
            wins = _to_int(
                usage_item.get("win_count"),
                0,
            )
            matches = _to_int(
                usage_item.get("battle_count"),
                0,
            )

            if matches > 0 and 0 <= wins <= matches:
                rate = wins / matches * 100
                lines.append(
                    f"角色总胜率: {rate:.1f}% "
                    f"({wins}胜/{matches}场)"
                )
            else:
                lines.append("角色总胜率: 暂无数据")
        else:
            lines.append("角色总胜率: 暂无数据")

        ranked_item = next(
            (
                item
                for item in p.character_ranked_usage
                if _to_int(
                    item.get("character_id"),
                    0,
                ) == character_id
            ),
            None,
        )

        if ranked_item:
            ranked_wins = _to_int(
                ranked_item.get("win_count"),
                0,
            )
            ranked_matches = _to_int(
                ranked_item.get("battle_count"),
                0,
            )

            if ranked_matches > 0 and 0 <= ranked_wins <= ranked_matches:
                ranked_rate = ranked_wins / ranked_matches * 100
                lines.append(
                    f"角色排位胜率: {ranked_rate:.1f}% "
                    f"({ranked_wins}胜/{ranked_matches}场)"
                )
            else:
                lines.append("角色排位胜率: 暂无数据")
        else:
            lines.append("角色排位胜率: 暂无数据")

        return "\n".join(lines)

    @staticmethod
    def _fmt_history(p: PlayerProfile) -> str:
        return f"近期战绩: 共{p.total_matches}场 | 连胜{p.win_streak}场"

    @staticmethod
    def _resolve_character_id(name: str) -> Optional[int]:
        name_lower = name.strip().lower()
        for cid, tool_name in CHARACTER_ID_MAP.items():
            if tool_name.lower() == name_lower:
                return cid
            cn = CHARACTER_NAMES.get(tool_name, "")
            if cn.lower() == name_lower:
                return cid
        return None

    @staticmethod
    def list_characters() -> str:
        lines = ["可用角色名称:"]
        for cid, tool_name in sorted(CHARACTER_ID_MAP.items()):
            cn = CHARACTER_NAMES.get(tool_name, tool_name)
            lines.append(f"  {cn} ({tool_name})")
        return "\n".join(lines)



