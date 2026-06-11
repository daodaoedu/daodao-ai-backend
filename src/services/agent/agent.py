import json
import re
import uuid
from pathlib import Path
from typing import AsyncIterator

import yaml

from src.logger import AppLogger
from src.services.agent.context import ContextBuilder
from src.services.agent.state import AppState
from src.services.llm.client import LLMClient

logger = AppLogger(__name__).get_logger()

_SKILLS_DIR = Path(__file__).parent / "skills"

# Matches ```json ... ``` or ```tool_call ... ``` blocks
_JSON_BLOCK_RE = re.compile(r"```(?:json|tool_call)\s*(\{.*?\})\s*```", re.DOTALL)


class SkillLoader:
    """Loads SKILL.md files from skills/ subdirectories and returns their metadata."""

    def load_skills(self, skills_dir: Path) -> list[dict]:
        """Scan for */SKILL.md, parse YAML frontmatter (name, description).
        Returns list of {name, description, path}.
        """
        skills = []
        if not skills_dir.exists():
            return skills

        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            try:
                content = skill_md.read_text(encoding="utf-8")
                metadata = self._parse_frontmatter(content)
                if metadata:
                    skills.append(
                        {
                            "name": metadata.get("name", skill_md.parent.name),
                            "description": metadata.get("description", ""),
                            "path": str(skill_md),
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to load skill from {skill_md}: {exc}")

        return skills

    def get_skill_content(self, skill_path: Path) -> str:
        """Read full SKILL.md content."""
        return Path(skill_path).read_text(encoding="utf-8")

    def _parse_frontmatter(self, content: str) -> dict:
        """Parse YAML frontmatter delimited by --- lines."""
        if not content.startswith("---"):
            return {}
        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}
        try:
            return yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            return {}


class DaoDaoAgent:
    """Intent recognition and skill dispatch using LLMClient."""

    def __init__(self, settings, state: AppState):
        self.settings = settings
        self.state = state
        self._skill_loader = SkillLoader()
        self._context_builder = ContextBuilder()

    async def process_turn(
        self,
        user_message: str,
        thread_history: list[dict],
    ) -> AsyncIterator[dict]:
        # 1. Build context
        system_context = self._context_builder.build(self.state)

        # 2. Load and inject skill registry
        skills = self._skill_loader.load_skills(_SKILLS_DIR)
        skill_registry_text = self._build_skill_registry(skills)

        system_prompt = f"{system_context}\n\n{skill_registry_text}"

        # 3. Build conversation prompt
        prompt = self._build_prompt(system_prompt, thread_history, user_message)

        # 4. Call LLMClient
        llm = LLMClient(self.settings, self.state.provider, enable_guardrail=False)
        if self.state.model_override:
            llm._backend.config["model"] = self.state.model_override

        output, _cost, _usage, _backend = await llm.generate(prompt)

        # 5. Parse tool calls from response
        tool_calls = self._parse_tool_calls(output)

        if tool_calls:
            for tc in tool_calls:
                tool_name = tc.get("tool") or tc.get("name", "unknown")
                tool_args = tc.get("args") or tc.get("arguments") or tc.get("params", {})
                self.state.tools_used.append(tool_name)

                # Check if this is a bulk action requiring approval
                if tool_name in ("send_emails", "send_notifications", "bulk_send_emails"):
                    approval_id = str(uuid.uuid4())
                    self.state.approval_pending = True
                    yield {
                        "type": "approval_request",
                        "id": approval_id,
                        "action": tool_name,
                        "description": f"Request to execute: {tool_name}",
                        "payload": tool_args,
                        "preview": tool_args.get("preview", []),
                    }
                else:
                    yield {
                        "type": "tool_call",
                        "tool": tool_name,
                        "args": tool_args,
                        "result": None,  # Execution handled by engine
                    }

        # Clean response text (remove tool_call blocks)
        clean_output = _JSON_BLOCK_RE.sub("", output).strip()
        if clean_output:
            yield {"type": "agent_message", "content": clean_output}

        yield {"type": "result", "summary": clean_output or "(no output)"}

    def _build_skill_registry(self, skills: list[dict]) -> str:
        if not skills:
            return "## Available Skills\n(none loaded)"

        lines = ["## Available Skills\n"]
        for skill in skills:
            lines.append(f"### {skill['name']}")
            lines.append(f"{skill['description']}\n")

        lines.append(
            "\nTo invoke a skill, respond with a JSON tool_call block:\n"
            "```json\n"
            '{"tool": "<skill_name>", "args": {...}}\n'
            "```"
        )
        return "\n".join(lines)

    def _build_prompt(
        self,
        system_prompt: str,
        history: list[dict],
        user_message: str,
    ) -> str:
        parts = [f"<system>\n{system_prompt}\n</system>\n"]

        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            parts.append(f"<{role}>\n{content}\n</{role}>")

        parts.append(f"<user>\n{user_message}\n</user>")
        parts.append("<assistant>")
        return "\n".join(parts)

    def _parse_tool_calls(self, response: str) -> list[dict]:
        """Parse tool calls from LLM response. Looks for ```json {...} ``` blocks."""
        results = []
        for match in _JSON_BLOCK_RE.finditer(response):
            try:
                data = json.loads(match.group(1))
                if isinstance(data, dict) and ("tool" in data or "name" in data):
                    results.append(data)
            except json.JSONDecodeError:
                pass
        return results
