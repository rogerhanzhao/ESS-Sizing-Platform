# DC Master Import Runbook

## 1. 目的

这份 runbook 对应当前仓库里的导入脚本：

- [import_dc_master_data_to_postgres.py](D:/CALB_SizingTool/scripts/import_dc_master_data_to_postgres.py)
- [generate_dc_master_seed_sql.py](D:/CALB_SizingTool/scripts/generate_dc_master_seed_sql.py)

目标是把当前 DC Excel 字典导入 PostgreSQL，写入：

- 可维护主数据：`battery_cell_masters` / `battery_cell_revisions` / `dc_block_masters` / `dc_block_revisions`
- 发布快照：`dictionary_versions` / `battery_cell_types` / `dc_block_templates`
- 计算快照辅助表：`pack_types` / `rack_types` / `soh_*` / `rte_*`
- 发布记录：`master_publish_batches` / `master_publish_batch_items`

## 2. 前置条件

导入前，数据库里要先有 schema：

- [001_init_postgres.sql](D:/CALB_SizingTool/deploy/sql/001_init_postgres.sql)
- [002_master_data_publish_flow.sql](D:/CALB_SizingTool/deploy/sql/002_master_data_publish_flow.sql)

当前导入脚本不会自动建表；如果缺表，会直接报错并提示缺哪些表。

## 3. 先做 dry-run

先不要直接连库，先看摘要：

```powershell
python scripts/import_dc_master_data_to_postgres.py --dry-run
```

如果想先导成非激活版本：

```powershell
python scripts/import_dc_master_data_to_postgres.py --dry-run --inactive-version
```

这一步会输出：

- workbook 文件名
- source sha256
- 默认 version label
- 将要导入的 cell / block / soh / rte 行数

## 4. 正式导入

先设置连接串：

```powershell
$env:DATABASE_URL = "postgresql://user:password@host:5432/dbname"
```

然后执行：

```powershell
python scripts/import_dc_master_data_to_postgres.py
```

如果要指定版本标签：

```powershell
python scripts/import_dc_master_data_to_postgres.py --version-label "dc_v13_seed_20260314"
```

如果本次导入不想激活成当前版本：

```powershell
python scripts/import_dc_master_data_to_postgres.py --inactive-version
```

## 5. 导入行为

脚本现在的行为是：

1. 检查 schema 是否齐全
2. 检查同一个 workbook sha 是否已经导入
3. 如果本次版本要激活，则先把当前激活的 `dc` dictionary 置为 `inactive`
4. Upsert `battery_cell_masters`
5. 归档每个电芯已有的 `published` revision
6. 写入新的 `battery_cell_revisions`
7. 写入 `battery_cell_types`
8. Upsert `dc_block_masters`
9. 归档每个 block 已有的 `published` revision
10. 写入新的 `dc_block_revisions`
11. 写入 `dc_block_templates`
12. 写入 `pack_types` / `rack_types` / `soh_*` / `rte_*`
13. 写入 `master_publish_batches` / `master_publish_batch_items`

整次导入在一个事务里执行，只要中间失败，就整体回滚。

## 6. 重复导入行为

如果同一个 workbook 的 sha256 已经存在：

- 默认：`skip`
- 可选：`error`

命令：

```powershell
python scripts/import_dc_master_data_to_postgres.py --on-existing error
```

## 7. 当前默认版本标签

如果你不传 `--version-label`，脚本会自动生成：

```text
<workbook_name>#<sha256前8位>
```

这样做是为了避免同名 Excel 更新后，`version_label` 冲突。

## 8. 相关测试

当前已经补了两个 smoke test：

- [test_generate_dc_master_seed_sql.py](D:/CALB_SizingTool/tests/test_generate_dc_master_seed_sql.py)
- [test_import_dc_master_data_to_postgres.py](D:/CALB_SizingTool/tests/test_import_dc_master_data_to_postgres.py)

当前通过的是：

```powershell
pytest -q tests/test_generate_dc_master_seed_sql.py tests/test_import_dc_master_data_to_postgres.py
```

## 9. 下一步

这一步完成后，下一阶段就可以直接接：

- 后端 `repository / service`
- 主数据维护接口
- 发布接口
- DC 页面切换到数据库读数
