# fin-audit · 金融数据稽核/对账工具

> 面向**金融数据治理 / 监管报送**场景的轻量级数据稽核工具：按规则比对「源数据」与
> 「目标/报送数据」，自动定位差异，一键产出 **HTML 汇总报告 + 明细 CSV**。
> 纯 Python，数据层用 pandas，核心审计引擎可被脚本直接 `import`。

---

## 一、这个项目解决什么问题（痛点）

金融机构在做数据治理、监管报送（如 EAST、1104、反洗钱口径核对）时，每天都要确认
**「源系统账务明细」和「报送出去的报表数据」是否一致**。传统做法是人工开 Excel、
VLOOKUP 拽半天，问题在于：

- **易漏**：行数差了几条、某个字段被清洗错、某个账户状态改错了，肉眼很难发现；
- **不可复现**：每次口径不同，昨天的核对逻辑明天没人记得；
- **不落痕**：查出来哪里不一样，却没法留一份能交给复核人的报告。

`fin-audit` 把这套核对**规则化、可配置、可复现**：写一份 JSON 规则，跑一条命令，
几秒内得到「哪条规则没过、差了几条、具体哪一行哪个字段、源值多少、目标值多少」，
并生成可截图、可归档的 HTML 报告。

---

## 二、功能

- **6 类内置稽核规则**（可自由组合、可加多条实例）：

  | # | 规则类型 | `type` | 作用 |
  |---|----------|--------|------|
  | ① | 记录数核对 | `record_count` | 比对源表与目标表行数是否一致 |
  | ② | 主键唯一 | `key_unique` | 检查指定表的主键是否重复 |
  | ③ | 非空 | `not_null` | 检查必填字段是否为空 |
  | ④ | 值域 | `value_range` | 取值须落在允许集合内，或在 [min, max] 范围内 |
  | ⑤ | 金额勾稽 | `reconcile` | 逐行勾稽（如 期末 = 期初 + 收入 − 支出）或合计勾稽（如 借方合计 = 贷方合计） |
  | ⑥ | 字段差异 | `field_diff` | 按主键逐行逐字段比对源表与目标表，列出不一致的字段与值，并标出「仅源表 / 仅目标表」存在的记录 |

- **JSON 配置驱动**：表/文件路径、主键、字段、规则参数全部写在 JSON 里。
- **两种报告**：HTML 汇总报告（各规则通过/失败、差异条数、总览卡片）+ 明细 CSV
  （每条差异一行：规则名、定位键、字段、源值、目标值、说明）。
- **CLI + GUI 双形态**：核心是 `fin_audit.engine`（可 import 的独立模块），CLI 与
  tkinter GUI 都只是薄壳。

---

## 三、安装

```bash
pip install -r requirements.txt
```

依赖：`pandas>=2.0`（测试另需 `pytest>=7.0`）。也可作为包安装：

```bash
pip install -e .
```

---

## 四、快速开始

仓库自带一份**故意埋了差异**的示例数据（`examples/source.csv` 9 行、
`examples/target.csv` 7 行）与规则配置（`examples/example.json`）。在项目根目录执行：

```bash
python -m fin_audit --config examples/example.json
```

示例输出：

```
==================================================================
  fin-audit 稽核报告  ·  examples/example.json
==================================================================
  源数据  : examples\source.csv  (9 行)
  目标数据: examples\target.csv  (7 行)
------------------------------------------------------------------
  规则名                 结果        差异条数   说明
------------------------------------------------------------------
  记录数核对               失败           1   源 9 行 / 目标 7 行
  主键唯一                失败           1   共 8 个唯一主键，重复 1 个
  非空校验                失败           1   校验 3 个必填字段，空值 1 个
  值域-币种               通过           0   currency 允许集合 ['CNY', 'USD', 'HKD']，越界 0 条
  值域-账户状态             失败           1   status 允许集合 ['正常', '冻结', '销户']，越界 1 条
  金额勾稽-期末余额           失败           1   逐行勾稽 ending_balance = beginning_balance + income - expense，不平 1 条
  字段差异比对              失败           4   比对主键 ['acct_no'] 下 3 个字段
------------------------------------------------------------------
  规则 7 条 · 通过 1 · 失败 6 · 差异合计 9 条
  HTML 报告: demo\report.html
  明细 CSV : demo\diff_detail.csv
==================================================================
```

跑完后：

- `demo/report.html` —— 用浏览器打开即可看的汇总报告；
- `demo/diff_detail.csv` —— 9 条差异的明细，可直接交给复核人。

> 加了 `--strict` 时，只要存在差异就以非零退出码结束，方便接入 CI 做数据门禁。

### 作为库调用（脚本里 import）

