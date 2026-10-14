"""报告生成：HTML 汇总报告 + 明细 CSV。"""

from __future__ import annotations

import csv
import html
import datetime as _dt
from pathlib import Path

from .models import AuditResult

_CSV_HEADERS = ["规则名", "规则类型", "定位键", "字段", "源值", "目标值", "说明"]


def write_csv(result: AuditResult, path) -> str:
    """把全部差异写成明细 CSV（每条差异一行，UTF-8 BOM 便于 Excel 打开）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    type_of = {r.name: r.rule_type for r in result.rule_results}
    rows = []
    for diff in result.all_differences:
        rows.append(diff.as_row(type_of.get(diff.rule, "")))
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_HEADERS)
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def write_html(result: AuditResult, path, title: str = "金融数据稽核报告") -> str:
    """生成自包含的 HTML 汇总报告。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    passed = result.passed
    status_text = "全部通过" if passed else "存在差异"
    status_class = "ok" if passed else "bad"

    # 汇总行
    summary_rows = []
    for i, r in enumerate(result.rule_results, 1):
        badge = ('<span class="pill pass">通过</span>' if r.passed
                 else '<span class="pill fail">失败</span>')
        summary_rows.append(
            f"<tr><td>{i}</td><td>{_esc(r.name)}</td><td>{_esc(r.rule_type)}</td>"
            f"<td>{badge}</td><td class='num'>{r.diff_count}</td>"
            f"<td>{_esc(r.message)}</td></tr>"
        )
    summary_html = "\n".join(summary_rows)

    # 明细行
    detail_rows = []
    for diff in result.all_differences:
        detail_rows.append(
            "<tr>"
            f"<td>{_esc(diff.rule)}</td>"
            f"<td class='mono'>{_esc(diff.key)}</td>"
            f"<td>{_esc(diff.field)}</td>"
            f"<td class='mono'>{_esc(diff.source_value)}</td>"
            f"<td class='mono'>{_esc(diff.target_value)}</td>"
            f"<td>{_esc(diff.message)}</td>"
            "</tr>"
        )
    detail_html = "\n".join(detail_rows) or (
        "<tr><td colspan='6' class='empty'>未发现差异</td></tr>"
    )

    doc = _HTML_TEMPLATE.format(
        title=_esc(title),
        now=_esc(now),
        status_text=status_text,
        status_class=status_class,
        n_rules=len(result.rule_results),
        n_pass=result.passed_rules,
        n_fail=result.failed_rules,
        total=result.total_diff,
        source_rows=result.source_rows,
        target_rows=result.target_rows,
        source_path=_esc(result.source_path),
        target_path=_esc(result.target_path),
        summary_html=summary_html,
        detail_html=detail_html,
    )
    path.write_text(doc, encoding="utf-8")
    return str(path)


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #f4f6f9; color: #2b2b2b;
         font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif; }}
  .wrap {{ max-width: 1120px; margin: 0 auto; padding: 32px 24px 64px; }}
  header {{ border-bottom: 3px solid #2F4858; padding-bottom: 16px; margin-bottom: 24px; }}
  h1 {{ margin: 0 0 6px; font-size: 26px; color: #2F4858; }}
  .sub {{ color: #7a8794; font-size: 13px; }}
  .cards {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 20px 0 8px; }}
  .card {{ flex: 1 1 160px; background: #fff; border-radius: 10px; padding: 18px 20px;
           box-shadow: 0 1px 4px rgba(0,0,0,.06); border-top: 4px solid #2F4858; }}
  .card .label {{ font-size: 13px; color: #7a8794; }}
  .card .value {{ font-size: 30px; font-weight: 700; margin-top: 6px; color: #2F4858; }}
  .card.ok {{ border-top-color: #2e9e5b; }}
  .card.ok .value {{ color: #2e9e5b; }}
  .card.bad {{ border-top-color: #C03A2B; }}
  .card.bad .value {{ color: #C03A2B; }}
  .status {{ display: inline-block; padding: 4px 14px; border-radius: 999px;
             font-size: 13px; font-weight: 600; color: #fff; }}
  .status.ok {{ background: #2e9e5b; }}
  .status.bad {{ background: #C03A2B; }}
  h2 {{ font-size: 18px; color: #2F4858; margin: 32px 0 12px; }}
  .meta {{ font-size: 13px; color: #55636f; background:#fff; border-radius:10px;
           padding: 14px 18px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  .meta div {{ margin: 3px 0; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px;
           overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.06); font-size: 14px; }}
  th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #eef1f4; }}
  th {{ background: #2F4858; color: #fff; font-weight: 600; }}
  tr:last-child td {{ border-bottom: none; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.mono {{ font-family: Consolas, "Courier New", monospace; }}
  .pill {{ display: inline-block; padding: 2px 10px; border-radius: 999px;
           font-size: 12px; font-weight: 600; color: #fff; }}
  .pill.pass {{ background: #2e9e5b; }}
  .pill.fail {{ background: #C03A2B; }}
  .empty {{ text-align: center; color: #9aa6b2; padding: 24px; }}
  footer {{ margin-top: 28px; color: #9aa6b2; font-size: 12px; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{title}</h1>
    <div class="sub">fin-audit · 生成时间 {now} · <span class="status {status_class}">{status_text}</span></div>
  </header>

  <div class="cards">
    <div class="card"><div class="label">规则总数</div><div class="value">{n_rules}</div></div>
    <div class="card ok"><div class="label">通过</div><div class="value">{n_pass}</div></div>
    <div class="card bad"><div class="label">失败</div><div class="value">{n_fail}</div></div>
    <div class="card bad"><div class="label">差异总条数</div><div class="value">{total}</div></div>
  </div>

  <div class="meta">
    <div><b>源数据：</b>{source_path}（{source_rows} 行）</div>
    <div><b>目标/报送数据：</b>{target_path}（{target_rows} 行）</div>
  </div>

  <h2>一、规则执行汇总</h2>
  <table>
    <thead><tr><th>#</th><th>规则名</th><th>类型</th><th>结果</th><th>差异条数</th><th>说明</th></tr></thead>
    <tbody>
{summary_html}
    </tbody>
  </table>

  <h2>二、差异明细</h2>
  <table>
    <thead><tr><th>规则名</th><th>定位键</th><th>字段</th><th>源值</th><th>目标值</th><th>说明</th></tr></thead>
    <tbody>
{detail_html}
    </tbody>
  </table>

  <footer>由 fin-audit 自动生成 · 仅用于数据稽核演示</footer>
</div>
</body>
</html>
"""
