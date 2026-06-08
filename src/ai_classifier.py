from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

EMAIL_TASK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "task_type_id": {"type": "string"},
        "task_type_name": {"type": "string"},
        "priority": {"type": "integer", "minimum": 1, "maximum": 3},
        "counterparty": {"type": ["string", "null"]},
        "fund_or_entity": {"type": ["string", "null"]},
        "due_date": {"type": ["string", "null"], "description": "YYYY-MM-DD if clearly present, else null"},
        "missing_items": {"type": "array", "items": {"type": "string"}},
        "next_action": {"type": "string"},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "human_review_required": {"type": "boolean"},
        "draft_reply": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "notes": {"type": "string"},
    },
    "required": [
        "task_type_id",
        "task_type_name",
        "priority",
        "counterparty",
        "fund_or_entity",
        "due_date",
        "missing_items",
        "next_action",
        "risk_flags",
        "human_review_required",
        "draft_reply",
        "confidence",
        "notes",
    ],
}

REQUIRED_KEYS = EMAIL_TASK_SCHEMA["required"]


class AIClassifier:
    def __init__(self, api_key: str, model: str, config: dict, base_url: str | None = None, provider: str = "openai"):
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model
        self.config = config
        self.provider = provider.lower()

    def classify_and_draft(self, email_payload: dict) -> dict:
        task_catalog = [
            {
                "id": t["id"],
                "name": t["name"],
                "priority_default": t.get("priority_default", 3),
                "description": t.get("description", ""),
                "draft_style": t.get("draft_style", ""),
            }
            for t in self.config.get("task_types", [])
        ]

        instructions = """
You are an operations email triage assistant for an investment/fund operations team.
Classify the email into exactly one task_type_id from the provided task catalog.
Extract concrete operational fields only when present or strongly implied.
Create a concise Outlook draft reply.
Never claim that payment/funds/wires/NAV/fees/legal docs are confirmed unless the email explicitly proves it.
For wire transfer, legal document, subscription document, ODD response, payment confirmation, or investor-facing messages, set human_review_required=true and include risk flags.
Do not include unsupported calculations. If calculation is needed, say it requires deterministic spreadsheet/code review.
Return only valid JSON. Do not wrap it in markdown.
The JSON object must contain exactly these keys:
task_type_id, task_type_name, priority, counterparty, fund_or_entity, due_date, missing_items, next_action, risk_flags, human_review_required, draft_reply, confidence, notes.
Use null for unknown scalar fields, [] for unknown lists, and keep confidence between 0 and 1.
Example JSON shape:
{
  "task_type_id": "investor_onboarding_kyc",
  "task_type_name": "Investor Onboarding & KYC",
  "priority": 1,
  "counterparty": "Investor ABC",
  "fund_or_entity": "GCF",
  "due_date": null,
  "missing_items": ["passport copy"],
  "next_action": "Draft a follow-up requesting missing KYC documents.",
  "risk_flags": ["investor_facing_email"],
  "human_review_required": true,
  "draft_reply": "Dear ...",
  "confidence": 0.9,
  "notes": "..."
}
""".strip()

        user_content = {
            "task_catalog": task_catalog,
            "risk_policy": self.config.get("risk_policy", {}),
            "email": email_payload,
        }

        try:
            response_format = self._response_format()
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
                ],
                "response_format": response_format,
                "temperature": 0,
                "max_tokens": 1800,
            }
            response = self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            parsed = self._parse_json(content)
            return self._normalise(parsed)
        except Exception as exc:
            # Fallback keeps the workflow moving without pretending the AI succeeded.
            return {
                "task_type_id": "unknown",
                "task_type_name": "Unknown / Needs Manual Triage",
                "priority": 3,
                "counterparty": None,
                "fund_or_entity": None,
                "due_date": None,
                "missing_items": [],
                "next_action": "Manual review required because AI classification failed.",
                "risk_flags": ["ai_error"],
                "human_review_required": True,
                "draft_reply": "Dear all,\n\nThank you for your email. We are reviewing this internally and will revert shortly.\n\nBest regards,",
                "confidence": 0.0,
                "notes": f"AI error: {exc}",
            }

    def _response_format(self) -> dict[str, Any]:
        # OpenAI supports strict json_schema on many current models. DeepSeek's
        # documented OpenAI-compatible API supports json_object JSON mode, not
        # necessarily OpenAI's strict json_schema parameter. We validate and
        # normalise locally after parsing.
        if "deepseek" in self.provider:
            return {"type": "json_object"}
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "ops_email_task",
                "strict": True,
                "schema": EMAIL_TASK_SCHEMA,
            },
        }

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        content = content.strip()
        if not content:
            raise ValueError("model returned empty content")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Defensive fallback if a provider returns fenced JSON despite instructions.
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.DOTALL)
            if match:
                return json.loads(match.group(1))
            match = re.search(r"(\{.*\})", content, flags=re.DOTALL)
            if match:
                return json.loads(match.group(1))
            raise

    @staticmethod
    def _normalise(data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("model output is not a JSON object")

        defaults = {
            "task_type_id": "unknown",
            "task_type_name": "Unknown / Needs Manual Triage",
            "priority": 3,
            "counterparty": None,
            "fund_or_entity": None,
            "due_date": None,
            "missing_items": [],
            "next_action": "Manual review required.",
            "risk_flags": [],
            "human_review_required": True,
            "draft_reply": "Dear all,\n\nThank you for your email. We are reviewing this internally and will revert shortly.\n\nBest regards,",
            "confidence": 0.0,
            "notes": "",
        }
        out = {key: data.get(key, defaults[key]) for key in REQUIRED_KEYS}

        try:
            out["priority"] = int(out["priority"])
        except Exception:
            out["priority"] = 3
        out["priority"] = max(1, min(3, out["priority"]))

        if not isinstance(out["missing_items"], list):
            out["missing_items"] = [str(out["missing_items"])] if out["missing_items"] else []
        if not isinstance(out["risk_flags"], list):
            out["risk_flags"] = [str(out["risk_flags"])] if out["risk_flags"] else []

        out["human_review_required"] = bool(out["human_review_required"])
        try:
            out["confidence"] = float(out["confidence"])
        except Exception:
            out["confidence"] = 0.0
        out["confidence"] = max(0.0, min(1.0, out["confidence"]))

        for key in ["task_type_id", "task_type_name", "next_action", "draft_reply", "notes"]:
            out[key] = str(out[key] or defaults[key])

        for key in ["counterparty", "fund_or_entity", "due_date"]:
            if out[key] is not None:
                out[key] = str(out[key])

        return out
