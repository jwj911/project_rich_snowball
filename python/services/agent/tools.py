"""Agent 工具系统。

提供 Tool 基类、注册表和装饰器，支持 Agent 动态发现和调用工具。
"""

from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from errors import ErrorCode
from services.domain.exceptions import ServiceError

if TYPE_CHECKING:
    from services.agent.context import AgentContext

logger = logging.getLogger(__name__)


@dataclass
class ToolParameter:
    """工具参数定义。"""

    name: str
    type: str
    description: str
    required: bool = True


@dataclass
class ToolDefinition:
    """工具定义（用于 LLM function calling）。"""

    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)

    def to_openai_schema(self) -> dict[str, Any]:
        """转换为 OpenAI function schema。"""
        props: dict[str, Any] = {}
        required: list[str] = []
        for p in self.parameters:
            props[p.name] = {"type": p.type, "description": p.description}
            if p.required:
                required.append(p.name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
        }


class Tool:
    """工具基类。"""

    name: str = ""
    description: str = ""

    def __init__(self) -> None:
        self._definition: ToolDefinition | None = None

    @property
    def definition(self) -> ToolDefinition:
        if self._definition is None:
            self._definition = self._build_definition()
        return self._definition

    def _build_definition(self) -> ToolDefinition:
        """子类可重写以自定义参数定义。"""
        return ToolDefinition(name=self.name, description=self.description)

    async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
        """执行工具逻辑。

        子类必须实现。
        """
        raise NotImplementedError

    def format_result(self, result: Any) -> str:
        """将工具执行结果格式化为文本，供 LLM 观察。"""
        if isinstance(result, dict | list):
            return json.dumps(result, ensure_ascii=False, default=str)
        return str(result)


class ToolRegistry:
    """工具注册表。

    统一管理所有可用工具，支持按名称查找。
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册工具。"""
        if not tool.name:
            raise ValueError("Tool must have a name")
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def get(self, name: str) -> Tool | None:
        """按名称获取工具。"""
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        """获取所有已注册工具。"""
        return list(self._tools.values())

    def get_openai_schemas(self) -> list[dict[str, Any]]:
        """获取所有工具的 OpenAI function schema。"""
        return [t.definition.to_openai_schema() for t in self._tools.values()]

    async def execute(self, name: str, context: AgentContext, params: dict[str, Any]) -> Any:
        """按名称执行已注册工具。"""
        tool = self.get(name)
        if tool is None:
            raise ServiceError(
                code=ErrorCode.AGENT_TOOL_ERROR,
                message=f"未知工具：{name}",
                status_code=400,
            )
        try:
            return await tool.execute(context, **params)
        except ServiceError:
            raise
        except Exception as exc:
            logger.exception("Agent tool failed: %s", name)
            raise ServiceError(
                code=ErrorCode.AGENT_TOOL_ERROR,
                message=f"工具 {name} 执行失败：{exc}",
                status_code=500,
            ) from exc

    def get_tools_description(self) -> str:
        """生成工具描述文本（用于 prompt）。"""
        lines = ["你可以使用以下工具："]
        for tool in self._tools.values():
            lines.append(f"- {tool.name}: {tool.description}")
            for p in tool.definition.parameters:
                req = "(必需)" if p.required else "(可选)"
                lines.append(f"  - {p.name} ({p.type}){req}: {p.description}")
        return "\n".join(lines)


# 全局默认注册表
_default_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表。"""
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry()
    return _default_registry


def register_tool(tool: Tool) -> Tool:
    """将工具注册到全局注册表。"""
    get_tool_registry().register(tool)
    return tool


def tool_def(name: str, description: str) -> Callable:
    """装饰器：将函数转换为 Tool。

    被装饰的函数第一个参数必须是 context（AgentContext），
    其余参数即为工具参数。
    """

    def decorator(func: Callable) -> Tool:
        sig = inspect.signature(func)
        params: list[ToolParameter] = []
        for param_name, param in list(sig.parameters.items())[1:]:  # 跳过 context
            ptype = "string"
            if isinstance(param.annotation, type) and issubclass(param.annotation, int | float):
                ptype = "number"
            elif isinstance(param.annotation, type) and issubclass(param.annotation, bool):
                ptype = "boolean"
            params.append(
                ToolParameter(
                    name=param_name,
                    type=ptype,
                    description="",
                    required=param.default is inspect.Parameter.empty,
                )
            )

        class _FuncTool(Tool):
            def __init__(self) -> None:
                super().__init__()
                self.name = name
                self.description = description
                self._func = func

            def _build_definition(self) -> ToolDefinition:
                return ToolDefinition(name=name, description=description, parameters=params)

            async def execute(self, context: AgentContext, **kwargs: Any) -> Any:
                return await self._func(context, **kwargs)

        t = _FuncTool()
        register_tool(t)
        return t

    return decorator
