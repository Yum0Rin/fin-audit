"""六类内置稽核规则的实现。

规则全部以函数形式注册在 :data:`RULE_REGISTRY`，签名统一为
``fn(ctx, rule) -> RuleResult``：``ctx`` 提供两张表与表达式求值，``rule`` 是一条
JSON 规则配置。要新增规则，只需再写一个函数并注册进字典。
"""

from __future__ import annotations

import ast
import operator
from typing import Any, Dict, List, Optional

import pandas as pd

from .models import Difference, RuleResult

# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARYOPS = {ast.USub: operator.neg, ast.UAdd: operator.pos}


def as_list(value: Any) -> List[Any]:
    """把 ``None / 标量 / 列表`` 统一成列表。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def to_number(value: Any) -> Optional[float]:
    """尽力把值转成 float，失败返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            if value != value:  # NaN
                return None
        except Exception:  # pragma: no cover
            pass
        return float(value)
    text = str(value).strip().replace(",", "").replace("，", "")
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def is_blank(value: Any) -> bool:
    """判断是否为空（None / NaN / 空串 / 纯空白）。"""
    if value is None:
        return True
    if isinstance(value, float) and value != value:
        return True
    return str(value).strip() == ""


def key_of(row, keys: List[str]) -> str:
    """按主键字段拼出定位键字符串。"""
    if not keys:
        return ""
    return "|".join("" if is_blank(row.get(k)) else str(row.get(k)) for k in keys)


def values_equal(a: Any, b: Any, tol: float = 1e-9) -> bool:
    """比较两个单元格：能转数字就按数值（带容差）比，否则按字符串比。"""
    na, nb = to_number(a), to_number(b)
    if na is not None and nb is not None:
        return abs(na - nb) <= tol
    sa = "" if a is None else str(a).strip()
    sb = "" if b is None else str(b).strip()
    return sa == sb


