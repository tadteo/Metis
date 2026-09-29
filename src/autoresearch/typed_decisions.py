"""Validated non-generative advisory questions and their dependent answer contracts."""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import Field, model_validator

from .contracts import Model


class TypedQuestion(Model):
    type: Literal["noul", "choice", "score"]
    prompt: str
    criteria: dict[str, str] | list[str] | None = None

    @model_validator(mode="after")
    def check_criteria(self) -> Self:
        validate_questions({"question": self.model_dump()})
        return self


class NoulAnswer(Model):
    noul: float = Field(ge=0, le=1, strict=True)


class ChoiceAnswer(Model):
    choice: str = Field(strict=True)


class ScoreAnswer(Model):
    score: float = Field(ge=0, strict=True)


class TypedDecisionResult(Model):
    answers: dict[str, NoulAnswer | ChoiceAnswer | ScoreAnswer]


def validate_questions(questions: dict[str, Any]) -> None:
    for question in questions.values():
        if (
            not isinstance(question, dict)
            or not isinstance(question.get("type"), str)
            or question["type"] not in {"noul", "choice", "score"}
        ):
            raise ValueError("Unsupported typed question")
        kind, criteria = question["type"], question.get("criteria")
        if kind == "choice" and (not isinstance(criteria, (dict, list)) or not criteria):
            raise ValueError("Typed choice requires nonempty criteria")
        if kind == "score" and (not isinstance(criteria, list) or not criteria):
            raise ValueError("Typed score requires nonempty ordered criteria")
        if criteria is not None and (
            not isinstance(criteria, (dict, list))
            or any(not isinstance(item, str) or not item.strip() for item in criteria)
        ):
            raise ValueError("Typed criteria must have nonempty string labels")


def validate_answers(questions: dict[str, Any], output: dict[str, Any]) -> None:
    validate_questions(questions)
    value = TypedDecisionResult.model_validate({"answers": output.get("answers")})
    if set(value.answers) != set(questions):
        raise ValueError("Typed result must answer exactly the declared questions")
    for name, question in questions.items():
        answer = value.answers[name].model_dump()
        kind = question["type"]
        if kind not in answer:
            raise ValueError("Answer type differs from the declared question")
        if kind == "choice" and answer[kind] not in question["criteria"]:
            raise ValueError("Choice is outside the declared criteria")
        if kind == "score" and answer[kind] > len(question["criteria"]) - 1:
            raise ValueError("Score exceeds the declared ordered criteria")


def output_schema(questions: dict[str, Any]) -> dict[str, Any]:
    validate_questions(questions)
    schema = TypedDecisionResult.model_json_schema()
    properties = {}
    for name, question in questions.items():
        kind = question["type"]
        answer = {"type": "number", "minimum": 0, "maximum": 1}
        if kind == "choice":
            answer = {"type": "string", "enum": list(question["criteria"])}
        elif kind == "score":
            answer["maximum"] = len(question["criteria"]) - 1
        properties[name] = {
            "type": "object",
            "properties": {kind: answer},
            "required": [kind],
            "additionalProperties": False,
        }
    schema["properties"]["answers"] = {
        "type": "object",
        "properties": properties,
        "required": list(questions),
        "additionalProperties": False,
    }
    return schema
