# Claude Cloud AC Sizing / SLD 执行指引（2026-07-28）

状态：**当前可执行基线的交接文件。**

本文给云端 Claude（以及后续维护者）使用。目标不是重新设计 DC
Sizing，而是在已验证的统一 AC Sizing 主线上继续工作，且不得恢复此前造成
AC 过配和 SLD 失真的“双分支”实现。

## 1. 本次基线已经完成了什么

当前工作树包含下列已实现、已本地验证的成果：

1. **统一的新 AC 流程**：`DC grouping -> PCS architecture -> transformer
   topology -> physical feeder check -> optional product binding -> SLD/layout/report`。
   新 AC run 没有旧的 `Governed Product` / `standard product preset` 开关或第二
   套 sizing engine。
2. **通用分组**：支持 `1:1`、`1:2`、`1:4`、`1:8`。分组数量为
   `ceil(DC block total / ratio denominator)`；DC 分配必须均衡，不能为了套用
   产品而人工制造 `8/4/2/1` 尾组。
3. **PCS 选择不是产品锁定**：正常产品对比优先显示 `2 x 2,500 kW = 5 MW`；
   用户选 `1:8` 时，额外显示 `8 x 1,250 kW = 10 MW` 的 small-PCS
   组合。两者都只是可选 PCS 架构，用户仍可选其他有效组合，亦可完全不绑定
   产品。
4. **物理馈线校验**：每个 DC Block 默认有两个受保护 PCS 输出。一个 AC
   Block 至少需要 `ceil(PCS count / DC Block output circuits)` 个 DC Block。
   因此 8 PCS 至少需要 4 个 DC Block；该限制检查的是连接可行性，不是新的
   sizing 公式。
5. **SLD 三绕组修复**：三绕组必须有两个独立 LV winding，且 vector group
   必须明确给出两个 LV token（例如 `Dy11y11`）。`y`、`yn`、`z`、`zn`
   只决定绕组符号；它们**不**是接地设计资料，渲染普通 Y，不得凭空画接地条。
6. **SLD 真实运行边界**：Guest 生成的是会话预览/下载，不能注册 Artifact
   Registry 或写正式工件。正式/严格 SLD 仍要求登录、工程设置和可追溯 run。
7. **产品目录已接通但保持可选**：本地数据库导入后有 18 条
   `ProductACBlock`，数据版本是 `vendor_datasheet_2026-07-24`。匹配仅按用户
   已选的 PCS 数量、单台 kW 和（若声明）变压器拓扑过滤；产品只可补充已确认的
   nameplate / LV voltage / cooling / vector-group 资料。

本基线曾执行：

```powershell
python -m compileall -q app.py calb_sizing_tool calb_diagrams
python -m pytest tests -q
```

2026-07-27 的历史验证结果为 **477 passed**。本次交接新增跨模块守门测试后，
2026-07-28 的当前 checkout 已重新验证：**481 tests collected，完整测试命令成功**。
后续提交仍必须重新执行同一套命令并以新结果为准。

## 2. 云端 Claude 的最小阅读顺序

只阅读与任务有关的区域；不要全仓扫描。顺序如下：

1. `docs/CURRENT_STATUS_2026-07-12.md`：模块边界和历史兼容约束。
2. `docs/AC_SIZING_UNIFIED_FLOW_V2_2026-07-27.md`：新 AC 主线的业务合同。
3. 本文：现状、待办和验收方法。
4. 若改 SLD，再读 `docs/DIAGRAM_QUALITY_GOVERNANCE_2026-07-15.md`、
   `calb_sizing_tool/sld/transformer_vector_group.py`、
   `calb_diagrams/sld_engineering_v2_renderer.py` 的相关函数及对应测试。
5. 若改 AC 页面，再读 `calb_sizing_tool/ui/ac_view.py`、
   `calb_sizing_tool/services/ac_sizing_service.py`、
   `calb_sizing_tool/services/ac_block_product_match.py` 及本文列出的测试。

涉及域：AC sizing orchestration、AC-to-SLD contract、SLD renderer、产品匹配、
UI、报告。**不涉及且不得随手修改** DC sizing 公式、SOH/RTE、`K_MAX_FIXED`
或 Stage 1/2/3 语义。

## 3. 不可退回的业务合同

### 3.1 一条新 run 主线

