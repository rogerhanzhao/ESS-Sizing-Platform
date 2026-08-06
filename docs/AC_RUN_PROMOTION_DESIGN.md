# AC 升级为独立 Run —— 设计方案（**第 1 步已实施 2026-08-04**）

**Owner 裁决 B（2026-08-04）**：

> "AC 可以尝试升级到独立 RUN，但是可能与前面的 CASE 可能重复，不能过度的细分；
> 如果逻辑可以理清楚，可以升级成独立的 AC RUN"

**结论先说**：逻辑理得清楚，**不会与 Case 重复**，但**会有过度细分的风险**，
需要一条明确的去重规则来挡住。

**当前状态**：第 1、2、3 步**均已实施**（2026-08-04），
第 4 步"报告分版本"**已实施**（2026-08-06）。见 §四。

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

### ✅ 第 2 步 —— 改址（已完成 2026-08-04）

**核心是"祖先回退"，不是逐个改址。** `load_artifact_bytes_from_db` 沿
`parent_run_id` 向上走，**就近优先**：

- 方案自己的图**永远赢**；
- 方案没生成过的那一种，**自动回退到 DC Run 的**；
- **老库完全不用迁移** —— 图本来就都在 DC Run 上，照常读得到。

写入端：`run_sld_pipeline_from_run_bundle` / `render_sld_from_run_bundle` /
`render_layout_from_run_bundle` 各加一个 `artifact_run_id=None` 参数，
**默认 None 即落在 DC Run**，所有既有调用行为不变。

`site_constraint_set` **故意没有改址**：场地约束是地块边界/进场/退界，
属于项目与 DC Run 层面，**不随 AC 方案变**。

页面侧只认一个 helper `workspace_state.artifact_run_id()`
（选中方案 → 否则 DC Run），SLD / 排布 / 报告三页都调它 ——
**这个判断只能有一处**，各页各写一份正是排布那条缺陷链的成因。

`set_active_run()` 切换 DC Run 时会**清掉方案选择**：
一个 AC 方案只属于一个 DC Run，带过去就会指向别人的分支。

### ✅ 第 3 步 —— UI（已完成 2026-08-04）

按 owner 裁决 **C/B**：workbench 第三级仍列 DC Run，
下面多一个 **AC 方案横向切换器**（不是第四级下拉）。
**只有当该 DC Run 下确实有 ≥2 个方案时才出现** —— 一个方案是常态，
不需要控件，下游本来就会解析到它。

### ✅ 第 4 步 —— 报告分版本（已完成 2026-08-06）

第 2、3 步之后图纸已经跟着方案走，但**两版报告的文件名还是同一个**，
第二次导出会**静默覆盖**第一次 —— 裁决 B 里"最终报告可以重新生成一个版本"
这半句其实还没落地。

**命名规则：`ac_alternative_label(dc_run_id, ac_run_id)` → `A` / `B` / …**

- **按最早优先排序**：先试的那个永远是 A。后来的方案**不会给已经发出去的
  报告改名** —— 报告可复现是硬要求。
- `list_child_runs` 的排序补了 `sizing_run_id` 作为次序键：
  同一时钟刻度内建的两个 Run 若只按 `started_at` 排，两次调用可能互换位置，
  等于给方案改名。
- **只有 ≥2 个方案时才返回标签**，否则返回 `None`。一个方案是常态，
  它跟谁都不用区分；给它贴标签会把**所有**普通报告的文件名都改掉。

标签落到三处：文件名 `..._V2.1_AC-B.docx`、封面 `AC Alternative: B`、
Document Provenance 表（连同 AC Run 号，用于追溯图纸来自哪个分支）。

回归锁 `tests/unit/test_report_ac_alternative_versioning.py`（10 条），
**正反两个方向都锁**：两个方案必须导出两个文件；
一个方案必须与历史文件名逐字一致、正文不出现任何方案措辞。

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

## 六、四步之后仍然成立的限制

前三条已经解决（方案能并存、图纸跟着方案走、报告分版本），**还剩一条**：

- `sld_data_source_service.load_persisted_ac_snapshot` 读 AC 运行态快照仍用
  `get_latest_output_snapshot_by_kind(dc_run_id, …)`，即"**最后保存的那套 AC**"，
  不是"选中的那个方案的那套 AC"。
  **影响面**：已经生成的图纸和报告不受影响 —— 它们是 artifact，按方案取
  （第 2 步）。受影响的是**重新生成**：在方案 A 上点重算 SLD，
  取到的输入可能是最后保存的方案 B 的配置。
  **要改的是**：`persist_ac_runtime_snapshot` 落到 AC Run 上，
  读取端同样走 `parent_run_id` 祖先回退（与 artifact 一致，老库不用迁移）。

这条已写进 `docs/CURRENT_STATUS_2026-07-12.md` §4.1b，避免被当成 bug 反复发现。
