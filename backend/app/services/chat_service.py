import re
import uuid
from collections.abc import Callable
from typing import Any

from app.agent_runtime import BoundToolExecutor, WebToolContext, build_web_tool_registry
from app.agent_runtime.tools import MemoryUpsertArgs, PortfolioUpsertArgs
from app.models import Message, User
from app.repositories.chat_repository import ChatRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.memory_repository import MemoryRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.portfolio_repository import PortfolioRepository
from app.repositories.research_repository import ResearchRepository
from app.repositories.tool_action_repository import ToolActionRepository
from app.services.memory_service import MemoryService
from app.services.research_service import ResearchService
from src.agents.chat import AgentRunResult, LangGraphChatAgent, build_chat_system_prompt


class ChatService:
    """Persisted LangGraph Agent with authenticated tools and durable confirmations."""

    def __init__(
        self,
        chat: ChatRepository,
        portfolio: PortfolioRepository,
        research: ResearchRepository,
        memory: MemoryRepository,
        knowledge: KnowledgeRepository,
        actions: ToolActionRepository,
        outbox: OutboxRepository,
    ):
        self.chat = chat
        self.portfolio = portfolio
        self.research = research
        self.memory = memory
        self.knowledge = knowledge
        self.actions = actions
        self.outbox = outbox

    async def respond(
        self,
        conversation_id: str,
        user: User,
        content: str,
        on_token: Callable[[str], None] | None = None,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> Message:
        pending_action = await self.actions.latest_pending(conversation_id, user.id)
        confirmation_intent = self._confirmation_intent(content)
        if pending_action is not None and confirmation_intent is not None:
            await self.chat.add_message(conversation_id, "user", content)
            if confirmation_intent == "confirm":
                return await self.confirm(
                    conversation_id, pending_action.message_id, user
                )
            return await self._cancel(
                conversation_id, pending_action.message_id, user
            )

        source_message_id = str(uuid.uuid4())
        history = await self.chat.recent_messages(conversation_id, limit=20)
        graph_messages = [
            {"role": item.role, "content": item.content}
            for item in history
            if item.role in {"user", "assistant"}
        ]
        graph_messages.append({"role": "user", "content": content})
        memory_context = await MemoryService(self.memory).context_for_user(user.id)
        context = WebToolContext(
            user_id=user.id,
            risk_profile=user.risk_profile,
            portfolio=self.portfolio,
            research=self.research,
            memory=self.memory,
            knowledge=self.knowledge,
            outbox=self.outbox,
        )
        executor = BoundToolExecutor(build_web_tool_registry(), context)
        agent = LangGraphChatAgent(
            executor,
            build_chat_system_prompt(memory_context),
        )
        result = (
            await agent.run(graph_messages, on_token=on_token, on_event=on_event)
            if on_token is not None
            else await agent.run(graph_messages)
        )
        if result.error == "llm request failed":
            result = await self._fallback(user, content)

        await self.chat.add_message(
            conversation_id,
            "user",
            content,
            message_id=source_message_id,
        )
        assistant_id = str(uuid.uuid4())
        tool_name, tool_payload = self._message_metadata(result, source_message_id)
        reply = await self.chat.add_message(
            conversation_id,
            "assistant",
            result.answer,
            tool_name,
            tool_payload,
            message_id=assistant_id,
        )
        if result.pending_action:
            await self.actions.create(
                user_id=user.id,
                conversation_id=conversation_id,
                message_id=assistant_id,
                source_message_id=source_message_id,
                tool_name=result.pending_action["tool_name"],
                arguments=result.pending_action["arguments"],
                status="pending",
            )
        return reply

    async def _cancel(
        self, conversation_id: str, message_id: str, user: User
    ) -> Message:
        action = await self.actions.cancel_pending(
            message_id, conversation_id, user.id
        )
        if action is None:
            raise ValueError("找不到待取消的操作")
        message = await self.chat.get_message(message_id, conversation_id)
        if message is not None:
            message.tool_payload = {
                **(message.tool_payload or {}),
                "status": "cancelled",
            }
            await self.chat.save(message)
        return await self.chat.add_message(
            conversation_id,
            "assistant",
            "已取消本次写入，数据没有发生变化。",
            action.tool_name,
            {"status": "cancelled"},
        )

    async def confirm(self, conversation_id: str, message_id: str, user: User) -> Message:
        action = await self.actions.claim_pending(message_id, conversation_id, user.id)
        if action is None:
            existing = await self.actions.get_for_message(message_id, conversation_id, user.id)
            if existing is None:
                raise ValueError("找不到待确认的操作")
            raise ValueError("该操作已经处理或正在执行")

        if action.tool_name == "portfolio_upsert":
            arguments = PortfolioUpsertArgs.model_validate(action.arguments)
            portfolio = await self.portfolio.get_default(user.id)
            position = await self.portfolio.upsert_position(
                portfolio=portfolio, **arguments.model_dump()
            )
            result = {"position_id": position.id, "stock_code": position.stock_code}
            reply_text = f"已保存 {position.stock_code} 的持仓记录。"
            display_name = "portfolio.upsert"
        elif action.tool_name == "memory_upsert":
            arguments = MemoryUpsertArgs.model_validate(action.arguments)
            memory = await self.memory.upsert(
                user_id=user.id,
                source_message_id=action.source_message_id,
                **arguments.model_dump(),
            )
            result = {"memory_id": memory.id, "memory_key": memory.memory_key}
            reply_text = f"已保存长期记忆：{memory.memory_key}。"
            display_name = "memory.upsert"
        else:
            raise ValueError("该操作不支持确认")

        await self.actions.complete(action, result)
        message = await self.chat.get_message(message_id, conversation_id)
        if message is not None:
            message.tool_payload = {
                **(message.tool_payload or {}),
                "status": "confirmed",
                "result": result,
            }
            await self.chat.save(message)
        return await self.chat.add_message(
            conversation_id,
            "assistant",
            reply_text,
            display_name,
            {"status": "completed", **result},
        )

    async def _fallback(self, user: User, content: str) -> AgentRunResult:
        code = self._stock_code(content)
        position = self._parse_position(content, code)
        if position:
            return AgentRunResult(
                answer=(
                    f"我将记录 {position['stock_code']}：{position['quantity']} 股，"
                    f"平均成本 {position['average_cost']} 元。请确认后写入持仓。"
                ),
                pending_action={"tool_name": "portfolio_upsert", "arguments": position},
            )
        if self._asks_positions(content):
            positions = await self.portfolio.list_positions(user.id)
            if not positions:
                return AgentRunResult(answer="你还没有记录持仓。你可以说：‘记录 600519 100 股，成本 1450 元’。")
            lines = [
                f"{item.stock_code} {item.stock_name or ''}：{item.quantity} 股，成本 {item.average_cost}"
                for item in positions
            ]
            return AgentRunResult(
                answer="当前持仓：\n" + "\n".join(lines),
                tool_results=[{"name": "portfolio_list", "result": {"count": len(positions)}}],
            )
        if self._asks_research(content):
            if code is None:
                return AgentRunResult(answer="请告诉我 6 位股票代码，例如：‘深度研究 600519，偏保守’。")
            depth = "full" if "完整" in content or "深度" in content else "quick" if "快速" in content else "standard"
            risk = "conservative" if "保守" in content else "aggressive" if "进取" in content else user.risk_profile
            job = await ResearchService(self.research, self.outbox).submit(
                user_id=user.id,
                stock_code=code,
                depth=depth,
                risk_profile=risk,
            )
            payload = {"job_id": job.id, "stock_code": code, "status": "queued"}
            return AgentRunResult(
                answer=f"已为 {code} 创建{self._depth_label(depth)}研究任务。",
                tool_results=[{"name": "research_submit", "result": payload}],
            )
        if "报告" in content and code:
            jobs = await self.research.list_jobs(user_id=user.id)
            job = next(
                (item for item in jobs if item.stock_code == code and item.status == "completed"),
                None,
            )
            if job:
                return AgentRunResult(
                    answer=f"已找到 {code} 的已完成报告，点击任务列表中的“查看报告”即可打开。",
                    tool_results=[{"name": "research_report", "result": {"job_id": job.id}}],
                )
        return AgentRunResult(
            answer="当前 LLM 服务不可用。你仍可以查询持仓、准备持仓录入或发起股票研究。"
        )

    @staticmethod
    def _message_metadata(
        result: AgentRunResult, source_message_id: str
    ) -> tuple[str | None, dict | None]:
        if result.pending_action:
            name = result.pending_action["tool_name"]
            display_name = {
                "portfolio_upsert": "portfolio.upsert",
                "memory_upsert": "memory.upsert",
            }.get(name, name)
            return display_name, {
                "status": "pending_confirmation",
                "action": name,
                "arguments": result.pending_action["arguments"],
                "source_message_id": source_message_id,
            }
        if not result.tool_results:
            return None, None
        last = result.tool_results[-1]
        payload = {
            "status": "completed"
            if all(item.get("result", {}).get("ok", True) for item in result.tool_results)
            else "failed",
            "result": dict(last.get("result") or {}),
            "tool_results": result.tool_results,
        }
        return str(last.get("name") or "agent.tool"), payload

    @staticmethod
    def _stock_code(content: str) -> str | None:
        match = re.search(r"(?<!\d)(\d{6})(?!\d)", content)
        return match.group(1) if match else None

    @staticmethod
    def _asks_positions(content: str) -> bool:
        return any(token in content for token in ("持仓", "仓位", "我持有", "我的股票")) and not any(
            token in content for token in ("记录", "新增", "添加", "买入")
        )

    @staticmethod
    def _asks_research(content: str) -> bool:
        return any(token in content for token in ("研究", "分析", "研报", "看看", "深度"))

    @staticmethod
    def _parse_position(content: str, code: str | None) -> dict | None:
        if code is None or not any(token in content for token in ("记录", "新增", "添加", "买入", "持有")):
            return None
        quantity = re.search(r"(\d+)\s*(?:股|份)", content)
        cost = re.search(r"(?:成本|均价|价格)\s*(\d+(?:\.\d+)?)", content)
        if quantity is None or cost is None:
            return None
        return {
            "stock_code": code,
            "stock_name": "",
            "quantity": int(quantity.group(1)),
            "average_cost": float(cost.group(1)),
        }

    @staticmethod
    def _depth_label(depth: str) -> str:
        return {"quick": "快速", "standard": "标准", "full": "完整"}[depth]

    @staticmethod
    def _confirmation_intent(content: str) -> str | None:
        """Recognize short replies only; longer requests must still reach LangGraph."""
        normalized = re.sub(r"[\s，。！!？?、]", "", content).lower()
        if len(normalized) > 32:
            return None
        if any(
            token in normalized
            for token in ("取消", "不确认", "不要", "算了", "停止")
        ):
            return "cancel"
        if normalized in {
            "确认",
            "确认写入",
            "确认保存",
            "是",
            "是的",
            "好",
            "好的",
            "可以",
            "没问题",
            "执行",
            "保存吧",
        }:
            return "confirm"
        if re.fullmatch(
            r"(?:我)?(?:是的)?(?:确认|同意)(?:以上|上述)?(?:信息|内容)?(?:无误)?(?:请)?(?:马上|正式)?(?:写入|保存|执行)?(?:吧)?",
            normalized,
        ):
            return "confirm"
        return None