```text
DC sizing result + POI power/energy
  -> user chooses generic DC:AC grouping
  -> user chooses PCS count and per-PCS kW
  -> user explicitly chooses two- or three-winding topology
  -> validate smallest grouping against DC protected-output capacity
  -> optionally match/bind a product record
  -> persist one AC output
  -> SLD, layout and report read that one output
```

以下做法是错误的，禁止重新引入：

- 旧 checkbox 触发第二套 governed sizing / POI 计算；
- `1:8` 自动等同于某个 10 MW 或 8-DC 标准产品；
- 先选 catalogue product，再反向改变 grouping、PCS 数量、PCS kW 或 AC Block 数；
- 对非 8 的整除尾组硬凑产品类别或虚增 DC / AC 容量；
- 因 PCS 大于两个就自动把变压器改成三绕组；
- 因 vector group 中出现 `n`、`y` 或 `yn` 就在 SLD 画中性点接地或接地条。

### 3.2 202 DC 的可复现例子

`202 DC Blocks` 在 `1:8` 下必须为 26 个 AC Blocks，均衡分配为：

```text
20 groups x 8 DC + 6 groups x 7 DC = 202 DC
```

不是 `8/4/2/1` 的产品尾组模型。若用户选 8 x 1,250 kW：

```text
required DC Blocks per AC Block = ceil(8 PCS / 2 protected outputs) = 4
```

上述 7/8-DC 尾组都可连接；仅有 3 DC Block 的 1:8 分组则必须阻止 8 PCS
选择，并给出清晰的物理连接错误。`2 x 2,500 kW` 只需要一个 DC Block，
但其可行不意味着系统应当选择它；PCS 及 POI 约束仍由正常 sizing/feasibility
流程决定。

### 3.3 产品数据的正确处理

产品种子不是 Git checkout 后自动存在于每个 SQLite 数据库中。云端或新的本地
数据库需要在管理员界面执行：

```text
Product & Database -> AC Blocks -> Import preset vendor catalogue
```

导入后的检查项：

- 表格不应再显示 `No columns to display`；
- 至少应能看到 Sineng `SINENG-EH-10000-HB-UD-10-33` 与 Kehua
  `KEHUA-BCS10000K-C-HUD-T8`；
- 缺失的产品 engineering field 必须显示 `partial` / `TBD`，不能伪造
  transformer MVA、Uk%、vector group、接地资料或 layout 尺寸；
- 不导入产品目录时，通用 AC sizing 仍必须工作，只是无可绑定产品。

## 4. SLD 真值合同

| 情况 | 正确输出 | 必须拒绝或降级的情况 |
| --- | --- | --- |
| 两绕组，1 个 LV bus | 例如 `Dyn11`，一个 LV token | 两绕组却给两个 LV token，或缺 vector group |
| 三绕组，2 个独立 LV bus | 例如 `Dy11y11` / `Dy11-y11`，两个 LV token，各自独立 LV section | 用 `Dyn11` 复制成两路 LV；没有 operator topology confirmation |
| LV `y` / `yn` / `z` / `zn` | 普通绕组符号，不画 ground bar | 以 vector group 推断接地设计 |
| strict/formal | 真实设置、拓扑与 vector group 必须一致 | 冲突或缺值时拒绝发正式图 |
| draft/Guest | 可显示 `TBD`，必须保留 draft watermark | Guest 写 Artifact Registry、伪称正式发图 |

对于准确齐套的 `1:8 + 8 x 1,250 kW + three-winding`，可以使用
`central_40ft_bilateral_4plus4` 的概念布置条件：中央竖向 40 ft AC station，
DC 为镜像 4+4。它是已选物理架构的 layout condition，不是产品或 sizing lock。
含尾组、其他 PCS 架构或两绕组时必须回到通用布局。

## 5. 当前问题、优先级与云端工作边界

### P0：发布前必须保持为绿

1. 不得让旧 governed checkbox、10MW/8DC 强制头组或 `8/4/2/1` 尾组重返新 run。
2. 所有变压器 vector/topology 不一致必须在 strict 模式拒绝，draft 模式只能
   `TBD`，不能“看起来像已确认”。
3. 真实 SVG 几何仍需检验；Python topology test 绿不等于画图正确。任何 SLD
   改动需要跑相关渲染测试并查看 SVG/PNG。

### P1：下一轮应优先补的真实验收

