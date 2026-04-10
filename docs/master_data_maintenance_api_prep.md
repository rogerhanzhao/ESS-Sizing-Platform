# CALB Sizing Tool Master Data Maintenance API Prep

## 1. 目标

这份文档只解决一个问题：

后续如果要给“电芯基础参数”和“DC Block 基础参数”做后台维护界面，数据库和接口边界应该怎么拆，才能同时满足：

- 参数可以持续维护
- 历史计算结果不被新参数覆盖
- 发布后的参数可以稳定进入 DC 计算

## 2. 数据分层

建议严格分成三层：

1. `Master`
   - 稳定业务对象
   - 例如 `battery_cell_masters`、`dc_block_masters`
2. `Revision`
   - 每次编辑形成一条新版本
   - 例如 `battery_cell_revisions`、`dc_block_revisions`
3. `Published Snapshot`
   - 发布给计算引擎使用的不可变快照
   - 例如 `dictionary_versions`、`battery_cell_types`、`dc_block_templates`

数据库对象已经对应落在：

- [001_init_postgres.sql](D:/CALB_SizingTool/deploy/sql/001_init_postgres.sql)
- [002_master_data_publish_flow.sql](D:/CALB_SizingTool/deploy/sql/002_master_data_publish_flow.sql)

## 3. 维护模块拆分

建议后台至少拆成 3 个模块：

### 3.1 电芯主数据维护

对象：

- `battery_cell_masters`
- `battery_cell_revisions`
- `vw_battery_cell_latest_revision`
- `vw_battery_cell_published_snapshot`

维护动作：

- 新建电芯主数据
- 编辑电芯基础属性
- 基于当前版本复制出新 revision
- 对 revision 做草稿保存
- 将 revision 提交发布

### 3.2 DC Block 主数据维护

对象：

- `dc_block_masters`
- `dc_block_revisions`
- `vw_dc_block_latest_revision`
- `vw_dc_block_published_snapshot`

维护动作：

- 新建 DC Block 主数据
- 编辑 block 基础属性
- 基于当前版本复制出新 revision
- 对 revision 做草稿保存
- 将 revision 提交发布

### 3.3 发布管理

对象：

- `master_publish_batches`
- `master_publish_batch_items`
- `vw_master_publish_batch_summary`

维护动作：

- 创建发布批次
- 选择要发布的 cell revision / dc block revision
- 审核
- 发布为新的 `dictionary_version`
- 写入 snapshot 表供 DC 计算使用

## 4. 推荐接口资源

下面先按资源边界设计，不绑定具体框架。

### 4.1 电芯接口

- `GET /api/master-data/cells`
  - 查询电芯主数据列表
- `POST /api/master-data/cells`
  - 新建电芯主数据
- `GET /api/master-data/cells/{cell_master_id}`
  - 查询单个电芯主数据
- `PATCH /api/master-data/cells/{cell_master_id}`
  - 修改主数据基础信息
- `GET /api/master-data/cells/{cell_master_id}/revisions`
  - 查询 revision 列表
- `POST /api/master-data/cells/{cell_master_id}/revisions`
  - 基于当前参数创建新 revision
- `GET /api/master-data/cell-revisions/{cell_revision_id}`
  - 查询单个 revision
- `PATCH /api/master-data/cell-revisions/{cell_revision_id}`
  - 修改 revision 参数
- `POST /api/master-data/cell-revisions/{cell_revision_id}/submit`
  - 提交进入发布批次

### 4.2 DC Block 接口

- `GET /api/master-data/dc-blocks`
- `POST /api/master-data/dc-blocks`
- `GET /api/master-data/dc-blocks/{dc_block_master_id}`
- `PATCH /api/master-data/dc-blocks/{dc_block_master_id}`
- `GET /api/master-data/dc-blocks/{dc_block_master_id}/revisions`
- `POST /api/master-data/dc-blocks/{dc_block_master_id}/revisions`
- `GET /api/master-data/dc-block-revisions/{dc_block_revision_id}`
- `PATCH /api/master-data/dc-block-revisions/{dc_block_revision_id}`
- `POST /api/master-data/dc-block-revisions/{dc_block_revision_id}/submit`

### 4.3 发布批次接口

- `GET /api/master-data/publish-batches`
  - 查询发布批次列表
- `POST /api/master-data/publish-batches`
  - 创建发布批次
- `GET /api/master-data/publish-batches/{publish_batch_id}`
  - 查询批次详情
- `POST /api/master-data/publish-batches/{publish_batch_id}/items`
  - 加入 revision 条目
- `DELETE /api/master-data/publish-batches/{publish_batch_id}/items/{item_id}`
  - 移出条目
- `POST /api/master-data/publish-batches/{publish_batch_id}/approve`
  - 审核通过
- `POST /api/master-data/publish-batches/{publish_batch_id}/publish`
  - 正式发布，生成新的 `dictionary_version`

## 5. 建议状态流转

### 5.1 Master 状态

`active -> inactive -> archived`

用途：

- `active`
  - 可继续创建新 revision，可用于后续发布
- `inactive`
  - 不建议新项目继续使用，但保留历史
- `archived`
  - 只保留追溯

### 5.2 Revision 状态

`draft -> published -> archived`

说明：

- `draft`
  - 可编辑
- `published`
  - 已进入某个 `dictionary_version`
- `archived`
  - 历史保留，不再作为当前发布版本

### 5.3 Publish Batch 状态

`draft -> review -> approved -> published`

失败链路：

- `failed`
- `archived`

## 6. 发布动作的数据库步骤

建议一次正式发布按下面顺序执行：

1. 创建 `master_publish_batches`
2. 写入 `master_publish_batch_items`
3. 生成新的 `dictionary_versions`
4. 把 batch 中的 cell revision 映射为 `battery_cell_types`
5. 把 batch 中的 DC block revision 映射为 `dc_block_templates`
6. 回写 revision 的 `published_dictionary_version_id`
7. 更新 revision 的 `published_at` 和 `revision_status`
8. 把批次改成 `published`

这里的关键原则是：

- 计算只读 snapshot
- 维护页面只改 master / revision
- 发布是唯一从“可编辑数据”进入“计算数据”的入口

## 7. 后续代码层建议

如果下一步开始落后端，我建议按下面顺序做：

1. 先做 repository / service 层
   - `CellMasterService`
   - `DcBlockMasterService`
   - `PublishBatchService`
2. 再做发布事务
   - 一个事务内完成 dictionary version + snapshot 写入 + revision 回写
3. 最后再让 DC 页面切换到数据库主数据读取

原因很简单：

- 如果先改 UI，不先把发布事务收敛好，后面容易出现“可维护数据”和“计算快照”串用的问题

## 8. 当前这版的边界

当前仓库里已经把数据库对象预留好了，但还没有实现：

- 实际后端 API
- Excel 导入到 master/revision 的脚手架
- 从 revision 发布到 snapshot 的服务代码
- 权限、审批、审计日志

所以现在这份设计的定位是：

- 先把数据模型定稳
- 给后续接口开发和迁移改造提供边界
