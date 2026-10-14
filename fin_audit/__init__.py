"""fin-audit · 金融数据稽核/对账工具。

面向金融数据治理 / 监管报送场景：按规则比对「源数据」与「目标/报送数据」，
自动定位差异并生成 HTML 汇总报告 + 明细 CSV。核心引擎可被脚本直接 import 调用。

示例::

    from fin_audit import AuditEngine, load_config

    result = AuditEngine(load_config("examples/example.json")).run()
    print(result.total_diff)
"""

from .engine import AuditConfig, AuditEngine, load_config
from .models import AuditResult, Difference, RuleResult
from .report import write_csv, write_html

__version__ = "0.1.0"

__all__ = [
    "AuditConfig",
    "AuditEngine",
    "load_config",
    "AuditResult",
    "RuleResult",
    "Difference",
    "write_csv",
    "write_html",
    "__version__",
]
