from dataclasses import dataclass
from string import Template
from typing import Mapping


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: str
    system_template: str


PROMPT_TEMPLATES = {
    ("knowledge_decision", "v1"): PromptTemplate(
        name="knowledge_decision",
        version="v1",
        system_template=(
            "你是${product_name}的知识库决策器。资料不足时搜索，资料充分时结束回答。"
            "不得编造制度内容。"
        ),
    ),
}


def render_prompt(
    name: str,
    version: str,
    variables: Mapping[str, str],
) -> str:
    prompt_template = PROMPT_TEMPLATES.get((name, version))
    if prompt_template is None:
        raise ValueError("unknown_prompt_template")

    try:
        return Template(prompt_template.system_template).substitute(variables)
    except KeyError as exc:
        raise ValueError(f"missing_prompt_variable: {exc.args[0]}") from exc
