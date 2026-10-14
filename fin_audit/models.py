"""审计结果的数据模型。

所有规则统一返回 :class:`RuleResult`，其中每条差异用 :class:`Difference` 表示，
再由 :class:`AuditResult` 汇总。模型层不依赖 pandas，方便被脚本直接 import 使用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List


def _cell(value: Any) -> Any:
    """把 None / NaN 统一成空字符串，便于写入 CSV 与 HTML。"""
    if value is None:
        return ""
    try:
        # pandas 的 NaN 自身不等于自己
        if value != value:  # noqa: PLR0124
            return ""
    except Exception:  # pragma: no cover - 极少数不可比较对象
        pass
    return value


@dataclass
class Difference:
    """一条差异记录（最终明细 CSV 里的一行）。"""

    rule: str                      # 规则名
    key: str = ""                  # 定位键（主键拼接）
    field: str = ""                # 涉及的字段
    source_value: Any = ""         # 源表取值
    target_value: Any = ""         # 目标表取值
    message: str = ""              # 人类可读说明

    def as_row(self, rule_type: str = "") -> dict:
        return {
            "规则名": self.rule,
            "规则类型": rule_type,
            "定位键": self.key,
            "字段": self.field,
            "源值": _cell(self.source_value),
            "目标值": _cell(self.target_value),
            "说明": self.message,
        }


@dataclass
class RuleResult:
    """单条规则的执行结果。"""

    name: str
    rule_type: str
    passed: bool
    differences: List[Difference] = field(default_factory=list)
    message: str = ""

    @property
    def diff_count(self) -> int:
        return len(self.differences)


@dataclass
class AuditResult:
    """一次完整审计的汇总结果。"""

    rule_results: List[RuleResult] = field(default_factory=list)
    source_rows: int = 0
    target_rows: int = 0
    source_path: str = ""
    target_path: str = ""
    config_path: str = ""

    @property
    def total_diff(self) -> int:
        return sum(r.diff_count for r in self.rule_results)

    @property
    def passed_rules(self) -> int:
        return sum(1 for r in self.rule_results if r.passed)

    @property
    def failed_rules(self) -> int:
        return sum(1 for r in self.rule_results if not r.passed)

    @property
    def passed(self) -> bool:
        """全部规则通过才为 True。"""
        return all(r.passed for r in self.rule_results)

    @property
    def all_differences(self) -> List[Difference]:
        rows: List[Difference] = []
        for r in self.rule_results:
            rows.extend(r.differences)
        return rows
