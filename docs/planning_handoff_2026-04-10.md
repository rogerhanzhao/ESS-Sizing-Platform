# CALB Sizing Tool Planning Handoff

更新时间：2026-04-10

## 1. 目的

这份文档用于给后续规划直接提供上下文，供 ChatGPT 或后续开发者快速读取。  
它不是新的设计文档，而是把当前仓库状态、最近一轮已形成的讨论结论、以及尚未落地的事项整合到一个入口里。

## 2. 当前仓库快照

### 2.1 当前分支

- 当前分支：`ops/ubuntu-docker-coexist-20260311`
- 跟踪远端：`origin/ops/ubuntu-docker-coexist-20260311`

### 2.2 最近已提交内容

当前分支最近的已提交工作集中在运维与部署：

1. `8568af4` `2026-03-11` `ops: add maintenance timer and cleanup flow`
2. `36613db` `2026-03-11` `docs: clarify interactive deploy steps`
3. `fb6f850` `2026-03-11` `ops: add ubuntu docker coexist deployment`

结论：

- 如果只看 Git 已提交历史，项目最近推进点是 Ubuntu Docker 共存部署与维护流程。
- 这部分已经进入当前分支历史。

### 2.3 当前工作区未提交内容

工作区里还有一批未提交的新文件，主题已经切到“数据库化与主数据迁移准备”：

- `calb_sizing_tool/db/__init__.py`
- `calb_sizing_tool/db/dc_master_seed.py`
- `calb_sizing_tool/db/dc_master_importer.py`
- `deploy/sql/001_init_postgres.sql`
- `deploy/sql/002_master_data_publish_flow.sql`
- `deploy/sql/003_seed_dc_master_data_from_excel.sql`
- `docs/current_state_db_migration_prep.md`
- `docs/database_design_and_er.md`
- `docs/master_data_maintenance_api_prep.md`
- `docs/dc_master_import_runbook.md`
- `scripts/generate_dc_master_seed_sql.py`
- `scripts/import_dc_master_data_to_postgres.py`
- `tests/test_generate_dc_master_seed_sql.py`
- `tests/test_import_dc_master_data_to_postgres.py`

结论：

- 最近一轮“讨论内容”实际已经不是前端功能增强，而是数据库迁移路线、主数据治理、以及 Excel 到 PostgreSQL 的导入准备。
- 但这批内容目前仍是本地未提交状态，不能当作“已合并完成”的事实。

## 3. 当前系统事实结论

基于 [current_state_db_migration_prep.md](./current_state_db_migration_prep.md) 的梳理，当前系统仍然是一个以 `Streamlit` 为入口的单体选型工具，主流程为：

1. `DC Sizing`
2. `AC Sizing`
3. `Single Line Diagram`
4. `Site Layout`
5. `Report Export`

当前版本的核心事实：

- 没有数据库。
- 跨页面主链路主要依赖 `st.session_state`。
- 关键结果依赖临时跨页对象，如 `dc_result_summary`、`stage13_output`、`ac_output`。
- `SLD/Layout/Report` 都是从这些中间对象继续取字段。
- `DC` 和 `AC` 的核心可运行逻辑仍主要在页面层，尚未真正抽成稳定服务层。

这意味着当前系统更接近：

- 页面驱动
- 会话驱动
- 文件补充驱动

而不是：

- 项目驱动
- 持久化驱动
- 服务层驱动

## 4. 最近一轮讨论已经形成的共识

### 4.1 不要直接把 `session_state` 原样搬进数据库

这是最近讨论里最重要的结论。

如果直接把当前 UI 里的多份状态包照搬进库里，只会把当前的冗余、字段漂移、跨页耦合从内存复制到数据库，问题不会真正解决。

### 4.2 数据库版建议采用三层结构

来自 [database_design_and_er.md](./database_design_and_er.md) 的核心建模方向：

1. `Draft`
   - 保存用户编辑中的输入快照
   - 解决刷新后输入丢失
2. `Run`
   - 保存一次正式计算或生成动作的不可变结果
   - 解决结果可追溯
3. `State Pointer`
   - 保存当前项目“活跃工作态”指针
   - 解决恢复编辑现场的问题

### 4.3 主数据维护建议采用三层结构

来自 [master_data_maintenance_api_prep.md](./master_data_maintenance_api_prep.md) 的核心分层：

1. `Master`
   - 稳定业务对象
2. `Revision`
   - 每次编辑形成新版本
3. `Published Snapshot`
   - 提供给计算引擎使用的不可变快照

关键原则：

- 维护页面只改 `master / revision`
- 计算只读 `published snapshot`
- 发布动作是从可编辑数据进入计算数据的唯一入口

### 4.4 PostgreSQL 已被选为当前首选方向

设计文档当前是按 PostgreSQL 展开，主要原因是：

- 支持 `JSONB`
- 支持更强约束和外键
- 适合迁移初期“结构化字段 + 原始 payload 并存”

## 5. 已经准备到什么程度

### 5.1 文档层

这轮讨论已经形成 4 份关键文档：

- [current_state_db_migration_prep.md](./current_state_db_migration_prep.md)
- [database_design_and_er.md](./database_design_and_er.md)
- [master_data_maintenance_api_prep.md](./master_data_maintenance_api_prep.md)
- [dc_master_import_runbook.md](./dc_master_import_runbook.md)

