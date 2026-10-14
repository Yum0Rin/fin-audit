"""审计引擎：加载配置、执行规则、汇总结果。

引擎是纯逻辑层，可被脚本直接 ``import`` 调用，GUI / CLI 都只是外层壳：

    from fin_audit import AuditEngine, load_config

    config = load_config("examples/example.json")
    result = AuditEngine(config).run()
    print(result.total_diff)

若缺少 pandas，会自动退回标准库 ``csv`` 实现（接口一致）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import AuditResult, RuleResult
from .rules import RULE_REGISTRY


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #

@dataclass
class AuditConfig:
    source: str
    target: str
    rules: List[Dict[str, Any]] = field(default_factory=list)
    html_report: Optional[str] = None
    csv_report: Optional[str] = None
    base_dir: str = "."

    def resolve(self, path: Optional[str]) -> Optional[str]:
        """相对路径以「配置文件所在目录」为基准，找不到再退回当前工作目录。"""
        if not path:
            return None
        p = Path(path)
        if p.is_absolute():
            return os.path.normpath(str(p))
        base = Path(self.base_dir) / path
        if base.exists():
            return os.path.normpath(str(base))
        if p.exists():
            return os.path.normpath(str(p))
        # 输出文件通常尚不存在：默认落在配置文件所在目录的对应位置
        return os.path.normpath(str(base))


def load_config(path: str) -> AuditConfig:
    """读取 JSON 规则配置。"""
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    report = data.get("report") or {}
    return AuditConfig(
        source=data.get("source", ""),
        target=data.get("target", ""),
        rules=data.get("rules", []),
        html_report=report.get("html"),
        csv_report=report.get("csv"),
        base_dir=str(cfg_path.parent),
    )


# --------------------------------------------------------------------------- #
# 规则执行上下文
# --------------------------------------------------------------------------- #

class _Context:
    """给规则函数提供两张表、取表、合计与表达式求值能力。"""

    def __init__(self, source, target):
        self.source = source
        self.target = target
        self.tables = {"source": source, "target": target}

    def table(self, name: str):
        if name not in self.tables:
            raise KeyError(f"未知表名: {name}（可选 source / target）")
        return self.tables[name]

    def _col_sum(self, df, col: str) -> Optional[float]:
        if col not in df.columns:
            return None
        try:
            import pandas as pd
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            return float(series.sum())
        except ImportError:
            total = 0.0
            for _, row in df.iterrows():
                total += row.get(col)
            return total

    def total(self, token, default_table: str) -> Optional[float]:
        """解析合计项：数字常量 / ``表名.列名`` / 当前表的列名。"""
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
        return self._col_sum(self.table(default_table), text)


# --------------------------------------------------------------------------- #
# 引擎
# --------------------------------------------------------------------------- #

class AuditEngine:
    """按配置执行所有规则并返回汇总结果。"""

    def __init__(self, config: AuditConfig):
        self.config = config

    # -- 数据加载 ---------------------------------------------------------- #
    def _load(self):
        source_path = self.config.resolve(self.config.source)
        target_path = self.config.resolve(self.config.target)
        try:
            from .data import load_frames
            source, target = load_frames(source_path, target_path)
        except ImportError:  # pragma: no cover - 无 pandas 的兜底路径
            source = _read_csv_stdlib(source_path)
            target = _read_csv_stdlib(target_path)
        return source, target, source_path, target_path

    # -- 主流程 ------------------------------------------------------------ #
    def run(self) -> AuditResult:
        source, target, source_path, target_path = self._load()
        ctx = _Context(source, target)

        results: List[RuleResult] = []
        for rule in self.config.rules:
            rule_type = rule.get("type")
            fn = RULE_REGISTRY.get(rule_type)
            if fn is None:
                results.append(
                    RuleResult(
                        name=str(rule.get("name") or rule_type),
                        rule_type=str(rule_type),
                        passed=False,
                        message=f"未知规则类型: {rule_type}",
                    )
                )
                continue
            results.append(fn(ctx, rule))

        return AuditResult(
            rule_results=results,
            source_rows=len(source),
            target_rows=len(target),
            source_path=source_path,
            target_path=target_path,
            config_path=str(self.config.base_dir),
        )


# --------------------------------------------------------------------------- #
# 纯标准库兜底读取（仅当环境没有 pandas 时启用）
# --------------------------------------------------------------------------- #

class _Row(dict):
    """给 dict 补一个 ``name``，模拟 pandas Series 的索引访问。"""

    def __init__(self, data: Dict[str, Any], name: int):
        super().__init__(data)
        self.name = name


class _SimpleTable:
    """极简表对象，提供规则层用到的 columns / iterrows / len。"""

    def __init__(self, columns: List[str], rows: List[Dict[str, Any]]):
        self.columns = columns
        self._rows = rows

    def __len__(self) -> int:
        return len(self._rows)

    def iterrows(self):
        for i, row in enumerate(self._rows):
            yield i, _Row(row, i)


def _read_csv_stdlib(path: str) -> "_SimpleTable":
    import csv as _csv

    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = _csv.DictReader(fh)
        columns = [c.strip() for c in (reader.fieldnames or [])]
        rows = [{k: _try_num(v) for k, v in raw.items()} for raw in reader]
    return _SimpleTable(columns, rows)


def _try_num(value):
    text = (value or "").strip()
    if text == "":
        return None
    try:
        return float(text)
    except (ValueError, TypeError):
        return value
