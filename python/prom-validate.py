#!/usr/bin/env python3
"""
Check PrometheusRule expressions for aggregation operators that may
drop required labels (job, exported_namespace, namespace).

Usage:
    kubectl get prometheusrule -A -o json | python3 check_prom_labels.py
"""

import json
import re
import sys

REQUIRED_LABELS = {"job", "exported_namespace", "namespace"}
THANOS_ENV_LABELS = {"k8s_env", "env"}  # at least one required for role: thanos-rule

AGG_OPS = (
    "sum", "count", "avg", "min", "max", "topk", "bottomk",
    "count_values", "quantile", "stddev", "stdvar", "group",
)

AGG_RE = re.compile(
    r'\b(' + '|'.join(AGG_OPS) + r')\b',
    re.IGNORECASE,
)

BY_WITHOUT_RE = re.compile(
    r'\s+(by|without)\s*\(([^)]*)\)',
    re.IGNORECASE,
)

ABSENT_RE = re.compile(r'\babsent(_over_time)?\s*\(', re.IGNORECASE)
LABEL_MATCHER_RE = re.compile(r'(\w+)\s*(=~|!~|!=|=)\s*"[^"]*"')


def find_matching_paren(expr, start):
    """Find the index of the closing paren matching the open paren at `start`."""
    depth = 0
    for i in range(start, len(expr)):
        if expr[i] == '(':
            depth += 1
        elif expr[i] == ')':
            depth -= 1
            if depth == 0:
                return i
    return -1


def extract_clause(expr, pos):
    """
    Given position right after an agg op keyword, look for by/without clause
    either BEFORE or AFTER the aggregation's parenthesized expression.

    PromQL allows:
        sum by (labels) (vector)
        sum(vector) by (labels)
        sum(vector)               -- bare, no clause
    """
    rest = expr[pos:]

    # Case 1: by/without comes before the paren group
    m = re.match(r'\s+(by|without)\s*\(([^)]*)\)', rest, re.IGNORECASE)
    if m:
        clause = m.group(1).lower()
        labels = {l.strip() for l in m.group(2).split(',') if l.strip()}
        return clause, labels

    # Case 2: bare paren first, then optional by/without after
    m_paren = re.match(r'\s*\(', rest)
    if m_paren:
        open_idx = pos + m_paren.end() - 1
        close_idx = find_matching_paren(expr, open_idx)
        if close_idx >= 0:
            after = expr[close_idx + 1:]
            m2 = re.match(r'\s+(by|without)\s*\(([^)]*)\)', after, re.IGNORECASE)
            if m2:
                clause = m2.group(1).lower()
                labels = {l.strip() for l in m2.group(2).split(',') if l.strip()}
                return clause, labels

    # No clause found
    return None, set()


def is_inside_label_list(expr, pos):
    """
    Check if position `pos` is inside a by(...) or without(...) label list.
    Walk backwards from pos to find an unmatched '(' and check if it's
    preceded by 'by' or 'without'.
    """
    depth = 0
    for i in range(pos - 1, -1, -1):
        if expr[i] == ')':
            depth += 1
        elif expr[i] == '(':
            if depth == 0:
                # Found unmatched open paren — check what precedes it
                before = expr[:i].rstrip()
                if re.search(r'\b(by|without)\s*$', before, re.IGNORECASE):
                    return True
                return False
            depth -= 1
    return False


def check_absent(expr, is_thanos=False):
    """Check absent() and absent_over_time() calls for common problems."""
    problems = []

    for m in ABSENT_RE.finditer(expr):
        is_over_time = bool(m.group(1))
        func_name = "absent_over_time" if is_over_time else "absent"

        # Check 3: absent_over_time is almost always a mistake
        if is_over_time:
            problems.append(f"absent_over_time() used — likely does not behave as intended")

        # Extract inner expression
        open_idx = m.end() - 1
        close_idx = find_matching_paren(expr, open_idx)
        inner = expr[open_idx + 1:close_idx] if close_idx >= 0 else expr[open_idx + 1:]

        matchers = LABEL_MATCHER_RE.findall(inner)  # list of (label, op) tuples

        # Check 1: regex matchers won't propagate to the alert
        if any(op in ('=~', '!~') for _, op in matchers):
            problems.append(f"{func_name}() uses regex matcher — label will not propagate to alert")

        exact_labels = {label for label, op in matchers if op == '='}

        # Check 2: at least one routing label must be an exact matcher
        if not (REQUIRED_LABELS & exact_labels):
            problems.append(
                f"{func_name}() has no exact routing label "
                f"(need one of: {', '.join(sorted(REQUIRED_LABELS))})"
            )

        # Check 2b: thanos rules also need k8s_env or env as an exact matcher
        if is_thanos and not (THANOS_ENV_LABELS & exact_labels):
            problems.append(
                f"{func_name}() missing env label for thanos-rule "
                f"(need one of: {', '.join(sorted(THANOS_ENV_LABELS))})"
            )

    return problems


def check_expr(expr, is_thanos=False):
    """Return list of problems found in a PromQL expression."""
    problems = []

    for m in AGG_RE.finditer(expr):
        op = m.group(1).lower()

        # Skip if this word is actually a label name inside by()/without()
        if is_inside_label_list(expr, m.start()):
            continue

        clause, labels = extract_clause(expr, m.end())

        if clause is None:
            problems.append(f"{op}() has no by/without — all labels dropped")
        elif clause == "by":
            if not (REQUIRED_LABELS & labels):
                problems.append(f"{op} by() missing all of: {', '.join(sorted(REQUIRED_LABELS))}")
            if is_thanos and not (THANOS_ENV_LABELS & labels):
                problems.append(
                    f"{op} by() missing env label for thanos-rule "
                    f"(need one of: {', '.join(sorted(THANOS_ENV_LABELS))})"
                )
        elif clause == "without":
            remaining = REQUIRED_LABELS - labels
            if not remaining:
                problems.append(f"{op} without() drops all of: {', '.join(sorted(REQUIRED_LABELS))}")
            if is_thanos and not (THANOS_ENV_LABELS - labels):
                problems.append(
                    f"{op} without() drops env label for thanos-rule "
                    f"(need one of: {', '.join(sorted(THANOS_ENV_LABELS))})"
                )

    problems += check_absent(expr, is_thanos=is_thanos)
    return problems


def main():
    data = json.load(sys.stdin)
    items = data.get("items", [])
    findings = []

    for item in items:
        ns = item.get("metadata", {}).get("namespace", "")
        name = item.get("metadata", {}).get("name", "")

        if ns == "prometheus-system":
            continue

        labels = item.get("metadata", {}).get("labels", {})
        is_thanos = labels.get("role") == "thanos-rule"

        for group in item.get("spec", {}).get("groups", []):
            group_name = group.get("name", "")

            for rule in group.get("rules", []):
                rule_name = rule.get("alert") or rule.get("record") or "unnamed"
                expr = rule.get("expr", "")

                problems = check_expr(expr, is_thanos=is_thanos)
                for p in problems:
                    findings.append({
                        "namespace": ns,
                        "prometheusrule": name,
                        "group": group_name,
                        "rule": rule_name,
                        "expr": expr,
                        "problem": p,
                    })

    if not findings:
        print("All expressions preserve required labels.")
    else:
        json.dump(findings, sys.stdout, indent=2)
        print()  # trailing newline
        print(f"\n{len(findings)} issue(s) found.", file=sys.stderr)

    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()