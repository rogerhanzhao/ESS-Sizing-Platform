# AC 升级为独立 Run —— 设计方案（**第 1 步已实施 2026-08-04**）

**Owner 裁决 B（2026-08-04）**：

> "AC 可以尝试升级到独立 RUN，但是可能与前面的 CASE 可能重复，不能过度的细分；
> 如果逻辑可以理清楚，可以升级成独立的 AC RUN"

**结论先说**：逻辑理得清楚，**不会与 Case 重复**，但**会有过度细分的风险**，
需要一条明确的去重规则来挡住。

**当前状态**：第 1 步（schema + 记录 + 去重 + 页面接入）**已实施**；
第 2 步（下游 artifact 改址）和第 3 步（UI 切换器）**未做** —— 见 §四。

---

## 一、为什么不会与 Case 重复

关键在于**两者装的是不同的东西**：

| | 装什么 | 数据来源 |
|---|---|---|
| `SizingCase.input_json` | `SizingCaseInput` —— **纯 DC 侧输入**（POI 功率/能量、寿命、DoD、RTE、各段效率、scenario） | DC Sizing 表单 |
| AC 配置 | PCS 台数、PCS 单机功率、1:4 / 1:8 配比、变压器拓扑（两绕组/三绕组）、LV 母线形式、绑定的产品 | AC Sizing 表单 |

**Case 里一个 AC 字段都没有。** 所以 "AC Run" 不是 Case 的再分，而是
**"在这份 DC 结果之上，选了哪一套 AC 方案"** —— 是 DC Run 的**子级**。

层级变成：

```
Project
 └─ Case            方案 x scenario（DC 侧假设）
     └─ DC Run      一次 DC 计算（不可变）
         └─ AC Run  一套 AC 配置（不可变）        ← 新增
             └─ artifacts: SLD / Layout / Report
```

---

## 二、怎么防止"过度细分"

这是这个方案唯一的真风险：AC 页面每点一次就多一个 Run，历史被噪声淹没。

**规则：AC Run 按内容哈希去重。**

1. AC 配置序列化后算 `content_hash`（沿用 `run_output_snapshot.content_hash` 的做法）。
2. 建 AC Run 前，先查**同一个 DC Run 下**有没有相同 `content_hash` 的 AC Run：
   - **有** → 复用那一行，只更新 `finished_at`，**不新建**；
   - **没有** → 新建。
3. 效果：反复点"重算"而参数没变 → 永远只有一行；真的换了 1:4 / 1:8 → 两行并存，
   可以对比。**行数 = 真正试过的方案数**，不是点击次数。

这条规则不需要 owner 再做判断，它是可验证的：
`test_recomputing_the_same_configuration_reuses_its_run`
与 `test_bookkeeping_noise_does_not_mint_an_alternative`。

---

## 三、需要改什么（工作量与风险）

| 项 | 内容 | 风险 |
|---|---|---|
| Schema | `sizing_run` 增 `parent_run_id`（自引用 FK，`ondelete=CASCADE`）+ migration | 低 |
| 持久化 | 新增 `persist_ac_run()`；`run_type="ac_sizing"`；输入/输出各一份快照 | 低 |
| **改址** | SLD / Layout / Report 的 artifact 现在挂在 **DC Run** 上，要改挂 **AC Run** | **高** —— 全链约 23 种 artifact 的 `run_id` 语义变了 |
| 兼容 | 已有数据的 artifact 还挂在 DC Run 上，读取要同时支持"本级"和"父级" | 中 |
| 访问控制 | `AccessControlService` 要能从 AC Run 追溯到 project | 低 |
| UI | 第三级仍列 DC Run，旁边给 AC 方案切换器 | 中 —— owner 已定 B |

**最大的一处是"改址"**：现在 `run_id` 在整条链路里是唯一坐标，
报告、SLD、布局、外部提交全用它。改成两级坐标后，
每一个 `load_artifact_bytes_from_db(run_id, ...)` 都要想清楚取哪一级。

---

## 四、实施顺序（三次提交，每次都能单独回滚）

### ✅ 第 1 步 —— 已完成（2026-08-04）

- `sizing_run.parent_run_id`（自引用 FK，`ondelete=CASCADE`），migration `20260804_0009`；
- `services/ac_run_service.py`：`persist_ac_run()` / `list_ac_alternatives()` /
  `ac_configuration_hash()`；
- **去重规则已落地**：身份哈希只覆盖 17 个真正决定方案的字段
  （PCS 数/单机功率、变压器容量与拓扑、LV 绕组数、**dc_allocation_plan**、
  产品名/配置代号、并网与 LV 电压等）。时间戳、UI 标记之类**不改变身份**。
- AC 页面已接入，且**故意 fail-soft**：配置本身由
  `persist_ac_runtime_snapshot` 保存（SLD 和报告读的是它），
  AC Run 只是台账 —— **台账写失败绝不能让用户丢掉保存**。
- 回归锁 `tests/unit/test_ac_run_service.py`（16 条），包括
  "Case 里确实没有任何 AC 字段" 这条**被验证而非假设**的前提。

**下游未动**：SLD / Layout / Report 的 artifact 仍挂 DC Run。

### 第 2 步 —— 改址（未做）

SLD / Layout / Report 改为挂 AC Run，读取加"本级找不到就找父级"的兼容。
这是三步里最大的一步，约 23 种 artifact 的 `run_id` 语义都要重新判断。

### 第 3 步 —— UI（未做）

按 owner 裁决走 **B**：workbench 第三级仍列 DC Run，选中后旁边给一个
AC 方案切换器（不算第四级）。`list_ac_alternatives()` 已经按这个形状返回数据。

---

## 五、UI 形态 —— owner 已定 B（2026-08-04）

workbench 第三级仍列 DC Run，AC 方案作为"同一次 DC 计算下的分支"横向切换，
不增加第四级下拉。`list_ac_alternatives(dc_run_id)` 已按这个形状返回。

## 五之二、增长控制（owner 同期要求）

> "运行的日志和数据库不能无限制的变大"

AC Run 的去重规则本身就是增长控制的一部分：**行数 = 真正试过的方案数**。
另有一整套保留策略见 `services/maintenance_service.py` 与
`docs/CURRENT_STATUS_2026-07-12.md` §4.1b。第 2 步改址时要注意：
artifact 改挂 AC Run 后，**每个 AC 方案会有自己的一套图**，
`CALB_ARTIFACT_GENERATIONS`（每条 lineage 只留最新一代）依然生效，
但方案数本身成为新的增长维度 —— 去重规则是唯一的闸门，不要放宽它。

---

## 六、第 1 步之后仍然成立的限制

- **AC 方案已经能并存并被记录**，但 SLD / Layout / Report 的 artifact
  **仍然挂在 DC Run 上**。所以现在切换 AC 方案**不会**自动给你第二套图纸和
  第二版报告 —— 那是第 2 步。
- `sld_data_source_service` 读 AC 快照仍用
  `get_latest_output_snapshot_by_kind`，即"最后保存的那套 AC"。
  第 2 步要把它改成"按选中的 AC Run 取"。

这两条已写进 `docs/CURRENT_STATUS_2026-07-12.md` §4.1b，避免被当成 bug 反复发现。