def eval_arith(expr: str, row) -> Optional[float]:
    """安全地对一行数据求算术表达式（仅支持 + - * / 与括号、字段名、数字）。

    用 ``ast`` 白名单实现，不调用 ``eval``，因此不存在任意代码执行风险。
    """
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError:
        return None

    def _ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](_ev(node.left), _ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
            return _UNARYOPS[type(node.op)](_ev(node.operand))
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            number = to_number(row.get(node.id))
            if number is None:
                raise ValueError(f"字段 {node.id} 非数值")
            return number
        raise ValueError("不支持的表达式")

    try:
        return _ev(tree)
    except (ValueError, ZeroDivisionError):
        return None


def _rule_name(rule: Dict[str, Any], default: str) -> str:
    return str(rule.get("name") or default)


# --------------------------------------------------------------------------- #
# 规则 1：记录数核对
# --------------------------------------------------------------------------- #

def rule_record_count(ctx, rule) -> RuleResult:
    name = _rule_name(rule, "记录数核对")
    n_src, n_tgt = len(ctx.source), len(ctx.target)
    diffs: List[Difference] = []
    if n_src != n_tgt:
        diffs.append(
            Difference(
                rule=name,
                key="__汇总__",
                field="记录数",
                source_value=n_src,
                target_value=n_tgt,
                message=f"源表 {n_src} 行，目标表 {n_tgt} 行，相差 {abs(n_src - n_tgt)} 行",
            )
        )
    return RuleResult(
        name=name,
        rule_type="record_count",
        passed=not diffs,
        differences=diffs,
        message=f"源 {n_src} 行 / 目标 {n_tgt} 行",
    )


# --------------------------------------------------------------------------- #
# 规则 2：主键唯一
# --------------------------------------------------------------------------- #

def rule_key_unique(ctx, rule) -> RuleResult:
    name = _rule_name(rule, "主键唯一")
    df = ctx.table(rule.get("table", "source"))
    keys = as_list(rule.get("key"))
    if not keys:
        return RuleResult(name, "key_unique", False,
                          [Difference(name, "", "", "", "", "未配置主键字段 key")],
                          "缺少主键配置")

    counts: Dict[str, int] = {}
    for _, row in df.iterrows():
        k = key_of(row, keys)
        counts[k] = counts.get(k, 0) + 1

    diffs = [
        Difference(
            rule=name,
            key=k,
            field="|".join(keys),
            source_value=cnt,
            target_value=1,
            message=f"主键 {k} 在表中重复出现 {cnt} 次",
        )
        for k, cnt in counts.items()
        if cnt > 1
    ]
    return RuleResult(name, "key_unique", not diffs, diffs,
                      f"共 {len(counts)} 个唯一主键，重复 {len(diffs)} 个")


# --------------------------------------------------------------------------- #
# 规则 3：非空
# --------------------------------------------------------------------------- #

def rule_not_null(ctx, rule) -> RuleResult:
    name = _rule_name(rule, "非空校验")
    df = ctx.table(rule.get("table", "source"))
    fields = as_list(rule.get("fields"))
    keys = as_list(rule.get("key"))
    diffs: List[Difference] = []
    for _, row in df.iterrows():
        loc = key_of(row, keys) if keys else str(row.name)
        for field in fields:
            if is_blank(row.get(field)):
                diffs.append(
                    Difference(
                        rule=name,
                        key=loc,
                        field=field,
                        source_value=row.get(field),
                        target_value="",
                        message=f"字段 {field} 不能为空",
                    )
                )
    return RuleResult(name, "not_null", not diffs, diffs,
                      f"校验 {len(fields)} 个必填字段，空值 {len(diffs)} 个")


# --------------------------------------------------------------------------- #
# 规则 4：值域
# --------------------------------------------------------------------------- #

def rule_value_range(ctx, rule) -> RuleResult:
    name = _rule_name(rule, "值域校验")
    df = ctx.table(rule.get("table", "source"))
    field = rule.get("field")
    allowed = rule.get("allowed")
    low = rule.get("min")
    high = rule.get("max")
    keys = as_list(rule.get("key"))
    if not field:
        return RuleResult(name, "value_range", False,
                          [Difference(name, "", "", "", "", "未配置 field")], "缺少字段配置")

    describe = (f"允许集合 {allowed}" if allowed is not None
                else f"范围 [{low}, {high}]")
    diffs: List[Difference] = []
    for _, row in df.iterrows():
        value = row.get(field)
        ok = True
        if allowed is not None:
            ok = value in list(allowed)
        if ok and (low is not None or high is not None):
            number = to_number(value)
            if number is None:
                ok = False
            elif low is not None and number < float(low):
                ok = False
            elif high is not None and number > float(high):
                ok = False
        if not ok:
            diffs.append(
                Difference(
                    rule=name,
                    key=key_of(row, keys) if keys else str(row.name),
                    field=field,
                    source_value=value,
                    target_value=describe,
                    message=f"{field} 取值 “{value}” 不在 {describe}",
                )
            )
    return RuleResult(name, "value_range", not diffs, diffs,
                      f"{field} {describe}，越界 {len(diffs)} 条")


# --------------------------------------------------------------------------- #
# 规则 5：金额勾稽
# --------------------------------------------------------------------------- #

def rule_reconcile(ctx, rule) -> RuleResult:
    name = _rule_name(rule, "金额勾稽")
    scope = rule.get("scope", "row")
    tol = float(rule.get("tol", 0.01))
    keys = as_list(rule.get("key"))
    diffs: List[Difference] = []

    if scope == "row":
        df = ctx.table(rule.get("table", "target"))
        expr = str(rule.get("expr", ""))
        if "=" not in expr:
            return RuleResult(name, "reconcile", False,
                              [Difference(name, "", "", "", "", "row 模式需配置 expr，如 a = b + c")],
                              "缺少勾稽表达式")
        lhs_expr, rhs_expr = (s.strip() for s in expr.split("=", 1))
        for _, row in df.iterrows():
            left = eval_arith(lhs_expr, row)
            right = eval_arith(rhs_expr, row)
            if left is None or right is None:
                continue
            if abs(left - right) > tol:
                diffs.append(
                    Difference(
                        rule=name,
                        key=key_of(row, keys) if keys else str(row.name),
                        field=expr,
                        source_value=round(left, 2),
                        target_value=round(right, 2),
                        message=(f"勾稽不平：{lhs_expr}={round(left, 2)}，"
                                 f"{rhs_expr}={round(right, 2)}，差额 {round(left - right, 2)}"),
                    )
                )
        total_msg = f"逐行勾稽 {expr}，不平 {len(diffs)} 条"
    else:  # total：合计勾稽（如 借方合计 = 贷方合计 / 跨表合计核对）
        table = rule.get("table", "source")
        left = ctx.total(rule.get("lhs"), table)
        right = ctx.total(rule.get("rhs"), table)
        if left is None or right is None:
            return RuleResult(name, "reconcile", False,
                              [Difference(name, "", "", "", "", "合计勾稽的 lhs/rhs 无法解析")],
                              "合计勾稽配置有误")
        if abs(left - right) > tol:
            diffs.append(
                Difference(
                    rule=name,
                    key="__合计__",
                    field=f"{rule.get('lhs')} = {rule.get('rhs')}",
                    source_value=round(left, 2),
                    target_value=round(right, 2),
                    message=(f"合计勾稽不平：{rule.get('lhs')}={round(left, 2)}，"
                             f"{rule.get('rhs')}={round(right, 2)}，差额 {round(left - right, 2)}"),
                )
            )
        total_msg = f"合计勾稽 {rule.get('lhs')} = {rule.get('rhs')}"

    return RuleResult(name, "reconcile", not diffs, diffs, total_msg)


# --------------------------------------------------------------------------- #
# 规则 6：字段差异（逐行逐字段比对）
# --------------------------------------------------------------------------- #

def rule_field_diff(ctx, rule) -> RuleResult:
    name = _rule_name(rule, "字段差异")
    keys = as_list(rule.get("key"))
    fields = as_list(rule.get("fields"))

    def index(df):
        mapping: Dict[str, list] = {}
        for _, row in df.iterrows():
            mapping.setdefault(key_of(row, keys), []).append(row)
        return mapping

    src_map = index(ctx.source)
    tgt_map = index(ctx.target)

    if not fields:
        common = [c for c in ctx.source.columns if c in ctx.target.columns]
        fields = [c for c in common if c not in keys]

    diffs: List[Difference] = []
    for k in sorted(set(src_map) | set(tgt_map)):
        in_src, in_tgt = k in src_map, k in tgt_map
        if in_src and not in_tgt:
            diffs.append(Difference(name, k, "", "存在", "缺失",
                                    "该记录仅在源表存在（目标报送缺失）"))
        elif in_tgt and not in_src:
            diffs.append(Difference(name, k, "", "缺失", "存在",
                                    "该记录仅在目标表存在（源表中无对应记录）"))
        else:
            src_row, tgt_row = src_map[k][0], tgt_map[k][0]
            for field in fields:
                sv, tv = src_row.get(field), tgt_row.get(field)
                if not values_equal(sv, tv):
                    diffs.append(
                        Difference(name, k, field, sv, tv,
                                   f"字段 {field} 不一致")
                    )
    return RuleResult(name, "field_diff", not diffs, diffs,
                      f"比对主键 {keys} 下 {len(fields)} 个字段")


# --------------------------------------------------------------------------- #
# 注册表
# --------------------------------------------------------------------------- #

RULE_REGISTRY = {
    "record_count": rule_record_count,
    "key_unique": rule_key_unique,
    "not_null": rule_not_null,
    "value_range": rule_value_range,
    "reconcile": rule_reconcile,
    "field_diff": rule_field_diff,
}

RULE_LABELS = {
    "record_count": "记录数核对",
    "key_unique": "主键唯一",
    "not_null": "非空校验",
    "value_range": "值域校验",
    "reconcile": "金额勾稽",
    "field_diff": "字段差异",
}