文档已经覆盖：

- 当前系统真实数据流与风险
- PostgreSQL 方向下的 ER 和表分组
- 主数据维护与发布边界
- Excel 字典导入 PostgreSQL 的运行说明

### 5.2 数据库对象层

当前工作区已经预留了数据库对象与脚手架：

- PostgreSQL DDL 初稿
- 主数据发布流 SQL
- DC 主数据 seed SQL 生成脚本
- Excel 导 PostgreSQL 的导入脚本
- 对应 smoke tests

### 5.3 验证层

本地已验证通过的测试：

```powershell
pytest -q tests/test_generate_dc_master_seed_sql.py tests/test_import_dc_master_data_to_postgres.py
```

结果：

- `2 passed`

这说明至少以下两件事已经具备最小可运行性：

- 从当前 Excel 生成 DC 主数据 seed SQL
- 以 dry-run 方式构建并校验导入 payload

## 6. 还没有落地的部分

这是后续规划最需要分清楚的边界。

当前仍未实现或未接通的部分包括：

- 实际后端 API
- `repository / service` 层
- 从 `revision` 到 `published snapshot` 的正式服务事务
- DC 页面改为数据库读数
- 项目级持久化工作流
- 权限、审批、审计日志
- 图纸和报告与 `project_id / run_id / scenario_id` 的真实绑定

因此，当前不能把数据库化理解为“已经做完”，更准确的表述是：

- 数据模型和迁移方向已初步定稳
- 脚手架与导入准备已出现
- 业务主链路尚未真正切到数据库

## 7. 对后续规划最重要的判断

### 7.1 真正的第一优先级不是“接数据库”，而是“统一契约”

根据 [current_state_db_migration_prep.md](./current_state_db_migration_prep.md) 的结论，后续升级前最关键的是先处理三件事：

1. 定义统一领域模型，替代 `stage13_output`、`dc_result_summary`、`ac_output` 等跨页临时包
2. 把页面内计算逻辑逐步抽成服务层
3. 让图纸、报告、快照都绑定到明确的 `project_id + run_id + scenario_id`

如果不先做这三件事，数据库只能保存混乱状态，不能真正提升系统可维护性。

### 7.2 数据库化落地建议按阶段推进

根据 [database_design_and_er.md](./database_design_and_er.md) 的建议，当前更稳妥的推进方式是：

第一阶段：

- `projects`
- `project_stage_state`
- `project_stage_drafts`
- `dc_runs`
- `dc_scenarios`
- `dc_scenario_items`
- `dc_scenario_yearly_results`
- `ac_runs`
- `ac_blocks`
- `ac_feeders`

目标：

- 先解决输入不丢
- 先解决结果可追溯

第二阶段：

- `artifacts`
- `sld_runs`
- `layout_runs`
- `report_runs`

目标：

- 图纸与报告版本化

第三阶段：

- `dictionary_versions`
- 各类模板/曲线表
- 计算正式切换到数据库主数据

目标：

- 历史结果可复算

注意：当前工作区虽然已经开始写主数据 DDL 和导入脚本，但从“系统改造路径”角度看，真正合理的实施顺序仍然需要和 DTO/服务层收敛一起评估，不能只因为主数据脚手架先写了，就默认它必须最先落地到 UI。

## 8. 建议 ChatGPT 继续规划时优先回答的问题

为了让下一步规划更可执行，建议 ChatGPT 继续聚焦下面这些问题：

1. 在不破坏现有 Streamlit 可用性的前提下，第一批统一 DTO 应该怎么定义。
2. `DC -> AC -> SLD/Layout -> Report` 的最小稳定主键链路应该如何落表。
3. `dc_view.py` 和 `ac_view.py` 里的核心计算逻辑应该先抽哪一层，怎么避免大范围重写。
4. 现有主数据导入脚手架与“第一阶段项目持久化”之间应该如何排优先级。
5. 图纸、报告、工件文件是先保留文件系统存储，还是同步规划对象存储接口。
6. 哪些字段必须进入结构化列，哪些字段暂时保留在 `jsonb`。
7. 现有测试体系里，哪些回归测试必须先固定，才能安全推进数据库化。

## 9. 建议后续阅读顺序

如果后续由 ChatGPT 继续承接，建议按下面顺序读取：

1. 本文
2. [current_state_db_migration_prep.md](./current_state_db_migration_prep.md)
3. [database_design_and_er.md](./database_design_and_er.md)
4. [master_data_maintenance_api_prep.md](./master_data_maintenance_api_prep.md)
5. [dc_master_import_runbook.md](./dc_master_import_runbook.md)

如果需要进一步落到代码方案，再补读：

- `calb_sizing_tool/ui/dc_view.py`
- `calb_sizing_tool/ui/ac_view.py`
- `calb_sizing_tool/db/dc_master_seed.py`
- `calb_sizing_tool/db/dc_master_importer.py`

## 10. 一句话交接结论

截至 2026-04-10，这个仓库的“最近一次讨论”已经明确切到数据库迁移与主数据治理准备阶段。  
当前最准确的状态不是“数据库化已完成”，而是“数据库方向、表结构思路、主数据发布边界、Excel 导入脚手架已形成；下一步应由统一 DTO、服务层抽离、项目级持久化路径规划来决定实施顺序”。
