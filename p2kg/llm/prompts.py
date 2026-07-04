"""PromptManager — jinja2-шаблоны по этапам.

Каждый шаг = пара шаблонов: `<name>.system.jinja` (роль/правила/формат) + `<name>.user.jinja`
(конкретный вход). system опционален. Старый `<name>.jinja` поддержан через render() для совместимости.
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class PromptManager:
    def __init__(self, prompts_dir: str | Path = _PROMPTS_DIR) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(prompts_dir)),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, name: str, **variables) -> str:
        return self.env.get_template(f"{name}.jinja").render(**variables)

    def render_pair(self, name: str, **variables) -> tuple[str, str]:
        """-> (system, user). system = "" если файла нет."""
        user = self.env.get_template(f"{name}.user.jinja").render(**variables)
        try:
            system = self.env.get_template(f"{name}.system.jinja").render(**variables)
        except TemplateNotFound:
            system = ""
        return system, user
