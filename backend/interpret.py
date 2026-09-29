"""LLM-based report interpretation with strict JSON output.

Sends OCR'd report text to an OpenAI-compatible chat endpoint and returns a
patient-friendly structured interpretation. The model is instructed to quote
report sentences verbatim as evidence and must never fabricate findings.

Configuration is via environment variables:

  LLM_BASE_URL  e.g. https://api.deepseek.com
  LLM_API_KEY   required; if unset the endpoint reports 503
  LLM_MODEL     default: deepseek-chat
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
REQUEST_TIMEOUT = 90.0
MAX_REPORT_CHARS = 8000

DISCLAIMER = (
    "以下内容仅为帮助理解检查报告的辅助信息，不构成任何诊断、治疗建议或医疗结论。"
    "请以医院正式报告为准，如有疑问请咨询执业医师。"
)

SYSTEM_PROMPT = """你是一名医疗报告解读助手，面向没有任何医学背景的患者。
你的任务：把检查报告原文转换成患者能看懂的结构化解读。

硬性规则：
1. 只能依据用户提供的报告原文，不得推测、补充或虚构任何信息。
2. 所有 quote 字段必须是报告原文中的句子或短语，逐字摘录，不得改写。
3. 不得给出明确诊断结论、不得推荐具体药物或治疗方案；只能解释含义并建议咨询医生。
4. 使用通俗的中文，避免专业术语；必须使用时用括号给出大白话解释。
5. 只输出一个 JSON 对象，不要输出任何其他文字、不要用 markdown 代码块包裹。

输出 JSON 结构：
{
  "summary": "用两三句话概括这份报告主要说了什么，大白话",
  "line_explanations": [
    {"quote": "报告原句", "explanation": "这句话是什么意思，大白话"}
  ],
  "abnormal_items": [
    {"quote": "报告原句", "level": "high|medium|low", "meaning": "这个异常意味着什么，大白话", "suggestion": "建议怎么做（只能是：就医/复查/随访/咨询医生类建议）"}
  ],
  "questions_for_doctor": ["建议下次就诊时问医生的问题"]
}

分级规则：
- high: 报告明确提示需要尽快处理的异常
- medium: 需要随访或复查的异常
- low: 轻微异常或年龄相关的常见改变
如果报告全部正常，abnormal_items 返回空数组，并在 summary 中说明报告未见明显异常。
line_explanations 覆盖报告中所有有信息量的句子（通常 3-8 条）。"""


class InterpretRequest(BaseModel):
    full_text: str = Field(min_length=1)
    lines: list[dict[str, Any]] = Field(default_factory=list)


class InterpretNotConfiguredError(RuntimeError):
    """Raised when no LLM credentials are configured."""


class InterpretUnavailableError(RuntimeError):
    """Raised when the LLM call or its JSON output cannot be used."""


def _config() -> tuple[str, str, str]:
    base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    if not api_key:
        raise InterpretNotConfiguredError("未配置 LLM_API_KEY，解读功能不可用")
    return base_url, api_key, model


def _extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of the model's reply."""
    text = text.strip()
    # Strip a markdown fence if the model added one despite instructions.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError("模型回复中没有 JSON 对象")
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if escape:
            escape = False
            continue
        if char == "\\" and in_string:
            escape = True
            continue
        if char == '"':
            in_string = not in_string
        elif not in_string:
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start : index + 1])
    raise ValueError("模型回复中的 JSON 不完整")


def _validate(payload: dict[str, Any], report_text: str) -> dict[str, Any]:
    """Coerce the model output into our schema; drop quotes not in the report."""
    if not isinstance(payload.get("summary"), str) or not payload["summary"].strip():
        raise ValueError("缺少 summary 字段")

    def check_quote(item: dict[str, Any]) -> bool:
        quote = item.get("quote", "")
        return isinstance(quote, str) and bool(quote.strip()) and quote in report_text

    line_explanations = [
        {"quote": item["quote"].strip(), "explanation": str(item.get("explanation", "")).strip()}
        for item in payload.get("line_explanations", [])
        if isinstance(item, dict) and check_quote(item)
    ]
    abnormal_items = []
    for item in payload.get("abnormal_items", []):
        if not isinstance(item, dict) or not check_quote(item):
            continue
        level = str(item.get("level", "low")).lower()
        if level not in ("high", "medium", "low"):
            level = "low"
        abnormal_items.append(
            {
                "quote": item["quote"].strip(),
                "level": level,
                "meaning": str(item.get("meaning", "")).strip(),
                "suggestion": str(item.get("suggestion", "")).strip(),
            }
        )
    questions = [
        str(question).strip()
        for question in payload.get("questions_for_doctor", [])
        if isinstance(question, str) and question.strip()
    ]
    return {
        "summary": payload["summary"].strip(),
        "line_explanations": line_explanations,
        "abnormal_items": abnormal_items,
        "questions_for_doctor": questions[:5],
        "disclaimer": DISCLAIMER,
    }


def interpret_report(report: InterpretRequest) -> dict[str, Any]:
    base_url, api_key, model = _config()
    report_text = report.full_text[:MAX_REPORT_CHARS]

    def call_llm(extra_note: str = "") -> str:
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT + extra_note},
                    {"role": "user", "content": f"以下是检查报告原文：\n\n{report_text}"},
                ],
                "temperature": 0.2,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        choices = response.json().get("choices") or []
        if not choices:
            raise ValueError("LLM 返回为空")
        return choices[0]["message"]["content"]

    try:
        try:
            payload = _validate(_extract_json(call_llm()), report_text)
        except (ValueError, KeyError, json.JSONDecodeError):
            # One retry with a stronger reminder before giving up.
            retry_note = "\n\n注意：上一次回复不符合要求。本次必须只输出一个合法的 JSON 对象，且所有 quote 必须逐字摘自报告原文。"
            payload = _validate(_extract_json(call_llm(retry_note)), report_text)
    except httpx.HTTPStatusError as error:
        raise InterpretUnavailableError(f"LLM 服务返回错误: HTTP {error.response.status_code}") from error
    except httpx.HTTPError as error:
        raise InterpretUnavailableError(f"LLM 服务连接失败: {type(error).__name__}") from error
    except (ValueError, KeyError, json.JSONDecodeError) as error:
        raise InterpretUnavailableError(f"LLM 输出格式异常: {error}") from error
    return payload
