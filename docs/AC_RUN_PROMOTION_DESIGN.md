# AC 升级为独立 Run —— 设计方案（待 owner 批准范围后实施）

**Owner 裁决 B（2026-08-04）**：

> "AC 可以尝试升级到独立 RUN，但是可能与前面的 CASE 可能重复，不能过度的细分；
> 如果逻辑可以理清楚，可以升级成独立的 AC RUN"

**结论先说**：逻辑理得清楚，**不会与 Case 重复**，但**会有过度细分的风险**，
需要一条明确的去重规则来挡住。方案如下，范围较大（含 migration + 下游全链改址），
**先请 owner 确认范围再动手**。

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
`test_ac_run_is_reused_when_the_configuration_is_unchanged`。

---

## 三、需要改什么（工作量与风险）

| 项 | 内容 | 风险 |
|---|---|---|
| Schema | `sizing_run` 增 `parent_run_id`（自引用 FK，`ondelete=CASCADE`）+ migration | 低 |
| 持久化 | 新增 `persist_ac_run()`；`run_type="ac_sizing"`；输入/输出各一份快照 | 低 |
| **改址** | SLD / Layout / Report 的 artifact 现在挂在 **DC Run** 上，要改挂 **AC Run** | **高** —— 全链约 23 种 artifact 的 `run_id` 语义变了 |
| 兼容 | 已有数据的 artifact 还挂在 DC Run 上，读取要同时支持"本级"和"父级" | 中 |
| 访问控制 | `AccessControlService` 要能从 AC Run 追溯到 project | 低 |
| UI | Workbench 第三级下拉从 "Run" 变成 "DC Run → AC Run" 两级，或在 Run 列表里分层显示 | 中 —— owner 说 workbench 保持三级下拉，**这里需要再确认** |

**最大的一处是"改址"**：现在 `run_id` 在整条链路里是唯一坐标，
报告、SLD、布局、外部提交全用它。改成两级坐标后，
每一个 `load_artifact_bytes_from_db(run_id, ...)` 都要想清楚取哪一级。

---

## 四、建议的实施顺序（可分三次提交，每次都能单独回滚）

1. **加 `parent_run_id` + `persist_ac_run()` + 去重规则**，但**下游不动**
   —— AC Run 先只作为记录存在，artifact 仍挂 DC Run。可测、零风险。
2. **改址**：SLD / Layout / Report 改为挂 AC Run，读取加"本级找不到就找父级"的兼容。
3. **UI**：Run 列表分层显示；决定 workbench 第三级怎么呈现。

---

## 五、需要 owner 再定的一件事

Workbench 现在是 **Project → Case → Run** 三级下拉，owner 说保持不变。
但 AC Run 落地后，第三级会同时存在 DC Run 和 AC Run 两类。两个选择：

- **A**：第三级只列 AC Run（因为报告/SLD 都挂它），DC Run 作为它的属性显示；
- **B**：第三级仍列 DC Run，选中后在旁边再给一个 AC 方案切换器（不算第四级下拉）。

**我倾向 B** —— 保持三级不变，AC 方案作为"同一次 DC 计算下的分支"横向切换，
更贴近"不要过度细分"的意图，也不改变用户已经熟悉的导航。

---

## 六、现状（未做此改造前）的已知限制

- AC 快照按 `add_output_snapshot` 追加，行会累积，但读取只用
  `get_latest_output_snapshot_by_kind`，**UI 无处查看或选回旧版本**；
- 同一份 DC 结果**无法**并存两套 AC 方案做对比，只能重跑 DC 建新 Run。

这两条已写进 `docs/CURRENT_STATUS_2026-07-12.md` §4.1b，避免被当成 bug 反复发现。
