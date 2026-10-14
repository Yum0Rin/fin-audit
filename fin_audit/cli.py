"""命令行入口：``python -m fin_audit --config <config.json>``。"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .engine import AuditEngine, load_config
from .report import write_csv, write_html


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fin-audit",
        description="金融数据稽核/对账工具：按规则比对源数据与报送数据，输出差异报告。",
    )
    parser.add_argument("-c", "--config", required=True, help="JSON 规则配置文件路径")
    parser.add_argument("--html", help="覆盖配置里的 HTML 报告输出路径")
    parser.add_argument("--csv", help="覆盖配置里的明细 CSV 输出路径")
    parser.add_argument(
        "--strict", action="store_true",
        help="存在差异时以非零退出码结束（便于接入 CI 门禁）",
    )
    parser.add_argument("--version", action="version", version=f"fin-audit {__version__}")
    return parser


def run(config_path: str, html_path=None, csv_path=None, strict: bool = False) -> int:
    config = load_config(config_path)
    result = AuditEngine(config).run()

    html_out = html_path or config.html_report
    csv_out = csv_path or config.csv_report
    if html_out:
        write_html(result, config.resolve(html_out))
    if csv_out:
        write_csv(result, config.resolve(csv_out))

    # -- 控制台汇总 ------------------------------------------------------ #
    print("=" * 66)
    print(f"  fin-audit 稽核报告  ·  {config_path}")
    print("=" * 66)
    print(f"  源数据  : {result.source_path}  ({result.source_rows} 行)")
    print(f"  目标数据: {result.target_path}  ({result.target_rows} 行)")
    print("-" * 66)
    print(f"  {'规则名':<20}{'结果':<6}{'差异条数':>8}   说明")
    print("-" * 66)
    for r in result.rule_results:
        status = "通过" if r.passed else "失败"
        print(f"  {r.name:<20}{status:<6}{r.diff_count:>8}   {r.message}")
    print("-" * 66)
    print(f"  规则 {len(result.rule_results)} 条 · 通过 {result.passed_rules} · "
          f"失败 {result.failed_rules} · 差异合计 {result.total_diff} 条")
    if html_out:
        print(f"  HTML 报告: {config.resolve(html_out)}")
    if csv_out:
        print(f"  明细 CSV : {config.resolve(csv_out)}")
    print("=" * 66)

    if strict and not result.passed:
        return 1
    return 0


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return run(args.config, args.html, args.csv, args.strict)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