```python
from fin_audit import AuditEngine, load_config, write_html, write_csv

config = load_config("examples/example.json")
result = AuditEngine(config).run()

print("差异合计:", result.total_diff)          # 9
print("失败规则:", result.failed_rules)        # 6
write_html(result, "demo/report.html")
write_csv(result, "demo/diff_detail.csv")
```

### 图形界面（薄壳）

```bash
python -m fin_audit.gui
```

选配置 → 运行稽核 → 看汇总 → 打开 HTML 报告。

---

## 五、规则配置说明

配置文件是一个 JSON，示例（`examples/example.json`）：

```json
{
  "source": "source.csv",
  "target": "target.csv",
  "report": { "html": "../demo/report.html", "csv": "../demo/diff_detail.csv" },
  "rules": [
    { "type": "record_count", "name": "记录数核对" },
    { "type": "key_unique", "name": "主键唯一", "table": "source", "key": ["acct_no"] },
    { "type": "not_null", "name": "非空校验", "table": "target", "key": ["acct_no"],
      "fields": ["acct_no", "cust_name", "ending_balance"] },
    { "type": "value_range", "name": "值域-账户状态", "table": "target", "field": "status",
      "allowed": ["正常", "冻结", "销户"] },
    { "type": "reconcile", "name": "金额勾稽-期末余额", "scope": "row", "table": "target",
      "expr": "ending_balance = beginning_balance + income - expense", "tol": 0.01 },
    { "type": "field_diff", "name": "字段差异比对", "key": ["acct_no"],
      "fields": ["cust_name", "currency", "ending_balance"] }
  ]
}
```

字段说明：

| 字段 | 说明 |
|------|------|
| `source` / `target` | 源数据、目标/报送数据的 CSV 路径（相对**配置文件所在目录**） |
| `report.html` / `report.csv` | 报告输出路径；也可用命令行 `--html` / `--csv` 覆盖 |
| `rules[].type` | 规则类型，取值见上表六个 `type` |
| `rules[].name` | 规则显示名（报告里展示，可自定义） |
| `rules[].table` | 规则作用表：`source` 或 `target` |
| `rules[].key` | 主键字段（数组），用于定位差异所在行；`key_unique` 必填 |
| `rules[].fields` | 参与校验的字段数组（`not_null` / `field_diff`） |
| `rules[].field` | 单个字段（`value_range`） |
| `rules[].allowed` / `min` / `max` | 值域规则：允许集合，或数值上下限 |
| `rules[].scope` | 勾稽范围：`row`（逐行）或 `total`（合计） |
| `rules[].expr` | 逐行勾稽表达式，如 `a = b + c`（仅 + − × ÷ 与字段名、数字） |
| `rules[].lhs` / `rhs` | 合计勾稽两侧，可为列名、`表名.列名` 或常量 |
| `rules[].tol` | 金额比较容差（默认 `0.01`） |

---

## 六、目录结构

```
fin-audit/
├─ fin_audit/                 # 核心包
│  ├─ __init__.py             # 对外导出 AuditEngine / load_config / ...
│  ├─ __main__.py             # python -m fin_audit 入口
│  ├─ models.py               # Difference / RuleResult / AuditResult 数据模型
│  ├─ data.py                 # 数据加载与数值型推断（pandas）
│  ├─ rules.py                # 6 类规则实现 + 规则注册表
│  ├─ engine.py               # 审计引擎：加载配置 → 执行规则 → 汇总
│  ├─ report.py               # HTML 汇总报告 + 明细 CSV
│  ├─ cli.py                  # 命令行入口
│  └─ gui.py                  # tkinter GUI 薄壳
├─ examples/                  # 示例数据与规则配置
│  ├─ source.csv              # 源数据（9 行，含重复主键）
│  ├─ target.csv              # 目标/报送数据（7 行，含多处差异）
│  └─ example.json            # 规则配置
├─ tests/
│  └─ test_fin_audit.py       # 12 项单元测试
├─ demo/                      # 演示产物（跑示例生成）
│  ├─ report.html             # HTML 报告
│  ├─ report.png              # 报告截图
│  ├─ diff_detail.csv         # 差异明细
│  └─ demo.md                 # 演示说明
├─ conftest.py                # 让 pytest 能 import 到本包
├─ pyproject.toml             # 打包与 fin-audit 命令入口
├─ requirements.txt
├─ LICENSE                    # MIT
└─ README.md
```

---

## 七、运行测试

```bash
python -m pytest -q
```

覆盖 6 类规则的判定逻辑与端到端流程，共 **12 项，全部通过**：

```
12 passed
```

---

## 八、License

[MIT](LICENSE) · 作者 Yum0Rin
