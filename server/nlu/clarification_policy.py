import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from server.config import ROOT_DIR
from server.nlu.taxonomy_classifier import TaxonomyCandidate, TaxonomyClassification, classify_taxonomy_query


DEFAULT_POLICY_PATH = ROOT_DIR / "data" / "clarification_policy.json"


class ClarificationRule(BaseModel):
    id: str
    product_type: str
    subject: str
    trigger_terms: list[str] = Field(default_factory=list)
    required_slots: list[str] = Field(default_factory=list)
    optional_slots: list[str] = Field(default_factory=list)
    ask_order: list[str] = Field(default_factory=list)
    max_clarifications: int = 1
    allow_default_recommendation: bool = True
    min_confidence_for_default: float = 0.9
    slot_terms: dict[str, list[str]] = Field(default_factory=dict)
    slot_regex: dict[str, str] = Field(default_factory=dict)
    slot_validators: dict[str, "SlotValidator"] = Field(default_factory=dict)
    question_templates: dict[str, str] = Field(default_factory=dict)
    provided_detail_terms: list[str] = Field(default_factory=list)
    budget_regex: str = ""
    question: str = ""


class SlotValidator(BaseModel):
    type: str = "non_empty"
    min_value: float | None = None
    max_value: float | None = None


class ClarificationPolicyConfig(BaseModel):
    version: str = ""
    rules: list[ClarificationRule] = Field(default_factory=list)
    default_question_template: str = "可以。我先确认一下：你对{subject}更看重什么场景、预算和品牌偏好吗？"


@dataclass(frozen=True)
class ClarificationDecision:
    subject: str
    question: str
    rule_id: str
    product_type: str
    missing_slots: tuple[str, ...] = ()
    requested_slot: str = ""
    filled_slots: dict[str, object] | None = None