1. 在一个新、持久化的管理员数据库执行产品导入，并覆盖登录正式 run 的产品绑定。
   当前已经覆盖 Guest 会话不注册工件；这不等于正式流已人工验收。
2. 在有 Playwright 的云端环境运行 `scripts/smoke_app_ac_sizing.py`，至少检查：
   四个 grouping button、无旧开关、`1:8` 的 8 x 1,250 kW 候选可见、普通候选仍可选。
3. 生成并人工查看两个 Engineering V2 SLD：
   - two-winding / `Dyn11`；
   - three-winding / `Dy11y11`、8 PCS、两个独立 LV distribution sections、无
     LV earth bar。

### P2：需要业务决定，不能擅自改公式

1. POI power overhead 的提示/阻止阈值是否改成完整的“最小 ACS/PCS 组合优化”
   问题，尚未获得新的业务授权。当前实现的职责是暴露并校验问题，不得为消除
   过配而偷偷改 DC quantities、SOH/RTE、duration 或 efficiency。
2. 产品 datasheet 中仍有未确认字段时，只能以 `TBD` / `partial` 保留。需要
   OEM 资料后才能写入正式 catalogue。
3. 92 DC 的 Guest 端到端演示已通过；含 7-DC tail 的 202-DC 正式登录版仍应做
   人工 SLD/layout/report 联测，尤其确认不把典型 8-DC 图误称为整个项目的唯一
   物理布置。

## 6. 机器可执行验收

本次新增的 `tests/integration/test_claude_ac_sizing_handoff.py` 是云端任务的
最小跨模块守门测试。它同时确认：

1. 202 DC / 1:8 是均衡 20 x 8 + 6 x 7；
2. 8 x 1,250 kW 只是 1:8 可选候选，5 MW 2 x 2,500 kW 仍可用；
3. 8 PCS 在双输出 DC Block 模型下需要至少 4 DC Blocks；
4. catalogue preference 仅为 UI preference；
5. 三绕组要求两个 LV vector token，不能从单个 `Dyn11` 猜两路 LV；
6. AC UI 没有旧的产品 preset sizing branch。

先运行目标测试，再运行全量回归：

```powershell
python -m pytest tests/integration/test_claude_ac_sizing_handoff.py -q
python -m pytest tests/unit/test_ac_sizing_service.py `
  tests/unit/test_ac_block_product_match.py `
  tests/unit/test_transformer_vector_group.py `
  tests/unit/test_sld_engineering_v2_renderer.py `
  tests/integration/test_sld_session_preview.py -q
python -m compileall -q app.py calb_sizing_tool calb_diagrams
python -m pytest tests -q
```

视觉验收不是可选项。若改了 renderer/SLD contract，还要执行已有的 SVG regression
路径并查看输出；不得以“单元测试全部通过”替代图纸检查。

## 7. Claude 修改时的提交清单

每个变更完成前按以下顺序自检：

1. 声明所改域；若职责跨域移动，同步更新
   `docs/CURRENT_STATUS_2026-07-12.md` 的 module map。
2. 不修改 frozen DC sizing modules；先检查 `git diff --name-only`。
3. 所有影响上述合同的改动必须同时更新本文件、
   `AC_SIZING_UNIFIED_FLOW_V2_2026-07-27.md` 和相应测试，不能只改 UI 文案。
4. 运行第 6 节命令；涉及 UI/SLD 时补充真实浏览器或 SVG/PNG 证据。
5. `git diff --check` 后只 stage 本任务文件，不对混合工作树做 `reset --hard`、
   `checkout --` 或 `git add -A`。
6. 在提交说明中明确写：本次是否影响 grouping、PCS、topology、product binding、
   SLD、layout、report，以及是否触及 frozen sizing core。

## 8. 历史文件的正确用途

`CLAUDE_HANDOFF_10MW_8PCS_8DC_2026-07-24.md` 与
`GOVERNED_AC_BLOCK_10MW_8PCS_8DC_2026-07-24.md` 保留为历史、产品和布局背景。
它们不能覆盖本文及 `AC_SIZING_UNIFIED_FLOW_V2_2026-07-27.md` 的新 run 规则。
特别是“governed configuration”“fixed 8 DC head”“产品优先于 sizing”的旧语义，
只可用于读取历史持久化记录，不能再用于生成新 AC run。
