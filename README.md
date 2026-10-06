# 尺寸公差链分析应用（Angular + FastAPI + NumPy/SciPy + PostgreSQL）

比较**装配间隙**在三种方法下的结果，并强制把三者的前提讲清楚：

| 方法 | 回答的问题 | 前提 |
|---|---|---|
| 最坏极值 WC | 100% 互换时封闭环的保证包络 `[X0_min, X0_max]` | 所有组成环同时取最不利极限；**不需要任何分布假设**，未知分布、单边公差都能参与 |
| 均方根 RSS | 独立随机变量下封闭环的均值与 σ，报告均值 ± kσ | 各环**显式登记**分布、相互独立、线性传递；封闭环近似正态时 ±3σ 才有分位数含义 |
| 蒙特卡洛 MC | 固定种子的封闭环经验分布与分位数 | 按各环登记分布独立抽样；样本极值**不是**保证，只用于核对解析极值与观察分布形状 |

## 应用刻意执行的工程纪律

1. **不把 Σ|Tᵢ| 当最终间隙**。Σ|Tᵢ| 只是封闭环公差带宽度；最终间隙是带方向的区间
   `[X0_min, X0_max]`，名义值 X0 由各环方向叠加决定。结果中带专门提示文案。
2. **方向必须显式声明**。每个组成环有 `direction = +1（增环）/ −1（减环）`，
   封闭环有正方向定义（如 `G = 孔径 − 轴径；G>0 间隙，G<0 过盈`）。
   可登记 `expected_closing_nominal`，后端会做名义残差核对并对方向错误告警；
   区间跨越 0（既可能间隙也可能过盈）时也会告警。
3. **单位必须核对**。每环可登记 mm / µm / inch，计算前全部换算到尺寸链基准单位，
   混合单位会产生显式的换算记录与告警，禁止跨单位直接相加。
4. **未知分布绝不自动设正态**。`distribution_kind=unknown` 的环只参与极值法；
   RSS/MC 整体阻断并返回明确原因。新建环的默认值就是 `unknown`（前端下拉默认“未知”）。
5. **单边公差不做对称化**。`[0, +T]` 不会被折叠成名义值两侧 ±T/2：
   - uniform/triangular：在真实非对称区间上取矩/抽样，均值平移如实进入 RSS 与 MC；
   - normal：按**带中点截断正态**建模（均值 m=(l+u)/2、σ=带宽/(2k)、带内截断），
     这是显式假设，结果中给出假设说明，并要求在 `distribution_params.basis` 写依据；
     后端不会在用户没选正态时替他选。
6. **零公差基准**用 `deterministic` 环表示：不贡献带宽/方差/相关性，抽样恒等于名义值。
7. **热膨胀**只做一阶线性项 ΔL=α·L·ΔT，温度区间支持单边（其一为 0），
   冷缩用负 ΔT 表达而不是改方向；明确声明不含约束应力、温度梯度与材料非线性。
8. **可追溯主导环**：极值法按各环带宽占比、RSS 按方差占比、
   MC 按各环与封闭环的 Spearman 等级相关（符号携带增/减环方向）排序。
9. **模型不替代制造验收**：所有结果附带免责声明；MC 给出的“验收区间内比例”明确标注
   仅为设计阶段估计，不是合格判定；首件检验、SPC、量具能力与按图纸验收不被取代。

## 内置核对案例（`POST /api/demo/seed`）

1. **轴孔配合 φ50 H7/g6**：孔 `50(+0.025/0)`（增环）、轴 `50(−0.009/−0.025)`（减环）。
   解析极值 G ∈ **[0.009, 0.050] mm**，带宽 0.041。固定种子 20260601 的 10 万次 MC
   与解析极值逐样本核对（0 越界），并与 RSS 矩交叉核对。
2. **热膨胀（单边温升）**：冷态间隙 `0.50(+0.04/−0.02)`，钢件 α=12e-6、L=500、
   ΔT=40 且实际 40~50°C（单边 [0,+10]，均匀）。极值 [0.18, 0.30] mm，
   非对称区间导致均值平移 −0.02 mm（错误对称化会得到 0）。
3. **零公差基准**：`G = B0 − L1 − L2`，B0=60 零公差，L1 ±0.03、L2 ±0.05。
   解析极值 [−0.08, +0.08]，基准环贡献占比 0，主导环为 L2。

## 目录

```
backend/    FastAPI + SQLAlchemy 2 + NumPy/SciPy（计算内核 app/tolerance.py 无框架依赖）
tolchain-frontend/  Angular 18 standalone（signals）：闭合链 SVG 示意图 + 三法对比直方图
docker-compose.yml  PostgreSQL 16 + API（JSONB 保存分布假设等结构化字段）
```

## 本地运行（PostgreSQL）

```bash
docker compose up --build
# API: http://localhost:8000/docs
# 写入演示案例:
curl -X POST http://localhost:8000/api/demo/seed

cd tolchain-frontend
npm install
npm start          # http://localhost:4200 ，/api 已配置代理到 8000
```

## 本地无 Docker 时（SQLite，仅用于开发/CI）

```bash
cd backend
python3 -m venv --without-pip .venv && .venv/bin/python get-pip.py   # 需要时引导 pip
.venv/bin/pip install -r requirements.txt pytest httpx
TC_DATABASE_URL="sqlite:///./dev.db" .venv/bin/uvicorn app.main:app --reload
```

> 生产目标方言是 PostgreSQL：分布参数、计算留痕使用 **JSONB**；
> SQLite 下退化为通用 JSON，功能行为一致（测试即跑在 SQLite 上）。

## 测试

```bash
cd backend
.venv/bin/python -m pytest tests/ -q
# 18 passed：解析极值手算、固定种子复现/换种子不同、越界核对、
# 未知分布阻断、单边正态均值不被对称化、零公差贡献为0、
# 混合单位换算、方向核对、热膨胀线性项、HTTP 留痕
```

## 主要 API

- `POST /api/demo/seed` 写入三个演示案例
- `GET/POST/DELETE /api/chains[/{id}]`，`POST /api/chains/{id}/dimensions`
- `POST /api/chains/{id}/analyze` body `{"n_samples": 100000, "seed": 20260601}`
  （两者均可空：默认 10 万样本、服务端固定种子）
- `GET /api/chains/{id}/runs` 计算留痕（方法/种子/样本数/结果摘录）
- `POST /api/utils/thermal-expansion-term` 由 α/L/ΔT 生成可入库的组成环

## 数值方法备注

- MC 使用 `numpy.random.default_rng(seed)`：固定种子逐位复现；正态环用
  `scipy.stats.truncnorm` 在公差带内截断，三角分布用 `scipy.stats.triang`。
- k=3 截断会使正态环实际 σ 约为未截断值的 0.973 倍，因此 RSS（解析未截断矩）
  对正态环略保守，MC 展示真实截断矩，两者差异在 `cross_check` 中量化展示。
- 本工具仅做**线性化**尺寸链（传递比 ±1），不处理非线性机构、形位公差与相关尺寸。
