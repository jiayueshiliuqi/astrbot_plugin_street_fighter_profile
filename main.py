import os
import sys
import re

ROOT = os.path.dirname(__file__)
sys.path.append(ROOT)

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter

from sf6_client import SF6Client, CHARACTER_ID_MAP, CHARACTER_NAMES

import asyncio
import json


class Main(star.Star):
    GLOBAL_PERSONA_KEY = "__global__"
    def __init__(self, context: star.Context):
        super().__init__(context)
        self.context = context
        self._client = None
        self._search_states = {}

        self._persona_path = os.path.join(ROOT, "personas.json")
        self._persona_lock = asyncio.Lock()
        self._persona_data = self._load_personas()

        print("[my_qq_tool] main.py loaded")

    def _load_personas(self) -> dict:
        default = {"personas": {}, "selected": {}}

        if not os.path.exists(self._persona_path):
            return default

        try:
            with open(self._persona_path, "r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, dict):
                return default

            data.setdefault("personas", {})
            data.setdefault("selected", {})
            return data
        except Exception as exc:
            print(f"[my_qq_tool] 读取人格配置失败: {exc}")
            return default

    def _save_personas(self):
        temp_path = self._persona_path + ".tmp"

        with open(temp_path, "w", encoding="utf-8") as file:
            json.dump(
                self._persona_data,
                file,
                ensure_ascii=False,
                indent=2,
            )

        os.replace(temp_path, self._persona_path)

    @staticmethod
    def _conversation_key(event: AstrMessageEvent) -> str:
        origin = getattr(event, "unified_msg_origin", "")
        if origin:
            return str(origin)

        # 兼容部分旧版 AstrBot，但群聊应优先使用 unified_msg_origin。
        return f"sender:{event.get_sender_id()}"

    @staticmethod
    def _command_content(
        event: AstrMessageEvent,
        command: str,
    ) -> str:
        message = (event.message_str or "").strip()
        return re.sub(
            rf"^/?{re.escape(command)}(?:\s+|$)",
            "",
            message,
        ).strip()

    def _get_client(self) -> SF6Client:
        if self._client is None:
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            cookie_path = os.path.join(plugin_dir, "cookie.txt")

            self._client = SF6Client(
                cookie_str=cookie_path,
            )

        return self._client

    @staticmethod
    def _sender_key(event: AstrMessageEvent) -> str:
        return event.get_sender_id()

    @staticmethod
    def _character_name(character_id: int) -> str:
        if character_id <= 0:
            return ""
        tool_name = CHARACTER_ID_MAP.get(character_id, "")
        if not tool_name:
            return ""
        return CHARACTER_NAMES.get(tool_name, tool_name)

    @staticmethod
    def _format_time(timestamp: int) -> str:
        if not timestamp:
            return ""
        import datetime
        t = float(timestamp)
        if t > 10_000_000_000:
            t /= 1000
        dt = datetime.datetime.fromtimestamp(t)
        return dt.strftime("%m-%d %H:%M")

    @staticmethod
    def _format_search_result(item: dict, index: int) -> str:
        platform = item.get("platform_name", "")
        cname = Main._character_name(
            item.get("favorite_character_id", 0)
        ) or item.get("favorite_character_name", "")
        lp = item.get("league_point", 0)
        last = Main._format_time(item.get("last_play_at", 0))

        parts = [
            f"{index}. {item['fighter_id']}",
            f"ID:{item['short_id']}",
        ]
        if platform:
            parts.append(platform)
        if cname:
            parts.append(f"角色:{cname}")
        if lp:
            parts.append(f"LP:{lp}")
        if last:
            parts.append(f"最近:{last}")

        return " | ".join(parts)

    @filter.command("查询")
    async def query(self, event: AstrMessageEvent):
        message = (event.message_str or "").strip()

        content = re.sub(
            r"^/?查询(?:\s+|$)",
            "",
            message,
        ).strip()

        if not content:
            event.stop_event()

            yield event.plain_result(
                "用法：\n"
                "/查询 <short_id>           -> 查询段位和胜率\n"
                "/查询 <short_id> 角色 <名> -> 查询指定角色战绩\n"
                "/查询 <CFN名称>            -> 搜索玩家\n"
                "例如：/查询 111111111\n"
                "例如：/查询 测试测试"
            )
            return

        parts = content.split()
        first = parts[0]
        rest = parts[1:]

        # 序号选择：/查询 1~5
        if first.isdigit() and 1 <= int(first) <= 5:
            sender_key = self._sender_key(event)
            state = self._search_states.get(sender_key)

            if state:
                idx = int(first) - 1
                if 0 <= idx < len(state["results"]):
                    short_id = state["results"][idx]["short_id"]
                    del self._search_states[sender_key]

                    event.stop_event()

                    try:
                        result = await asyncio.to_thread(
                            self._get_client().query_by_short_id,
                            short_id,
                        )
                        yield event.plain_result(result)
                    except Exception as exc:
                        yield event.plain_result(
                            f"查询失败: {exc}"
                        )
                    return
                else:
                    event.stop_event()
                    yield event.plain_result(
                        f"序号 {first} 超出范围，"
                        f"当前页只有 {len(state['results'])} 条结果"
                    )
                    return
            # no active search state, fall through to short_id query

        # short_id 查询
        if first.isdigit():
            short_id = first
            params = {}

            if rest:
                if rest[0] != "角色":
                    event.stop_event()

                    yield event.plain_result(
                        "目前只支持角色查询：\n"
                        "/查询 <short_id> 角色 <角色名>\n"
                        "/查询 <short_id> 角色 全部"
                    )
                    return

                if len(rest) == 1:
                    params["character"] = "all"
                elif len(rest) == 2:
                    params["character"] = rest[1]
                else:
                    event.stop_event()

                    yield event.plain_result(
                        "用法：/查询 <short_id> 角色 <角色名>\n"
                        "例如：/查询 2567968452 角色 杰米"
                    )
                    return
            else:
                params = {
                    "rank": True,
                    "winrate": True,
                }

            event.stop_event()

            try:
                result = await asyncio.to_thread(
                    self._get_client().query_by_short_id,
                    short_id,
                    **params,
                )

                yield event.plain_result(result)

            except Exception as exc:
                yield event.plain_result(
                    f"查询失败: {exc}"
                )
            return

        # 名称搜索
        name = content

        event.stop_event()

        sender_key = self._sender_key(event)

        try:
            search_result = await asyncio.to_thread(
                self._get_client().search_by_name,
                name,
                page=1,
            )

            results = search_result.get("results", [])

            if not results:
                error_msg = search_result.get("error", "")
                if error_msg:
                    yield event.plain_result(error_msg)
                else:
                    yield event.plain_result(
                        f"未找到 CFN 名称为 \"{name}\" 的玩家"
                    )
                self._search_states.pop(sender_key, None)
                return

            self._search_states[sender_key] = {
                "name": name,
                "page": 1,
                "has_more": search_result.get("has_more", False),
                "results": results,
            }

            lines = [
                f"搜索 \"{name}\" 找到结果（第1页）:",
            ]

            for i, item in enumerate(results):
                lines.append(
                    self._format_search_result(item, i + 1)
                )

            if search_result.get("has_more"):
                lines.append("输入 /下一页 查看更多")

            lines.append("输入 /查询 序号 查看详情")

            yield event.plain_result("\n".join(lines))

        except Exception as exc:
            yield event.plain_result(
                f"搜索失败: {exc}"
            )

    @filter.command("下一页")
    async def next_page(self, event: AstrMessageEvent):
        event.stop_event()

        sender_key = self._sender_key(event)
        state = self._search_states.get(sender_key)

        if not state:
            yield event.plain_result(
                "没有活跃的搜索结果，请先使用 /查询 <名称> 搜索"
            )
            return

        if not state.get("has_more"):
            yield event.plain_result("已是最后一页")
            return

        next_page = state["page"] + 1

        try:
            search_result = await asyncio.to_thread(
                self._get_client().search_by_name,
                state["name"],
                page=next_page,
            )

            results = search_result.get("results", [])

            if not results:
                state["has_more"] = False
                yield event.plain_result("已是最后一页")
                return

            state["page"] = next_page
            state["has_more"] = search_result.get("has_more", False)
            state["results"] = results

            lines = [
                f"搜索 \"{state['name']}\" 结果（第{next_page}页）:",
            ]

            for i, item in enumerate(results):
                lines.append(
                    self._format_search_result(item, i + 1)
                )

            if state["has_more"]:
                lines.append("输入 /下一页 查看更多，/上一页 返回")

            lines.append("输入 /查询 序号 查看详情")

            yield event.plain_result("\n".join(lines))

        except Exception as exc:
            yield event.plain_result(
                f"翻页失败: {exc}"
            )

    @filter.command("上一页")
    async def prev_page(self, event: AstrMessageEvent):
        event.stop_event()

        sender_key = self._sender_key(event)
        state = self._search_states.get(sender_key)

        if not state:
            yield event.plain_result(
                "没有活跃的搜索结果，请先使用 /查询 <名称> 搜索"
            )
            return

        if state["page"] <= 1:
            yield event.plain_result("已是第一页")
            return

        prev_page = state["page"] - 1

        try:
            search_result = await asyncio.to_thread(
                self._get_client().search_by_name,
                state["name"],
                page=prev_page,
            )

            results = search_result.get("results", [])

            if not results:
                yield event.plain_result("已是第一页")
                return

            state["page"] = prev_page
            state["has_more"] = search_result.get("has_more", False)
            state["results"] = results

            lines = [
                f"搜索 \"{state['name']}\" 结果（第{prev_page}页）:",
            ]

            for i, item in enumerate(results):
                lines.append(
                    self._format_search_result(item, i + 1)
                )

            if state["has_more"]:
                lines.append("输入 /下一页 查看更多")

            if prev_page > 1:
                lines.append("输入 /上一页 返回")

            lines.append("输入 /查询 序号 查看详情")

            yield event.plain_result("\n".join(lines))

        except Exception as exc:
            yield event.plain_result(
                f"翻页失败: {exc}"
            )

    @filter.command("人格添加")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def persona_add(self, event: AstrMessageEvent):
        event.stop_event()
        content = self._command_content(event, "人格添加")

        if not content:
            yield event.plain_result(
                "用法：/人格添加 <名称> <人格提示词>\n"
                "例如：/人格添加 隆 你是街头霸王中的隆，说话沉稳简洁。"
            )
            return

        parts = content.split(maxsplit=1)
        if len(parts) != 2:
            yield event.plain_result("必须同时提供人格名称和提示词")
            return

        name, prompt = parts
        if len(name) > 32:
            yield event.plain_result("人格名称不能超过 32 个字符")
            return
        if len(prompt) > 8000:
            yield event.plain_result("人格提示词不能超过 8000 个字符")
            return

        async with self._persona_lock:
            existed = name in self._persona_data["personas"]
            self._persona_data["personas"][name] = prompt
            self._save_personas()

        action = "覆盖" if existed else "添加"
        yield event.plain_result(f"已{action}人格：{name}")

    @filter.command("人格删除")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def persona_delete(self, event: AstrMessageEvent):
        event.stop_event()
        name = self._command_content(event, "人格删除")

        if not name:
            yield event.plain_result(
                "用法：/人格删除 <名称>\n"
                "例如：/人格删除 隆"
            )
            return

        async with self._persona_lock:
            personas = self._persona_data["personas"]
            selected = self._persona_data["selected"]

            if name not in personas:
                yield event.plain_result(f"未找到人格：{name}")
                return

            del personas[name]

            was_global = (
                selected.get(self.GLOBAL_PERSONA_KEY) == name
            )

            if was_global:
                selected.pop(self.GLOBAL_PERSONA_KEY, None)

            # 删除旧版本遗留的按会话人格选择。
            stale_keys = [
                key
                for key, selected_name in selected.items()
                if selected_name == name
            ]

            for key in stale_keys:
                del selected[key]

            self._save_personas()

        if was_global:
            yield event.plain_result(
                f"已删除人格：{name}\n"
                "该人格原为全局人格，现已恢复 AstrBot 默认人格"
            )
        else:
            yield event.plain_result(f"已删除人格：{name}")

    @filter.command("人格查询")
    async def persona_query(self, event: AstrMessageEvent):
        event.stop_event()

        name = self._command_content(event, "人格查询")
        personas = self._persona_data["personas"]

        if name:
            prompt = personas.get(name)

            if prompt is None:
                yield event.plain_result(f"未找到人格：{name}")
                return

            yield event.plain_result(
                f"人格：{name}\n"
                f"设定：{prompt}"
            )
            return

        selected = self._persona_data["selected"].get(
            self.GLOBAL_PERSONA_KEY
        )

        if not personas:
            yield event.plain_result("当前没有可用人格")
            return

        lines = [
            f"当前全局人格：{selected or '默认'}",
            "可用人格：",
        ]

        for persona_name in sorted(personas):
            mark = "（当前）" if persona_name == selected else ""
            lines.append(f"- {persona_name}{mark}")

        lines.append("管理员可使用 /人格设置 <名称> 全局切换")
        yield event.plain_result("\n".join(lines))

    @filter.command("人格当前")
    async def persona_current(self, event: AstrMessageEvent):
        event.stop_event()

        name = self._persona_data["selected"].get(
            self.GLOBAL_PERSONA_KEY
        )

        if not name:
            yield event.plain_result(
                "当前未启用全局插件人格，所有会话正在使用 "
                "AstrBot 默认人格。"
            )
            return

        prompt = self._persona_data["personas"].get(name)

        if not prompt:
            async with self._persona_lock:
                self._persona_data["selected"].pop(
                    self.GLOBAL_PERSONA_KEY,
                    None,
                )
                self._save_personas()

            yield event.plain_result(
                f"全局人格“{name}”已不存在，"
                "已自动恢复 AstrBot 默认人格。"
            )
            return

        effective_prompt = (
            f"[全局人格：{name}]\n"
            f"{prompt}"
        )

        yield event.plain_result(
            f"当前全局人格：{name}\n"
            "当前注入给 LLM 的提示词：\n"
            f"{effective_prompt}"
        )

    @filter.command("人格设置")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def persona_set(self, event: AstrMessageEvent):
        event.stop_event()
        name = self._command_content(event, "人格设置")

        if not name:
            yield event.plain_result(
                "用法：/人格设置 <名称>\n"
                "恢复默认：/人格设置 关闭"
            )
            return

        async with self._persona_lock:
            selected = self._persona_data["selected"]

            if name in ("关闭", "默认", "取消"):
                selected.clear()
                self._save_personas()

                yield event.plain_result(
                    "已关闭全局插件人格，所有会话将使用 "
                    "AstrBot 默认人格"
                )
                return

            if name not in self._persona_data["personas"]:
                yield event.plain_result(
                    f"未找到人格：{name}\n"
                    "使用 /人格查询 查看可用人格"
                )
                return

            # 移除旧版本按群聊或私聊保存的选择。
            selected.clear()
            selected[self.GLOBAL_PERSONA_KEY] = name
            self._save_personas()

        yield event.plain_result(
            f"全局人格已切换为：{name}\n"
            "所有群聊和私聊的后续消息都会使用该人格"
        )

    @filter.command("记忆清空")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def clear_memory(self, event: AstrMessageEvent):
        event.stop_event()

        origin = getattr(event, "unified_msg_origin", "")
        if not origin:
            yield event.plain_result(
                "清空失败：无法识别当前 QQ 会话"
            )
            return

        try:
            manager = self.context.conversation_manager

            conversation_id = (
                await manager.get_curr_conversation_id(origin)
            )

            if not conversation_id:
                yield event.plain_result(
                    "当前会话还没有聊天记忆，无需清空"
                )
                return

            await manager.update_conversation(
                origin,
                conversation_id,
                history=[],
            )

            yield event.plain_result(
                "已清空当前会话的历史聊天记忆。\n"
                "当前选择的人格保持不变，下一条消息将使用全新上下文。"
            )

        except Exception as exc:
            print(f"[my_qq_tool] 清空聊天记忆失败: {exc}")

            yield event.plain_result(
                f"清空聊天记忆失败：{exc}"
            )

    @filter.on_llm_request()
    async def apply_persona(self, event: AstrMessageEvent, request):
        name = self._persona_data["selected"].get(
            self.GLOBAL_PERSONA_KEY
        )

        if not name:
            print(
                "[PERSONA DEBUG] 未启用全局插件人格，"
                f"system_prompt={request.system_prompt!r}"
            )
            return

        prompt = self._persona_data["personas"].get(name)

        if not prompt:
            print(
                "[PERSONA DEBUG] 全局人格不存在："
                f"{name!r}"
            )
            return

        request.system_prompt = (
            f"[全局人格：{name}]\n"
            f"{prompt}"
        )

    @filter.command("help")
    async def help_cmd(self, event: AstrMessageEvent):
        event.stop_event()

        yield event.plain_result(
            "街霸6查询工具\n"
            "/查询 <short_id>           -> 查询段位和胜率\n"
            "/查询 <short_id> 角色 杰米 -> 查询指定角色战绩\n"
            "/查询 <short_id> 角色 全部 -> 查询各角色战绩\n"
            "/查询 <CFN名称>            -> 搜索玩家\n"
            "/下一页 /上一页            -> 翻页搜索结果\n"
            "/查询 1~5                  -> 选择搜索结果查看详情\n"
            "/help                     -> 显示帮助"
        )

    @filter.command("help_p")
    async def help_personas_cmd(self, event: AstrMessageEvent):
        event.stop_event()

        yield event.plain_result(
            "人格管理\n"
            "/人格添加 <名称> <提示词> -> 添加或覆盖人格（管理员）\n"
            "/人格删除 <名称>          -> 删除人格（管理员）\n"
            "/人格查询                 -> 查看人格列表\n"
            "/人格查询 <名称>          -> 查看指定人格内容\n"
            "/人格当前                 -> 查看全局人格及提示词\n"
            "/人格设置 <名称>          -> 设置全局人格（管理员）\n"
            "/人格设置 关闭            -> 关闭全局人格（管理员）\n"
            "/记忆清空                 -> 清空当前会话聊天记录"
        )