# 尺寸公差链分析（Worst Case / RSS / Monte Carlo）

面向机械质量团队的尺寸公差链应用：比较装配间隙的**最坏情况**与**统计分布**。

- **Angular 18**：展示闭合尺寸链、组成环方向/单位/分布、三种方法结果与主导尺寸追溯。
- **FastAPI + NumPy/SciPy**：极值法（解析）、均方根（解析矩）、蒙特卡洛（固定种子抽样）。
- **PostgreSQL**：保存尺寸链、尺寸来源、正负方向（+1/−1）、公差上下偏差与分布假设，以及每次分析运行。

## 目录

```
tolerance-chain/
├── backend/            FastAPI 应用
│   ├── app/
│   │   ├── tolerance.py   # 核心计算内核（纯函数，NumPy/SciPy）
│   │   ├── models.py      # SQLAlchemy 表：chains / rings / runs
│   │   ├── schemas.py     # 请求校验（方向、单边公差、sigma 等）
│   │   ├── seed.py        # 四个核对案例
│   │   └── main.py        # REST API
│   └── tests/             # 14 个内核用例 + 5 个 API 用例
└── frontend/           Angular 18（standalone 组件，无第三方图表库）
start-pg.sh           免 root 启动随仓 PostgreSQL（tools/pgsql16, 端口 5433）
```

## 启动

### 1. PostgreSQL

本环境使用的是从源码编译到 `tools/pgsql16` 的 PostgreSQL 16（免 root）：

```bash
./start-pg.sh
# => 127.0.0.1:5433, 用户/库 tolerance/tolerance_db, trust 认证
```

换用自有 PostgreSQL 时设置（SQLAlchemy URL）：

```bash
export TOLERANCE_DB="postgresql+psycopg2://user:pass@host:5432/dbname"
```

### 2. 后端

```bash
cd tolerance-chain/backend
python3 -m pip install -r requirements.txt
PYTHONPATH=. python3 -m uvicorn app.main:app --reload --port 8000
```

首次启动自动建表并写入四个演示尺寸链。API 文档：<http://localhost:8000/docs>。

### 3. 前端

```bash
cd tolerance-chain/frontend
npm install
npx ng serve            # http://localhost:4200 （/api 代理到 :8000）
npx ng build            # 生产构建到 dist/tolerance-ui
```

## 计算规则（为什么不是“公差绝对值直接相加”）

封闭环 `G = Σ direction_i · (nominal_i + dev_i)`，`direction ∈ {+1 增环, −1 减环}`。

| 方法 | 结果 | 前提 |
|---|---|---|
| **极值法 WC** | 保证界限 `gap_min/gap_max`（100% 互换） | 各组成环**同时**达到最不利极限；不需要分布 |
| **RSS** | 封闭环均值 μ、标准差 σ、±kσ 区间 | 各环相互独立、过程受控、**分布已显式给出**；不是保证界限 |
| **蒙特卡洛** | 经验分布、p05/p50/p95、干涉比例、各环方差份额 | 按各环**显式声明**的分布抽样；固定种子可复现；假设错误结果即错误 |

关键约束（代码中强制，不满足返回 422 而不是静默给数）：

1. **闭合性与方向**：链中必须同时存在增环和减环；每个环带符号参与叠加。
2. **单位检查**：长度族（mm/µm/cm/m/in/mil）与角度族（rad/mrad/deg）不能混入同一条链；
   环单位先换算到封闭环单位再计算。
3. **单边公差不按对称范围处理**：如 50H8 的 `+0.039/0`，半宽虽是 0.0195，但中点是
   0.0195 —— 统计法把均值移动计入 μ，分布只能用 `halfnormal`（需显式 σ），
   不能套成对称正态。
4. **未知分布不自动设正态**：`distribution=unknown` 时极值法照常，RSS/MC 明确报错。
5. **零公差基准**：极值法贡献为 0；统计法退化为位于公称值的常数，不需要分布。
6. 无界分布（正态/半正态）的蒙特卡洛样本允许少量超出极值界限，结果里会标注数量；
   有界分布（uniform/triangular）样本必须全部落在解析极值内（测试断言为 0 超出）。

## 核对案例（`backend/app/seed.py`，可在界面直接选）

| code | 场景 | 解析核对 |
|---|---|---|
| `shaft_hole_50H8f7` | 轴孔配合 50H8/f7（孔单边正公差 + halfnormal；轴 normal） | 极值 **[0.025, 0.089] mm**，中心 0.057，恒为间隙；朴素绝对值和 0.089 不是“间隙” |
| `thermal_growth` | 热膨胀简化线性项 ΔL=α·L·ΔT（铝/钢，ΔT=60°C），mm 与 µm 混合输入 | 公称 0.2028，极值 **[0.1598, 0.3108] mm**；全三角分布 MC 0 样本越界 |
| `zero_datum_stack` | 零公差基准隔块 | 极值 **[0, 0.15] mm**；基准环份额 0，MC 中为零公差常数 |
| `unknown_dist` | 供应商无过程数据 | 极值可用；RSS/MC 被拒绝并说明“不自动套用正态” |

测试包含解析极值手算、固定种子复现（同种子逐位相等、异种子不同）、RSS 解析矩与
大样本 MC 互核（均匀分布 σ=全宽/√12）、单位换算、方向/量纲/闭合/单边拒绝等。

```bash
cd backend && PYTHONPATH=. python3 -m pytest -q          # 19 passed
cd frontend && node e2e-smoke.cjs                        # 需先 ng serve + 后端
```

## 主导尺寸追溯

- 极值法：`dominance_share = 半宽_i / Σ半宽`。
- RSS：`variance_share = σ_i² / Σσ_j²`（单边公差的均值移动另计入 μ）。
- 蒙特卡洛：`Cov(x_i, gap)/Var(gap)`（样本协方差份额），界面以条形展示。

## 免责

固定种子抽样与解析结果仅用于设计阶段核对模型与方案比较；
**本工具不替代制造验收**、首件检验或按图纸/标准进行的合格判定（该声明随每次分析返回）。
