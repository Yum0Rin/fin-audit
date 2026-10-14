"""fin-audit 单元测试。

用 pytest 运行：``pytest -q``（或 ``python -m pytest``）。
共 12 项，覆盖 6 类规则的判定逻辑与端到端流程。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from fin_audit import AuditEngine, load_config, write_csv, write_html
from fin_audit import rules

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG = ROOT / "examples" / "example.json"


class Ctx:
    """给规则函数用的最小上下文。"""

    def __init__(self, source: pd.DataFrame, target: pd.DataFrame):
        self.source = source
        self.target = target
        self.tables = {"source": source, "target": target}

    def table(self, name):
        return self.tables[name]

    def _col_sum(self, df, col):
        return float(pd.to_numeric(df[col], errors="coerce").dropna().sum())

    def total(self, token, default_table):
        if token is None:
            return None
        text = str(token).strip()
        try:
            return float(text)
        except ValueError:
            pass
        if "." in text:
            tbl, col = text.split(".", 1)
            if tbl in self.tables:
                return self._col_sum(self.tables[tbl], col)
        return self._col_sum(self.tables[default_table], token)


# --------------------------------------------------------------------------- #
# 规则 1：记录数核对
# --------------------------------------------------------------------------- #

def test_record_count_detects_mismatch():
    ctx = Ctx(pd.DataFrame({"id": [1, 2]}), pd.DataFrame({"id": [1]}))
    res = rules.rule_record_count(ctx, {"name": "记录数"})
    assert res.passed is False
    assert res.diff_count == 1
    assert res.differences[0].source_value == 2


def test_record_count_passes_when_equal():
    ctx = Ctx(pd.DataFrame({"id": [1, 2]}), pd.DataFrame({"id": [3, 4]}))
    res = rules.rule_record_count(ctx, {})
    assert res.passed is True
    assert res.diff_count == 0


# --------------------------------------------------------------------------- #
# 规则 2：主键唯一
# --------------------------------------------------------------------------- #

def test_key_unique_detects_duplicate():
    df = pd.DataFrame({"id": ["A1", "A1", "A2"]})
    res = rules.rule_key_unique(Ctx(df, df), {"table": "source", "key": ["id"]})
    assert res.passed is False
    assert res.diff_count == 1
    assert res.differences[0].key == "A1"


def test_key_unique_passes_when_unique():
    df = pd.DataFrame({"id": ["A1", "A2", "A3"]})
    res = rules.rule_key_unique(Ctx(df, df), {"table": "source", "key": ["id"]})
    assert res.passed is True


# --------------------------------------------------------------------------- #
# 规则 3：非空
# --------------------------------------------------------------------------- #

def test_not_null_detects_blank():
    df = pd.DataFrame({"id": ["A1", "A2"], "name": ["张三", ""]})
    res = rules.rule_not_null(ctx=Ctx(df, df),
                              rule={"table": "target", "key": ["id"], "fields": ["name"]})
    assert res.passed is False
    assert res.diff_count == 1
    assert res.differences[0].key == "A2"


# --------------------------------------------------------------------------- #
# 规则 4：值域
# --------------------------------------------------------------------------- #

def test_value_range_allowed_set():
    df = pd.DataFrame({"id": ["A1", "A2"], "status": ["正常", "关注"]})
    rule = {"table": "target", "field": "status", "allowed": ["正常", "冻结"], "key": ["id"]}
    res = rules.rule_value_range(Ctx(df, df), rule)
    assert res.passed is False
    assert res.diff_count == 1
    assert res.differences[0].source_value == "关注"


def test_value_range_min_max():
    df = pd.DataFrame({"id": ["A1", "A2"], "amount": [10.0, 999.0]})
    rule = {"table": "source", "field": "amount", "min": 0, "max": 100, "key": ["id"]}
    res = rules.rule_value_range(Ctx(df, df), rule)
    assert res.passed is False
    assert res.diff_count == 1
    assert res.differences[0].key == "A2"


# --------------------------------------------------------------------------- #
# 规则 5：金额勾稽
# --------------------------------------------------------------------------- #

def test_reconcile_row_detects_imbalance():
    df = pd.DataFrame({
        "id": ["A1", "A2"],
        "ending": [13000.0, 12000.0],
        "begin_": [10000.0, 12000.0],
        "income": [5000.0, 2000.0],
        "expense": [2000.0, 1000.0],
    })
    rule = {"scope": "row", "table": "target", "key": ["id"],
            "expr": "ending = begin_ + income - expense", "tol": 0.01}
    res = rules.rule_reconcile(Ctx(df, df), rule)
    assert res.passed is False
    assert res.diff_count == 1
    assert res.differences[0].key == "A2"


def test_reconcile_total_mismatch():
    df = pd.DataFrame({"debit": [100.0, 50.0], "credit": [100.0, 40.0]})
    rule = {"scope": "total", "table": "source", "lhs": "debit", "rhs": "credit"}
    res = rules.rule_reconcile(Ctx(df, df), rule)
    assert res.passed is False
    assert res.diff_count == 1
    assert res.differences[0].key == "__合计__"


# --------------------------------------------------------------------------- #
# 规则 6：字段差异
# --------------------------------------------------------------------------- #

def test_field_diff_detects_value_and_missing_key():
    src = pd.DataFrame({"id": ["A1", "A2", "A3"], "name": ["张三", "李四", "王五"]})
    tgt = pd.DataFrame({"id": ["A1", "A2"], "name": ["张三", "李四四"]})
    rule = {"key": ["id"], "fields": ["name"]}
    res = rules.rule_field_diff(Ctx(src, tgt), rule)
    assert res.passed is False
    # A2 字段不一致 + A3 仅源表存在
    assert res.diff_count == 2
    keys = {d.key: d for d in res.differences}
    assert keys["A2"].source_value == "李四"
    assert keys["A2"].target_value == "李四四"
    assert keys["A3"].message.startswith("该记录仅在源表存在")


# --------------------------------------------------------------------------- #
# 端到端
# --------------------------------------------------------------------------- #

def test_engine_example_end_to_end(monkeypatch):
    monkeypatch.chdir(ROOT)
    result = AuditEngine(load_config(str(EXAMPLE_CONFIG))).run()
    assert result.source_rows == 9
    assert result.target_rows == 7
    assert len(result.rule_results) == 7          # 6 类规则，7 个实例
    assert result.passed_rules == 1               # 值域-币种 通过
    assert result.failed_rules == 6
    assert result.total_diff == 9


def test_reports_are_written(tmp_path):
    result = AuditEngine(load_config(str(EXAMPLE_CONFIG))).run()
    html_file = tmp_path / "report.html"
    csv_file = tmp_path / "diff.csv"
    write_html(result, html_file)
    write_csv(result, csv_file)
    assert html_file.exists() and "金融数据稽核报告" in html_file.read_text(encoding="utf-8")
    lines = csv_file.read_text(encoding="utf-8-sig").strip().splitlines()
    assert len(lines) == 10                       # 表头 + 9 条差异
