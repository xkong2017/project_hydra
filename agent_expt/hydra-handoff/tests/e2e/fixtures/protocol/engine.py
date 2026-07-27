import json
import os


class ScoringEngine:
    def __init__(self, config_path=None):
        self._rules = []
        if config_path and os.path.exists(config_path):
            with open(config_path) as f:
                cfg = json.load(f)
            self._load_rules(cfg)

    def _load_rules(self, cfg):
        for rule in cfg.get("scoring_rules", []):
            self._rules.append(rule)

    def set_rules(self, rules):
        self._rules = list(rules)

    def score(self, record):
        total = 0
        scored_fields = set()  # Track fields that have already been scored

        for rule in self._rules:
            field = rule["field"]

            # Skip if this field has already matched a rule
            if field in scored_fields:
                continue

            op = rule["op"]
            value = rule["value"]
            points = rule["points"]

            actual = record.get(field)
            if actual is None:
                continue

            matched = False
            if op == "gt" and actual > value:
                matched = True
            elif op == "gte" and actual >= value:
                matched = True
            elif op == "eq" and actual == value:
                matched = True
            elif op == "lt" and actual < value:
                matched = True
            elif op == "lte" and actual <= value:
                matched = True
            elif op == "in" and actual in value:
                matched = True

            if matched:
                total += points
                scored_fields.add(field)  # Mark field as scored to prevent stacking

        return total