class CategoryClarificationPolicy:
    def __init__(self, config: ClarificationPolicyConfig) -> None:
        self.config = config
        self._rules_by_product_type = {rule.product_type: rule for rule in config.rules}

    @classmethod
    def from_file(cls, path: str | Path = DEFAULT_POLICY_PATH) -> "CategoryClarificationPolicy":
        file_path = Path(path)
        config = ClarificationPolicyConfig.model_validate_json(file_path.read_text(encoding="utf-8"))
        return cls(config)

    def decide(
        self,
        message: str,
        taxonomy: TaxonomyClassification | None = None,
        *,
        filled_slots: dict[str, object] | None = None,
        confidence_by_field: dict[str, float] | None = None,
        clarification_counts: dict[str, int] | None = None,
        skipped_product_types: set[str] | None = None,
    ) -> ClarificationDecision | None:
        normalized = message.strip()
        if not normalized:
            return None

        taxonomy = taxonomy or classify_taxonomy_query(normalized)
        filled_slots = dict(filled_slots or {})
        confidence_by_field = dict(confidence_by_field or {})
        clarification_counts = dict(clarification_counts or {})
        skipped_product_types = skipped_product_types or set()
        for match in taxonomy.product_types:
            rule = self._rules_by_product_type.get(match.value)
            if rule is None:
                continue
            if match.value in skipped_product_types:
                continue
            if not self._trigger_applies(rule, normalized):
                continue

            effective_slots = self._collect_filled_slots(rule, normalized, filled_slots)
            missing_slots = self._missing_required_slots(rule, effective_slots)
            if rule.required_slots:
                if not missing_slots:
                    continue
                if clarification_counts.get(rule.product_type, 0) >= max(0, rule.max_clarifications):
                    continue
                if self._can_default_without_clarification(rule, confidence_by_field, match):
                    continue
                question = self._build_slot_question(rule, missing_slots)
            else:
                if not self._legacy_rule_applies(rule, normalized):
                    continue
                question = rule.question or self.config.default_question_template.format(subject=rule.subject)

            return ClarificationDecision(
                subject=rule.subject,
                question=question,
                rule_id=rule.id,
                product_type=rule.product_type,
                missing_slots=tuple(missing_slots),
                requested_slot=missing_slots[0] if missing_slots else "",
                filled_slots=effective_slots,
            )
        return None

    def collect_filled_slots(
        self,
        product_type: str,
        message: str,
        filled_slots: dict[str, object] | None = None,
    ) -> dict[str, object]:
        rule = self._rules_by_product_type.get(product_type)
        if rule is None:
            return dict(filled_slots or {})
        return self._collect_filled_slots(rule, message, dict(filled_slots or {}))

    def _trigger_applies(self, rule: ClarificationRule, message: str) -> bool:
        if rule.trigger_terms and not any(term in message for term in rule.trigger_terms):
            return False
        return True

    def _legacy_rule_applies(self, rule: ClarificationRule, message: str) -> bool:
        if rule.provided_detail_terms and any(term in message for term in rule.provided_detail_terms):
            return False
        if rule.budget_regex and re.search(rule.budget_regex, message):
            return False
        return True

    def _collect_filled_slots(
        self,
        rule: ClarificationRule,
        message: str,
        filled_slots: dict[str, object],
    ) -> dict[str, object]:
        effective = {key: value for key, value in filled_slots.items() if _slot_value_is_filled(value)}

        if rule.budget_regex:
            budget_match = re.search(rule.budget_regex, message)
            if budget_match:
                effective.setdefault(
                    "budget",
                    {
                        "source": "clarification_policy.regex",
                        "span": budget_match.group(0),
                    },
                )

        for slot_name, pattern in rule.slot_regex.items():
            if not pattern:
                continue
            match = re.search(pattern, message)
            if match:
                effective.setdefault(
                    slot_name,
                    {
                        "source": "clarification_policy.regex",
                        "span": match.group(0),
                    },
                )

        for slot_name, terms in rule.slot_terms.items():
            matched_terms = [term for term in terms if term and term in message]
            if matched_terms:
                effective.setdefault(
                    slot_name,
                    {
                        "source": "clarification_policy.terms",
                        "terms": matched_terms,
                    },
                )

        if rule.provided_detail_terms and any(term in message for term in rule.provided_detail_terms):
            matched_terms = [term for term in rule.provided_detail_terms if term in message]
            effective.setdefault(
                "use_case",
                {
                    "source": "clarification_policy.legacy_detail_terms",
                    "terms": matched_terms,
                },
            )

        return self._validate_filled_slots(rule, effective)

    def _validate_filled_slots(
        self,
        rule: ClarificationRule,
        filled_slots: dict[str, object],
    ) -> dict[str, object]:
        if not rule.slot_validators:
            return filled_slots
        valid: dict[str, object] = {}
        for slot_name, value in filled_slots.items():
            validator = rule.slot_validators.get(slot_name)
            if validator is None or validate_slot_value(value, validator):
                valid[slot_name] = value
        return valid

    def _missing_required_slots(self, rule: ClarificationRule, filled_slots: dict[str, object]) -> list[str]:
        ask_order = [slot for slot in rule.ask_order if slot in rule.required_slots]
        ordered_slots = [*ask_order, *(slot for slot in rule.required_slots if slot not in ask_order)]
        return [slot for slot in ordered_slots if not _slot_value_is_filled(filled_slots.get(slot))]

    def _can_default_without_clarification(
        self,
        rule: ClarificationRule,
        confidence_by_field: dict[str, float],
        match: TaxonomyCandidate,
    ) -> bool:
        if not rule.allow_default_recommendation:
            return False
        product_type_confidence = max(float(confidence_by_field.get("product_type", 0.0)), float(match.confidence))
        return product_type_confidence >= rule.min_confidence_for_default

    def _build_slot_question(self, rule: ClarificationRule, missing_slots: list[str]) -> str:
        key = ",".join(missing_slots)
        if key in rule.question_templates:
            return rule.question_templates[key]

        fallback_key = ",".join(slot for slot in rule.required_slots if slot in missing_slots)
        if fallback_key in rule.question_templates:
            return rule.question_templates[fallback_key]

        if rule.question:
            return rule.question
        return self.config.default_question_template.format(subject=rule.subject)


def _slot_value_is_filled(value: object) -> bool:
    if value is None:
        return False
    if value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def validate_slot_value(value: object, validator: SlotValidator) -> bool:
    if not _slot_value_is_filled(value):
        return False
    if validator.type == "price":
        prices = extract_numeric_values(value)
        if not prices:
            return False
        return any(
            (validator.min_value is None or price >= validator.min_value)
            and (validator.max_value is None or price <= validator.max_value)
            for price in prices
        )
    return True


def extract_numeric_values(value: object) -> list[float]:
    values: list[float] = []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, str):
        return [float(item) for item in re.findall(r"\d+(?:\.\d+)?", value)]
    if isinstance(value, dict):
        for item in value.values():
            values.extend(extract_numeric_values(item))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            values.extend(extract_numeric_values(item))
    return values


@lru_cache
def get_default_clarification_policy() -> CategoryClarificationPolicy:
    return CategoryClarificationPolicy.from_file(DEFAULT_POLICY_PATH)
