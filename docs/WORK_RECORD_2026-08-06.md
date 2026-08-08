# 执行记录与状态（2026-08-06）

**用途**：供 owner 与其他审阅者（含 CODEX）核对本轮改动。每一条结论都给出
**可自行复现的验证方式**，不要求相信本文——请直接跑验证命令。

**分支**：`ops/ubuntu-docker-coexist-20260311`（未新建分支）
**基线**：`1f053b7` → 分支末端，共 8 次提交
**测试**：起始 633 passed / 2 skipped → **末端 721 passed / 0 skipped**
（**skipped 归零** —— 那 2 条常年 skipped 的正是被退役的 IIDM 栈的唯一测试，见 §四之十）
**冻结正典**：`services/ac_sizing_service.py`、`services/dc_pipeline_service.py`、
`common/ac_block.py`、`common/allocation.py` —— **本轮一个字节未改**

```bash
# 一次性核对上面三条
git log --oneline 1f053b7..HEAD
python -m pytest tests/ -q | tail -3
git diff --name-only 1f053b7..HEAD | grep -E "ac_sizing_service|dc_pipeline_service|common/ac_block|common/allocation" || echo "冻结正典未动"
```

---

## 一、本轮提交清单

| 提交 | 主题 | 性质 |
| --- | --- | --- |
| `393463f` | 报告按 AC 方案分版本（第 4 步） | 功能 |
| `e216f5a` | 重新生成也按选中方案取输入（第 5 步） | 功能 |
| `81b58b0` | 复用的方案必须发最新内容，不是首次内容 | **修我自己引入的回归** |
| `9b7f2ab` | 回收"有文件、没数据库行"的产物 + 堵 `.gitignore` 缺口 | 运维 + 安全 |
| `bfb36ac` | 服务器上七个保留参数以前根本没传进容器 | **修既有缺陷** |
| `2977966` | 服务器只读诊断脚本 | 工具 |
| `5db9aca` | 执行记录文档 + 本机清理脚本 | 文档 + 工具 |
| （本次） | 侧边栏版本号可随升级变化、V 大写、升级后自动校验 | **修既有缺陷** |

---

## 二、功能改动（owner 裁决 B 收尾）

裁决 B 原文："同一个确定了的 DC 方案，AC 是可以稍微有多一个方案的……
SLD 以后的所有生成都可以变，最终报告可以重新生成一个版本"。
第 1–3 步在 2026-08-04 已完成；本轮做完第 4、5 步，**裁决 B 全部落地**。

### 第 4 步 —— 报告分版本（`393463f`）

**问题**：两个 AC 方案导出的报告**文件名相同**，第二次静默覆盖第一次。

**命名规则**：`ac_run_service.ac_alternative_label(dc_run_id, ac_run_id)` → `A`/`B`/…

| 约束 | 为什么 |
| --- | --- |
| **按最早优先排序** | 先试的永远是 A；后来的方案不给已发出的报告改名，报告必须可复现 |
| **只有 ≥2 个方案才返回标签** | 一个方案是常态，跟谁都不用区分；贴标签会改掉**所有**普通报告的文件名 |
| `list_child_runs` 加 `sizing_run_id` 次序键 | 同一时钟刻度内建的两个 Run 若只按 `started_at` 排，两次调用可能互换 = 改名 |

标签落到三处：文件名 `..._V2.1_AC-B.docx`、封面 `AC Alternative: B`、
Document Provenance 表（含 AC Run 号）。

**验证**：`tests/unit/test_report_ac_alternative_versioning.py`（10 条），
**正反双向锁**——两个方案必须导出两个文件；一个方案必须与历史文件名逐字一致、
正文不出现任何方案措辞。

### 第 5 步 —— 重新生成按方案取输入（`e216f5a`）

**问题**：图纸已跟着方案走，但 `load_persisted_ac_snapshot` 读的仍是
"最后保存的那套 AC"。在方案 A 上重算 SLD，喂进去的可能是 B 的参数 ——
**图上写着 A，画的是 B**。

**修法：不新增任何存储。** `persist_ac_run` 本来就把每个方案的 inputs/output
各存了一份快照，且与运行态快照来自同一对 dict，读取端优先取即可。

```
load_persisted_ac_snapshot(dc_run_id, ac_run_id=选中方案)
    1. 方案自己的 ac_case_input / ac_sizing_output  → 有就用
    2. 否则回退 DC Run 的 ac_runtime_snapshot_v1   → 老库就是这一条（无需迁移）
```

三个设计决定：

1. **`run_id` 始终是 DC Run** —— 它是身份锚点，页面 run/case/project 交叉校验
   都认它；方案快照里的 `source_run_id` 仍是 DC Run，**校验一行未改**。
2. **选到别的 DC Run 的分支 → 拒绝使用**，落回本 DC Run 的快照。
3. `resolve_preferred_ac_snapshot` **自己**读 `active_ac_run_id`，
   与 `artifact_run_id()` 同一条规矩：**这个判断只能有一处**。

配套：AC 页面保存成功后 `adopt_saved_ac_run(新方案)` ——
**保留 AC 状态**（session 里装的就是这个方案的结果）、**清掉 SLD 与排布**
（那是上一套配置画的）。见 §四之三。

**验证**：`tests/unit/test_ac_alternative_snapshot_scope.py`（13 条）。

### 自查发现并修掉的回归（`81b58b0`）

**这是我在第 5 步亲手挖的洞，不是既有缺陷。**

身份哈希只覆盖 17 个字段，所以**同一身份下内容可以变**（案例改名、不改变方案的
输入微调），此时 Run 被**复用**。第 5 步让方案自己的快照成为页面读取来源后，
停在第一次保存 = **发陈货**。第 5 步之前 DC 运行态快照每次保存都重写，不会发生。

复现过，不是推测：

```
保存 → 案例改名 → 再保存
Run 被复用: True              ← 符合预期
方案给出 source_case_name = OLD NAME   ← 错
方案给出 inputs = {'note': 'first'}    ← 错
```

**修法**：`_refresh_alternative_snapshots` **只在内容真的变了时**补写。
守住两条红线：

- 参数没动的重算依然一行不写 → **行数 = 真正试过的方案数**不破
- 补写的 input 行**保留身份哈希**，不能换成自身 payload 的哈希 ——
  `find_child_run_by_hash` 认的就是它，改了会让方案变孤儿、下次保存多出重复 Run

`prune_snapshot_generations` 同步覆盖 input 快照（同一 AC Run 的 input 行哈希
全都一样，剪枝不影响去重查找）。

---

## 三、垃圾文件治理

### 3.1 三个位置必须分清

| 位置 | 有没有垃圾 | 谁在清 |
| --- | --- | --- |
| **GitHub 仓库** | **没有** —— `outputs/` 一直被 gitignore | 不需要清 |
| **开发机 checkout** | 有 | **以前没有任何东西在清** ← 本轮补上 |
| **服务器 runtime** | 有 | 每周日 03:30 systemd timer（本来就有） |

`git ls-files | grep -E "^outputs/"` 为空 —— 那 172 MB **从未上过 GitHub**。

### 3.2 查出的真缺口：有一半方向没有 owner（`9b7f2ab`）

- `prune_orphaned_artifacts` 管"**有行、没文件**" → 删行
- "**有文件、没行**" → **Python 侧一个函数都没有**

唯一在扫的是 `deploy/docker/calb-maintenance.sh` 里的 `find -mtime +30 -delete`，
而它只对部署机的 `CALB_RUNTIME_ROOT` 生效。**开发机的 checkout 是裸奔的**，
所以攒到 479 个 run 目录 / 5081 个文件 / 172 MB。

**源头控制是有效的**（这一条要单独说，避免被误判为失效）：
全量测试跑前跑后 `outputs` 文件数不变，`tests/conftest.py` 的隔离生效。

### 3.3 新增清扫的三道护栏

`maintenance_service.prune_unreferenced_artifact_files`：

1. **默认只数不删**。不是胆小：操作员连错数据库时看到的是空注册表，
   一个信任它的清扫会把磁盘上**所有** artifact 判成垃圾。先把数字摆到人面前。
2. **注册表读不出来就一个都不删**。`find_unreferenced_artifact_files`
   **故意不接** `OperationalError` —— 它绝不能在"读不到"时回答"没有被引用"。
3. **只扫 `outputs/artifacts`**（`logs/` 有自己的保留策略、`external_ai/` 是
   给用户的产出）；**`CALB_UNREFERENCED_GRACE_DAYS`（7 天）内的文件永不入选**。

**验证**：`tests/unit/test_maintenance_service.py` 中 7 条，含
`test_an_unreadable_registry_deletes_nothing`。

### 3.4 `.gitignore` 堵住三类进入公开仓库的途径

| 新增 | 原因 |
| --- | --- |
| `*.docx` | `export_docx` 在哪运行往哪写，报告含客户数据 |
| `*.db` / `*.sqlite*` / `*-wal` / `*-shm` | sizing 库是客户数据；`var/` 挡住了，路径跑偏挡不住 |
| `/.env`、`/secrets.toml`、`/.streamlit/secrets.toml` | **密钥**；根锚定，不影响 `deploy/systemd/*.env.example` 例外 |

**验证**：`git ls-files | git check-ignore --stdin` 输出为空 = 无已跟踪文件被误伤。

### 3.5 本容器的实际清理（已执行）

| | 清理前 | 清理后 |
| --- | --- | --- |
| `outputs/` 总计 | 5267 文件 / **158.8 MB** | 186 文件 / **1.0 MB** |
| `outputs/artifacts` | 5081 文件 | **0** |
| `external_ai/` / `logs/` | 1.5 MB / 1.0 MB | **未动** |

**未使用 `rm`**，两次都走产品自己的清扫入口：

1. 默认 7 天宽限期 → 1275 文件 / 40.1 MB
2. `CALB_UNREFERENCED_GRACE_DAYS=0` → 3806 文件 / 117.7 MB

**第二次归零宽限期的前提**：先 `alembic upgrade head` 让 `artifact_registry`
表真正建起来，查得 **0 行** —— 把手工推断换成了产品口径的证据。
**这个组合只在验证过注册表确实为空时成立，不是常规操作。**

---

## 四、服务器侧缺陷（`bfb36ac`）

`calb-maintenance.sh` 在**容器内**跑清扫，但 `docker-compose.ubuntu.yml`
的 `environment:` 块**一个数据库侧保留参数都没传**。

**后果**：`deploy/docker/.env` 里设的值**全在容器边界上被丢掉**，
清扫永远只用内置默认值；未引用文件清扫**根本无法在服务器上启用**。
之前唯一生效的是 `CALB_OUTPUT_RETENTION_DAYS` —— 那个是宿主机 `find` 用的。

七个参数现已接通并写进 `.env.example`。`CALB_PRUNE_UNREFERENCED_FILES`
在服务器上同样默认留空（只数不删）。

**验证**：`test_the_server_can_actually_tune_the_sweep`、
`test_the_server_sweep_runs_rows_before_files`。

---

## 四之二、侧边栏版本号（owner 2026-08-06 提出）

**缺陷**：`app.py` 侧边栏底部是 `st.caption("v2.1 · …")` —— **硬编码字面量**。
它不可能随代码变化，**比不显示版本更糟**：升级后无论成没成功都显示 `v2.1`，
去核对的人会被一个什么都没证明的字符串安抚。

**两个数字，回答两个不同问题**（只显示前者正是无用的原因）：

| | 来源 | 变化频率 |
| --- | --- | --- |
| `release_version()` | `VERSION` 文件 | 手动改版本时才变；报告以它署名 |
| `build_revision()` | 构建时烧入的 commit | **每次部署都变** —— 唯一能验证部署的东西 |

**为什么必须构建时烧入**：`.dockerignore` **排除了 `.git`**，容器里没有 git
元数据，运行时查 git 在服务器上**永远失败**。因此走
Dockerfile `ARG` → compose `build.args` → `calb-serverctl.sh` 三段链路，
**任何一段断了，侧边栏就静默退回 `dev`**，缺陷复发而无人察觉。
`tests/unit/test_app_version.py` 逐段锁死（18 条）。

**显示**（位置就是 owner 要求的侧边栏最底部，原本就在那里）：

- 正文：`V2.1 · 5db9aca · CALB ESS Sizing Platform · db:20260804_0009`
- 悬停：加上 `branch <分支>` 与 `built <UTC 时间>`

**V 大写**：`VERSION` 文件只存裸数字 `2.1`，大写 V 在 `release_version()`
统一加，杜绝各调用点写法漂移；文件里已带 `v/V` 前缀会被归一化而不是叠加。

### 复审发现的三个缺陷（2026-08-06 二次梳理，均已修）

owner 要求"再梳理一遍"，把上面这套机制当别人的代码逐条实证，查出三处：

| # | 缺陷 | 实证 | 修法 |
| --- | --- | --- | --- |
| 1 | `env_rev[:12]` 把 `5db9aca+dirty` 截成 `5db9aca+dirt` | 直接跑出来 | 上限放到 24 字符；**截断仍保留**，防止构建参数灌爆侧边栏 |
| 2 | `@lru_cache` 让开发机上的版本号**永远停在进程启动时** | 进程内改仓库后函数仍返回旧值 | `release_version` / `build_revision` / `build_branch` 全部取消缓存（git 调用实测 2.2 ms）；`build_time` 保留缓存，因为它只来自环境变量、容器内不可变 |
| 3 | `verify_version` 的 `git fetch` 会因索要凭据打断部署 | 见下 | 加 `GIT_TERMINAL_PROMPT=0` / `GIT_ASKPASS=true` |

**缺陷 2 是原缺陷的翻版**：owner 报的就是"版本号不随更新改变"，而缓存会在开发机上
把同一个毛病重新造出来——`git pull` 改了代码，页面还是旧号，直到重启进程。

**缺陷 3 的实证过程值得记一笔**：我最初写的是"无 tty 会挂起"。搭了一个返回 401 的
本地服务端实测，**结论是相反的** —— 无 tty 时 git 直接以 128 退出，不会挂。
真正的场景是 ssh 交互式跑 `update` 时弹出凭据提示打断部署。
脚本注释已按实测结论改写，没有保留我未证明的说法。

**一处怀疑但证伪的**：`case "$container_line" in *"$local_rev"*)` 中若 `local_rev`
取不到而变成 `?`，`?` 在 case 里是通配符，会误判成"一致"。实测**不会** ——
模式里的 `"$local_rev"` 带引号，引号已禁用了通配。原样保留。

**已验证无问题的**：`st.caption(help=)` 在 streamlit 1.60 受支持（不支持会直接
崩掉整个应用）；`VERSION` 不被 `.dockerignore` 排除，确实进得了镜像。

回归锁：`tests/unit/test_app_version.py` 增至 23 条，其中 5 条专锁这三个缺陷，
含"拿掉护栏测试必须失败"的反向验证。

### 二次梳理续：版本号还有两处对不上

**A. 报告里的版本号与 `VERSION` 文件是两个独立的真源。**

实测：把 `VERSION` 改成 `2.2` —— 侧边栏显示 `V2.2`，
**报告封面和文件名仍是 `V2.1`**（`brand_profiles.py` 里 8 处硬编码）。
这正是 owner 报的那类毛病（版本号不跟着走），只是搬到了交给客户的文档里。

**故意没有改成自动派生**：报告封面标题与提案文件名是对外署名，
怎么产生是 owner 的决定，不是可以顺手重构的东西。
所加的是一道守卫 `test_the_report_cannot_drift_from_the_release_file` ——
**改了 `VERSION` 而没同步 brand，测试直接失败**，脱节无法被静默提交。
已反向验证：`VERSION=2.2` 时该测试确实 FAIL。

> 若 owner 认为报告版本**应当**独立于工具版本演进，
> 那就删掉这条守卫并在此写明理由；现在的状态是"两者必须一致"。

**B. 登录前看不到版本号。** 侧边栏在 `show_login(); st.stop()` 之后才渲染，
所以核对"升级有没有生效"必须先有账号并登录。已在登录页底部加上同一个
`version_label()` —— 查部署结果不该需要凭据。

### 每次升级自动校验（owner："无论任何升级，版本号都要检验"）

`calb-serverctl.sh` 的 `start` / `restart` / `update` **收尾都会跑
`verify_version`**，另有独立的 `version` 动作。它检查**三方一致**：

```
branch          : ops/ubuntu-docker-coexist-20260311
local HEAD      : 5db9aca
origin/<branch> : 5db9aca      -> checkout matches GitHub
running app     : V2.1 · 5db9aca · branch ...
                               -> the running image is built from this checkout
```

三条设计要点：

1. **与 GitHub 的比较按分支**（`origin/<branch>`）。"最新"是相对分支的说法，
   光有 commit 号无法判断。
2. **连不上 origin 报 `UNREACHABLE`，绝不报"一致"**。内网服务器出不去是常态，
   把"没查到"说成"没问题"才是真事故。
3. **checkout 与 GitHub 一致，不代表镜像是新的** —— 构建失败时旧容器会继续服务，
   这恰恰是最该抓的情况，所以运行中容器单独查一遍。

`+dirty` 标记：工作区脏时构建，镜像不配声称自己是那个 commit。

---

## 四之三、系统性审查（CODEX 停止后，2026-08-06）

对本轮全部改动（14 个产品文件、约 1600 行 diff）做了一次系统审查，
查出 **6 个缺陷 + 1 条被证伪的结论**。全部**先复现再动手**。

### 最严重：新增返回值，四个调用点无人更新

`resolve_preferred_ac_snapshot` 增加了 `source="persisted_ac_alternative"`，
而 SLD、排布、AC 三个页面都在写 `source == "persisted_run_snapshot"`。
又因为我给 AC 保存加了"选中刚存的方案"，**这个新值变成了常态而不是边角**。

实测后果：

| 页面 | 选中方案后 |
| --- | --- |
| SLD | `force_draft=True`，**每张图都被打成 draft/override 并标记未达正式条件** |
| 排布 | 警告"session compatibility fallback，请先持久化 AC" —— **数据明明已持久化** |
| AC | 快照不被采纳，切换会话/案例后**表单一片空白** |

**修法不是各加一个 `or`** —— 根因是字符串型契约。
服务侧给出 `PERSISTED_SOURCES` 与 `AcSnapshotResolution.is_persisted`，
页面问属性。新增来源必须在**唯一一处**分类，否则
`test_every_source_the_service_can_return_is_classified` 直接失败。

### 其余五个

| 缺陷 | 后果 | 修法 |
| --- | --- | --- |
| `calb-diagnose.sh` 第 5 节没带 `--dry-run` | **号称"生产可安全运行的只读诊断"，实际删产物行/文件/快照/审计/oplog** | 加 `--dry-run`；测试遍历脚本每一行 |
| `clear_downstream=False` 连同图纸一起保留 | 报告标着"AC Alternative B"，里面却是 A 的 SLD | 新增 `adopt_saved_ac_run()`：**保留 AC 状态、清掉图纸**；并删除 `clear_downstream` 参数，不留误用余地 |
| dry-run 只数不量 | `unreferenced_files=1` 却报 `bytes_freed=0`，"先看数字再删"失去意义 | 三处补上字节统计（实测 4096 字节现在如实上报） |
| 路径映射失效时会全盘误删 | 库被恢复 / outputs 搬家 → legacy 绝对路径全失效 → **磁盘上所有文件被判为垃圾** | `BrokenArtifactPathsError`：**过半行解析不到就拒绝执行** |
| `external_layout_service` 未传 `ac_run_id` | 对外导出仍用"最后保存的那套" | **维持现状**（对外接口只给 run_id，无方案上下文），已在 §六 记录 |

### 一条被证伪的审查结论

审查说"孤儿行清理先跑，清空注册表，文件清扫随后全删"。
**机制不成立**：孤儿行清理只删*文件已不存在*的行，
这种行本来就不保护任何现存文件。按此写的测试**确实失败了**，
于是撤掉了那个没有依据的重排理由，改成针对真实风险（路径映射失效）的护栏。
`run_maintenance` 的顺序保留，但注释改成"这是整洁性，不是那道保护"。

**教训**：审查结论也要复现才能采信 —— 照单全收会写出一个防不住真实风险、
却让人以为已经防住的"修复"。

回归锁：新增 11 条，含两处"撤掉修复测试必须失败"的反向验证。
`tests/` 总计 **705 passed, 2 skipped**。

---

## 四之四、把页面真正跑起来验证（2026-08-06 第三轮）

前几轮的版本号测试**全部只测函数和文件，没有一条跑过页面**。
补了 `tests/test_version_display_smoke.py`，用 `streamlit.testing.v1.AppTest`
**真正执行 app.py**。这类测试抓的是前面抓不到的东西：侧边栏里一个不被支持的
关键字、一个漏掉的 import、一次转义错误 —— 那会让**整个应用崩掉**，
比它替换掉的那个陈旧 `v2.1` 后果严重得多。

先做了更基础的一步：`streamlit run app.py` 实际启动，`/_stcore/health` 返回 `ok`。
但**这只证明静态外壳能发出去，不证明脚本渲染不报错** —— 所以才需要 AppTest。

### 抓到的第三处硬编码版本

`calb_sizing_tool/ui/login_view.py:120` 登录页左栏页脚：

```
© 2026 Alex Zhao · MIT License · v2.1     ← 小写，且永远不会变
```

同一缺陷的第三个实例（侧边栏、`brand_profiles`、这里）。已改为从 `VERSION` 取。
**是那条新写的渲染测试抓到的，不是我看出来的** —— 正是"只测函数不测页面"会漏的那类。

登录页现在两处版本各有用途：左栏页脚 `V2.1`（产品发布号），
表单下方 `V2.1 · <commit>`（**验证部署用的那个**）。

### 一个测试陷阱，记给下一个人

`app.py` 的迁移挂在 `@st.cache_resource` 上，**每进程只跑一次**。
同一会话里第二个 app 级测试拿到的新库从未被迁移，页面死在 "no such table"。
四条测试单独跑全过、进全量套件就挂 —— 现象极具误导性。
fixture 里显式跑 alembic 即可（`test_sld_page_state_smoke` 早就这么做）。

### 治理闸门复核（这条最不能想当然）

`force_draft=True` 不只是标签难看，它会打开 `override_mode`，
**直接禁用正式/严格生成** —— 所以上一轮那个缺陷是功能性阻塞。

反过来问：把 `persisted_ac_alternative` 判为权威，是否**放松了闸门**？
**没有**。方案快照本身就是持久化的（`persist_ac_run` 带内容哈希写进快照表），
正是闸门要求的东西；`_validate_ac_snapshot_context` 的 run/case/project
交叉校验仍在其之前生效 —— 实测：同一 DC/case/project 通过，
指向别的 run 或别的 case 一律拒绝。

### 本轮核对项

| 项 | 结果 |
| --- | --- |
| 应用能否启动 | `streamlit run` 正常，健康检查 `ok` |
| 登录页 / 侧边栏渲染 | AppTest 执行无异常，版本号均在位 |
| 是否还有硬编码版本 | 全仓库扫描；剩余全在报告域，已被脱节守卫覆盖 |
| 第四个 resolver 调用点 | `report_export_view` **不按 source 分支**，无遗漏 |
| 治理闸门 | 未放松，交叉校验实测有效 |
| 冻结正典 | 一字未改，guard 7 条全绿 |
| 库无表时 | **异常抛到页面**，不是静默空白（实测） |

`tests/` **709 passed, 2 skipped**。

---

## 四之五、扩大审查：本轮改动之外的存量问题（2026-08-06）

owner："这个项目经历了很多过程，CODEX、Claude 都参与，模型能力迭代很快，
之前的设计可能有不合理的地方。"

审查范围从"本轮 diff"扩到**整个仓库**（49k 行产品代码）。
先讲已修的那条，因为它是唯一有对外风险的。

### 已修：加戳咽喉之外还有一条插图路径

NOT-FOR-CONSTRUCTION 的设计是对的 —— `_add_concept_figure` 是唯一咽喉，
fail-closed。**但设计只在"所有图纸都走它"时成立**，而
`export_docx.create_combined_report` 用裸 `doc.add_picture` 插入 SLD 和排布图，
**不加戳**。

它目前只有测试在调，UI 用的是 `export_report_v2_1`，所以**没有发出过无标记的图**。
但"当前不可达"不是安全属性 —— 把那个生成器接回一个按钮，就会把无标记的工程图
发给客户，而且没有任何东西会反对。已改为走同一个咽喉。

规则现在是**结构性强制**而非靠人记得：`tests/unit/test_watermark_choke_point.py`
用 AST 遍历 reporting 包里**每一个** `add_picture`，要么在咽喉内，
要么在 `ALLOWED_UNSTAMPED` 里具名说明"这是数据不是图纸"（POI 曲线、页眉 logo、
DC 寿命图表）。新增一处未声明的插图 → 测试直接失败。

**顺带纠正我自己一个错误判断**：我最初写的测试断言"坏图必须抛 `WatermarkError`"，
**实测没抛，但代码是对的、而且比我以为的更严** —— 坏图会被换成**带红框标记的
占位图**，报告仍能产出而那张图明确标着无法加戳；`WatermarkError` 只在连占位图
都造不出来（Pillow 缺失）时才抛。是我的预期错了，测试已按真实契约重写。

### 查实但未动，需要 owner 决策的三项

| # | 发现 | 量级 | 为什么没动 |
| --- | --- | --- | --- |
| 1 | ~~死代码 1596 行~~ | — | **已删除**，见下方 §四之六 |
| 2 | **SLD 渲染器并存 8 套**：`sld_server_baseline_renderer`(1716) / `sld_engineering_v2_renderer`(1309) / `jp_pro_renderer`(778) / `sld_pro_renderer` / `sld_professional_sheet` / `visualizer` / `renderer` / `calb_diagrams_sld`(死) | ~6k 行 | 其中 `sld_server_baseline_renderer` 只被 1 个文件引用。要判断哪些是活的、哪些该退役，需要您确认产品意图 |
| 3 | **`svg_postprocess` 三个变体**（`_margin` / `_raw` / 主体） | ~400 行 | `_raw` 已死；另两个的分工没有文档说明 |

### 查过但**不是**问题的（记下来免得反复发现）

- **报告缺图不是静默的**：§7 会写 "SLD not generated"。但措辞会误导 ——
  读取失败也说成"没生成"，用户会去重新生成一张本来就存在的图。**小问题，未改。**
- **DC 页导出、报告 §容量曲线**：插的是数据图表（POI 曲线、容量衰减），
  不是工程图纸，**不需要加戳**，治理没破。
- **32 处静默吞异常**：逐个看过，多数是可选依赖探测和路径回退，属合理用法。
  唯一值得留意的是 `report_context.py` 读 artifact 失败会静默 —— 后果就是上面
  那条"缺图但说成没生成"。

---

## 四之六、删除死代码（owner 批准，2026-08-06）

owner："先删掉死代码，但是再多确认梳理一次！"

第一次的判定只按**模块名**做正则。再查一次时补上**符号级引用**，
结果直接推翻了那个方法的可靠性：`calb_diagrams_sld.py` 导出的
`render_sld_pro_svg` **在 16 处出现**，其中包括 `calb_diagrams/__init__.py`。

追下去才清楚 —— **仓库里有三份同名的 `render_sld_pro_svg`**：

| 定义处 | 谁在用 |
| --- | --- |
| `calb_diagrams/sld_pro_renderer.py` | `calb_diagrams/__init__.py` + 4 个测试 |
| `calb_diagrams/sld_server_baseline_renderer.py` | `plugins/sld_engineering_plugin.py` |
| `calb_diagrams/calb_diagrams_sld.py` | **无人** |

那 16 处命中全是**别的模块里的同名函数**。结论不变，但**如果只做模块名扫描就删，
理由是站不住的** —— 这正是 owner 要求"再确认一次"的价值。

### 删除前通过的八项确认

| # | 检查 | 结果 |
| --- | --- | --- |
| 1 | 模块名在全仓库（py/md/toml/json/yml/sh/ps1）的引用 | 0 |
| 2 | **每个 public 符号**在别处的引用 | 全为同名巧合，非引用 |
| 3 | 是否在冻结正典清单里 | 否（清单只有 7 个 sizing 核心文件） |
| 4 | 是否被任何 `__init__.py` 再导出 | 否 |
| 5 | 星号导入路径（会绕过模块名） | 仓库仅 2 处，均不涉及 |
| 6 | 打包/配置/Dockerfile 点名 | 无 |
| 7 | git 历史 | 随初始导入 `2cb294c`（579 文件/92k 行）进来，**此后从未修改** |
| 8 | 自身能否导入 | 能 —— 不是坏掉的残骸，只是无人使用 |

### 删除后验证

| 验证 | 结果 |
| --- | --- |
| 逐模块导入 207 个模块 | 全部成功（2 个 `networkx` 失败是本容器缺装可选依赖，与删除无关） |
| 全量测试 | **722 passed, 2 skipped**，与删除前一致 |
| 应用启动 | `streamlit run` 正常，健康检查 `ok`，HTTP 200 |

净减 **1596 行**。

> **顺带暴露的问题**：`render_sld_pro_svg` 现在仍有**两份活的实现** ——
> `__init__.py` 和测试用 `sld_pro_renderer`，插件用 `sld_server_baseline_renderer`。
> 同名不同实现，两条路径可能画出不同的图。这属于 §四之五 第 2 项
> "8 套渲染器并存"，需要 owner 确认产品意图后才能收敛。

---

## 四之七、渲染器与重复实现的取证（2026-08-06，只查不动）

owner："请继续分析！！先确认清楚。" 所以这一节**只摆事实**，没有删任何东西。
方法上放弃了正则猜测，改用 **AST 解析真实 import 语句建导入图**。

### 先纠正我自己上一条消息里的判断

我上一条说"两份 `render_sld_pro_svg`，测试验的可能不是用户看到的那份"。
**查下来不成立**：

```
PUBLIC_SLD_RENDERER_MODES = ("engineering_v2",)      ← 用户唯一能选的
DEV_ONLY   = ("legacy_server",)     → sld_server_baseline_renderer
RESERVED   = ("topology_v1",)       → sld_pro_renderer（已退役，UI 选不到）
```

用户看到的是 `sld_engineering_v2_renderer`（1309 行，**7 处测试引用**），
覆盖是好的。担心不成立。

### 渲染相关模块的真实状态

| 模块 | 行数 | 产品可达路径 | 测试 |
| --- | --- | --- | --- |
| `sld_engineering_v2_renderer` | 1309 | **用户默认路径** | 7 |
| `sld_server_baseline_renderer` | 1716 | 仅 `legacy_server`（dev-only） | **0** |
| `sld_pro_renderer` + `sld_layout_engine` | 187 + 548 | 仅 `topology_v1`（**已退役**） | 4 + 2 |
| `jp_pro_renderer` | 778 | **产品无消费者**，唯一调用者是 `test_sld_pro_smoke.py` | 1 |
| `visualizer` | 68 | **导入图不可达**，唯一调用者是 `test_sld.py` | 1 |
| `svg_postprocess` / `_margin` | 155 + 99 | 只被 `sld/__init__.py` **再导出**，`append_dc_block_function_blocks` 与 `add_margins` **无任何调用点** | 0 |

**"被 `__init__` 导入"不等于"被使用"** —— 这是上次删死代码时踩过的同一个坑，
所以这次逐个查了调用点而不是引用数。

合计约 **3.5k 行**只被测试或已退役模式触及。是否退役需要 owner 的产品意图：
`legacy_server` 是否还要保留作为出问题时的回退？`topology_v1` 是否真的不再需要？

### 另一条：23 个 public 符号被多处独立定义

其中最值得追的是 `ui/dc_view.py` 与**冻结正典** `services/stage1_service.py`
同名的七个。

**第一反应是严重问题**：冻结正典被 SHA 锁定，而页面有自己一份 `run_stage1`？
那冻结岂不是装饰品。

**查完是虚惊**：`dc_view.run_stage1` 是**两行的转发壳**，直接调
`service_run_stage1(...).to_legacy_dict()`。**冻结正典就是用户拿到的东西。**

但另外六个（`to_float`/`to_int`/`to_frac`/`clamp01`/`safe_div`/`calc_sc_loss_pct`）
**是真的复制粘贴副本**。不看代码、直接比行为：

```
to_float / to_int / to_frac   28 组用例   差异 0
clamp01 / safe_div            22 组用例   差异 0
calc_sc_loss_pct              51 组用例   差异 0
```

**今天完全一致，所以这是漂移风险而不是现行缺陷。** 但冻结保护的是其中一份，
而用户看的页面读的是另一份，**没有任何东西保证它们同步**。
`calc_sc_loss_pct` 尤其要紧 —— 它是个 sizing 数字，一旦分叉，
页面显示一个储存损失率、正典算出另一个，**而冻结文件的哈希校验照样通过**。

已加 `tests/unit/test_dc_view_helpers_match_the_canon.py`（13 条）锁住这个事实，
并反向验证过：把页面那份的 `4.5` 改成 `4.6`，测试立刻失败。
**根治方法是让页面直接调服务**（`run_stage1` 已经是这么做的），
在那之前由这个测试盯着。

---

## 四之八、退役 legacy_server 与 topology_v1（owner 裁定 2026-08-06）

owner：「1. legacy_server，不留；2. TOPOLOGY_V1 不用了」。

### 删了什么

| 模块 | 行数 | 归属 |
| --- | --- | --- |
| `calb_diagrams/sld_server_baseline_renderer.py` | 1716 | `legacy_server` |
| `calb_diagrams/sld_pro_renderer.py` | 187 | `topology_v1` |

加上模式管道（插件分派、UI 选择器、`__init__` 导出、死掉的
`server_baseline_commit` 元数据字段）。**净减约 1.9k 行。**

### 关键设计：退役的模式名必须能优雅降级

`renderer_mode` 会写进**每一张 SLD artifact 的 metadata**。恢复旧 run、
外部提交、手改设置，都可能把 `"legacy_server"` 递回来。
如果 `normalize_sld_renderer_mode` 对它抛错，**旧的合法数据就变成了崩溃**。

所以模式名保留在 `RETIRED_SLD_RENDERER_MODES` 里并**映射到当前渲染器**；
只有真正未知的字符串才报错——那是调用方的 bug，不是历史记录，
这个区分不能丢，否则一个拼写错误会静默渲染出别的东西。

### 我删过界了一次，被测试逮住

第一遍连 `sld_layout_engine.py` 一起删了（以为它是 topology_v1 独占）。
**11 个测试文件集体报错**，其中包括 engineering_v2 自己的：
它的测试模块里有 `_build_topology` 夹具，被 **3 个活的 engineering_v2 测试文件**
导入，`SldLayoutSymbol` 还撑着 `test_symbol_library`。

**已恢复。** 为了一次清理去重写活测试是本末倒置 —— 这个文件现在只被测试用，
属于后续可清理项，但要先把夹具解耦。

### 测试的处置：逐个按其真实主题判断，不是一删了之

| 测试 | 处置 | 依据 |
| --- | --- | --- |
| `test_sld_busbar_groups_smoke` / `test_sld_pro_template_smoke` | **删** | 整体就是退役渲染器的 smoke |
| `test_mv_rmu_voltage_contract` | **保留 4/5 条** | 契约本身与 builder 由前 3 条覆盖；**第 4 条本来就用 engineering_v2 验的**；只删掉测退役渲染器兼容包装器的末条 |
| `test_sld_renderer_pure_render_only` | **保留 2 条** | 主体测 engineering_v2；只摘掉末尾两行对退役渲染器的断言 |
| `test_sld_renderer_mode_boundary` | 删 2 条 | 验的是"非 v2 渲染器拒绝三绕组"，渲染器没了规则也就不存在 |
| `test_sld_renderer_mode_service` | **重写** | 改锁新契约：唯一渲染器 + 退役名降级 + 未知名仍报错 |

### 回归基线：只动了一个键，且证明图没变

`render_baseline.json` 因 `server_baseline_commit` 消失而失配。
**没有整体重新生成**（那会掩盖别的变化），而是先逐键比对：

```
仅基线有的键: ['server_baseline_commit']
仅当前有的键: []
共有键中值变化: 无
metadata 之外的部分是否完全一致: True
```

**图纸逐字节未变**，只删掉那一个死字段。

### 验证

| 项 | 结果 |
| --- | --- |
| 全量测试 | **732 passed, 2 skipped** |
| 逐模块导入 | 205 个模块，失败 0 |
| 应用启动 | 健康检查 `ok` |
| SLD 页面真渲染（AppTest） | 无异常，提示 `Renderer mode: Engineering V2 Professional SLD.` |

---

## 四之九、清掉 sld/ 包里的取代品（owner「继续」，2026-08-06）

### 删了什么

| 模块 | 行数 | 依据 |
| --- | --- | --- |
| `sld/jp_pro_renderer.py` | 778 | 产品无消费者；`render_jp_pro_svg` 只被一个 smoke 测试调 |
| `sld/svg_pro_template.py` 之外的 `svg_postprocess` + `_margin` | 254 | 只被 `__init__` 再导出，`append_dc_block_function_blocks` 与 `add_margins` **零调用点** |
| `sld/visualizer.py` | 68 | 导入图不可达，只被一个测试调 |
| `calb_diagrams/sld_layout_engine.py` | 548 | `topology_v1` 退役后产品已无消费者 |

连同它们各自的测试。**净减约 1.6k 行**（本轮累计约 5.1k）。

### `sld_layout_engine` 这次是先解耦再删

上一轮它被恢复过一次 —— 它的测试模块里寄居着 `_build_topology`，
**三个活的 engineering_v2 测试文件从那里导入夹具**，一删就是 11 个模块无法收集。

这次的顺序：

1. 把 `_build_topology` / `_build_single_winding_topology` 抽到
   `tests/unit/sld_topology_fixtures.py` —— **夹具不该寄居在某个被测模块的测试文件里**，
   那正是"删一个退役模块会炸掉三个活测试"的成因；
2. `test_symbol_library` 原本借用退役引擎的 `SldLayoutSymbol` 当替身，
   **让一个活模块的活测试依赖了退役模块**。`draw_symbol` 是鸭子类型的，
   换成本地 `_Symbol` dataclass；
3. 两处解耦各自单独跑绿之后，才删模块与它自己的 9 条测试。

### 一个更大的发现（未动，需 owner 决定）

`calb_sizing_tool/sld/` 里还剩**一整套被取代的 pypowsybl / IIDM 技术栈**，
全部只挂在 `sld/__init__.py` 的再导出上或彼此互引，**产品代码零消费**：

| 模块 | 行数 | 模块 | 行数 |
| --- | --- | --- | --- |
| `svg_pro_template` | 644 | `snapshot_schema` | 169 |
| `iidm_builder` | 349 | `renderer` | 122 |
| `snapshot_single_unit` | 281 | `ac_block_group` | 88 |
| `snapshot_builder_v2` | 235 | `qc` / `topology` / `generator` | 186 |
| `snapshot_builder` | 173 | | |

**约 2.2k 行。** 佐证：`pypowsybl` **不在 `requirements.txt` 里**，
它唯一的两个测试（`test_sld_smoke` / `test_sld_raw_smoke`）**一直是 skipped 状态** ——
就是每次全量结果里那 2 条。

`sld/` 里真正活着的只有三个：`voltage_contract`、`transformer_vector_group`、
`standard_transformer_impedance`。

**没有动。** 这不是零散死代码，是一整套早期架构；退不退役是产品决定。

### 验证

| 项 | 结果 |
| --- | --- |
| 全量测试 | **721 passed, 2 skipped** |
| 逐模块导入 | 200 个模块，失败 0 |
| SLD 页面真渲染（AppTest） | 无异常 |

---

## 四之十、退役 pypowsybl / IIDM 栈（2026-08-06）

owner 在看过取证清单后说「继续」，据此退役。**`git revert c0669c0..` 可整体回退。**

### 删了什么

`calb_sizing_tool/sld/` 下 11 个模块，约 **2.2k 行**：

`svg_pro_template`(644) · `iidm_builder`(349) · `snapshot_single_unit`(281) ·
`snapshot_builder_v2`(235) · `snapshot_builder`(173) · `snapshot_schema`(169) ·
`renderer`(122) · `ac_block_group`(88) · `qc`(73) · `topology`(63) · `generator`(50)

**集群是闭合的**：这些模块只被彼此和 `sld/__init__.py` 的再导出引用，
产品代码零消费。删完 `sld/` 只剩三个真正活着的模块 ——
`voltage_contract`、`transformer_vector_group`、`standard_transformer_impedance`，
它们都被消费者**直接导入**，不经过包，所以 `__init__.py` 现在有意不再导出任何东西。

### 最有说服力的一条证据

那 2 条**常年 skipped** 的测试（`test_sld_smoke` / `test_sld_raw_smoke`）
正是这个栈的唯一测试 —— 它们从来没跑过，因为 `pypowsybl` 只在
`requirements_optional.txt` 里。**退役后全量结果的 skipped 归零。**

这个状态是最差的：**既没在用，也没在验**。

### 连带清掉的依赖足迹

| 位置 | 内容 |
| --- | --- |
| `requirements_optional.txt` | 整个文件（唯一内容就是 pypowsybl） |
| `requirements.txt` | `graphviz>=0.20.1` —— 唯一消费者 `visualizer` 已随上一步删除 |
| `packages.txt` / `Dockerfile` | 系统包 `graphviz`（`libcairo2` 留着，cairosvg 需要） |
| `common/dependencies.py` | `pypowsybl` 探测项 —— 报告一个用不上的库是噪声不是诊断 |

**镜像和安装都变小了**，而且不再暗示一个已不存在的能力。

### 一条活契约被保住了

`test_sld_builder_unification` 的 3 条里，有 1 条验的是
**「legacy 包装器与权威 topology 路径必须产出相同的 spec」** —— 活契约，与集群无关。
删除时它一度失败，因为同一条测试的后半段还在调用两个已退役的构建器。
**没有删掉整条测试**，而是摘掉后两段、保留这条断言，并在注释里写明摘掉了什么。

### 验证

| 项 | 结果 |
| --- | --- |
| 全量测试 | **721 passed, 0 skipped** |
| 逐模块导入 | 189 个模块，失败 0（`networkx` 的两个失败也随之消失 —— 它们正属于该集群） |
| 应用启动 | 健康检查 `ok` |
| SLD 页面真渲染 | 无异常 |

---

## 四之十一、report_v2 / dc_view 逻辑审查（owner「继续审核一下」，2026-08-08）

前十轮清的是**死代码**；这一轮查的是**逻辑缺陷**，对象是仅存的两个超大活文件：
`reporting/report_v2.py`（1797 行）与 `ui/dc_view.py`（1512 行）。
约束：owner 2026-08-08「DC SIZING 等公式坚决不能动」——本轮未触碰任何 sizing 公式，
冻结正典七个模块的哈希未变。

### 11.1 报告校验层是死的（owner 裁定：删）

`report_v2._validate_efficiency_chain` / `_validate_report_consistency` /
`_aggregate_ac_block_configs`、`report_context.validate_report_context`，
以及 `ReportContext.qc_checks` 字段——**产品代码零调用**。`qc_checks` 每次建报告都算，
无人读取。四个测试文件在测它们，制造了"有覆盖"的假象。

而且算术本身是错的：全部假设电站均匀（expected PCS = blocks × per_block，
total MW = blocks × block_size_mw），而 mixed governed 站故意用 HEAD 组的 per-block
数值配 SITE 级 rollup。实测 92 DC 用例（12 AC Block / 92 PCS / 115 MW，尺寸正确）：

```
AC total power (120.00 MW) does not match POI requirement (115.00 MW)
PCS module count mismatch: expected 96 (blocks x per_block), got 92
```

两条皆误报，且 120 MW 这个数在设计里不存在。`_aggregate_ac_block_configs` 声称按签名
聚合，实际永远返回一行，把 5 MW/4-PCS 尾块也计成 10 MW/8-PCS。

删而不修的理由：报告正文已经通过 §6 / §6.1 / §9 的 schedule 正确披露混合站
（读 `governed_groups` 与 `ac_block_breakdown`）；再养一套算错的平行逻辑没有价值。
输入校验留在上游 `dc_input_guard_service`——它**拦住**一次运行，而不是事后描述它。
顺带删掉随之失效的 `_parse_template_count` 及 `math` / `re` import。

### 11.2 DC 页面对同一 mode 跑了两遍 sizing（owner 裁定：改）

`show()` 原先为胜出的 mode 调用两次流水线：一次经 `dc_view.size_with_guarantee`
产出屏幕上的 tuple，一次经 `dc_pipeline_service.size_with_guarantee` 产出写库的
snapshot。同样输入的两次独立执行——结果一致，但**没有任何机制保证它一致**，
且页面最重的运算白跑一遍。

改法：每个 mode 只算一次 snapshot，显示用的 tuple 由 `snapshot_to_legacy_tuple`
从同一个 snapshot 派生。公式一行未动，只是不再重算。
写库的 snapshot 与改动前逐字节相同（bundle 仍带 `defaults=defaults`）。

### 11.3 已修的其余三项

| 位置 | 问题 | 处理 |
| --- | --- | --- |
| `dc_view._docx_add_lifetime_table` | 在**调用方的** Stage 3 DataFrame 上补缺失列；该 frame 是 `dc_results["results_dict"]` 里的活对象，导出报告会改写页面正在显示的结果 | 改为在副本上补（`a4a05bd`） |
| `dc_view.show()` 导出按钮 | 给游客也构建整份 DOCX，再丢弃换成"请登录"提示 | 先判身份，游客不构建 |
| `dc_view.show()` 运行按钮 | `bump_run_id_dc()` 在输入闸门之前，被拒绝的提交也消耗一个 run id | 移到闸门之后 |
| `product_admin_service.df_blocks_as_sizing_dataframe` | docstring 称"Convert active records"，实际返回全部 | 改正 docstring，并写明过滤由 `stage2_service.pick_dc_block` 独家负责（行为无害，已核实） |

### 11.4 新增测试

| 文件 | 锁住什么 |
| --- | --- |
| `tests/unit/test_report_export_does_not_edit_the_run.py` | 导出不得改写它所报告的运行结果 |
| `tests/unit/test_dc_page_sizes_each_mode_once.py` | tuple 与 snapshot 同源；AST 断言 `show()` 只调用一次流水线；并证明 `bundle.defaults` 不影响结果（即复用为何安全） |
| `tests/test_dc_page_run_smoke.py` | 已登录路径首次被真正按下 Run Sizing：持久化 + 导出按钮出现；被拒绝的运行不消耗 run id |

三者均做了**反向验证**：撤掉修复，对应测试失败。

### 11.5 验证

| 项 | 结果 |
| --- | --- |
| 全量测试 | **713 passed, 0 skipped**（721 → 707 删掉 16 个死校验测试 → 713 补回 6 个新测试） |
| 冻结正典 | 哈希未变，`test_frozen_canon_guard` 通过 |
| DC 页面真渲染 | 游客与已登录两条路径均经 AppTest 按下 Run Sizing，无异常 |

### 11.6 仍未处理（记录在案，未改）

报告在 SLD 读取失败被吞掉时仍写"SLD not generated"——措辞误导。属文案问题，
需 owner 决定改成什么口径。

---

## 五、尚未执行的两件事（均因**访问权限**受阻，非技术阻塞）

会话运行在 Anthropic 云上的隔离容器：**`ssh` 未安装**，出站仅一个 HTTPS 代理，
仓库内无任何服务器地址。owner 的 VPN 连在本人笔记本上，与本容器无路由。
下面两件必须由 owner 在自己的机器上执行。

### 5.1 开发机 `outputs/` 清理

```powershell
cd <项目根目录>
python -m alembic upgrade head
powershell -ExecutionPolicy Bypass -File scripts\clean_outputs.ps1          # 只看数字
powershell -ExecutionPolicy Bypass -File scripts\clean_outputs.ps1 -Delete  # 确认后删除
```

`scripts/clean_outputs.ps1` 把"先看数字再删"固化成了流程。
**开发机的库里有真实数据**，因此：

- **不要**加 `-GraceDays 0`，保留 7 天宽限期
- 若数出的数字接近 `outputs/` 全部文件，**停下别删** —— 那是连错库了

### 5.2 服务器升级（否则 `bfb36ac` 不生效）

```bash
cd /opt/calb-sizingtool/app
sudo bash deploy/scripts/calb-diagnose.sh                  # 先看现状（只读）
sudo bash deploy/docker/calb-serverctl.sh update           # 升级，收尾自动校验版本
sudo bash deploy/docker/calb-serverctl.sh version          # 随时可单独复查
```

`update` 结束会自动打印版本三方比对（checkout / GitHub / 运行中的镜像），
并提示"同一串内容显示在 Web 页面左侧导航栏最底部"，照着核对即可。
诊断脚本第 4 节会打印容器内的实际环境变量：**列表为空 = 该容器早于
2026-08-06，清扫在用内置默认值** —— 脚本会把这句话直接印出来，
而不是让一次"看起来正常"的运行蒙混过关。

> **注意**：升级后侧边栏若仍显示 `dev`，说明镜像是用 `docker compose` 直接构建的，
> 没走 `calb-serverctl.sh` —— 构建参数只在该脚本里注入。


---

## 六、给审阅者的复核清单

```bash
# 1) 冻结正典未动
git diff --name-only 1f053b7..HEAD | grep -E "ac_sizing_service|dc_pipeline_service|common/ac_block|common/allocation"

# 2) 产品代码改动规模（其余为测试与文档）
git diff --stat 1f053b7..HEAD

# 3) 全量测试
python -m pytest tests/ -q

# 4) 单方案（常态）路径未被改变
python -m pytest tests/unit/test_report_ac_alternative_versioning.py -q

# 5) 清扫的安全边界
python -m pytest tests/unit/test_maintenance_service.py -q

# 6) 无已跟踪文件被新 gitignore 误伤（应无输出）
git ls-files | git check-ignore --stdin
```

**重点复核建议**（这几处最值得挑毛病）：

1. `_refresh_alternative_snapshots` 补写 input 行时保留身份哈希 ——
   若此处判断有误，会导致方案变孤儿并产生重复 Run。
2. `prune_unreferenced_artifact_files` 的"注册表读不出来就不删" ——
   这是唯一挡住"误删全部 artifact"的护栏。
3. `resolve_preferred_ac_snapshot` 中"选到别的 DC Run 的分支要拒绝" ——
   陈旧选择不能偷渡外来配置。
4. `list_child_runs` 次序键的必要性 —— 关系到已发出报告的方案名是否稳定。

---

## 七、CI 测试依赖收口（2026-08-06，Codex）

本轮维护参数的 compose 契约测试最初直接导入 `yaml`，但 PyYAML 不在
`requirements.txt` 或 CI 的测试依赖中。GitHub Actions 因此在测试收尾阶段报
`ModuleNotFoundError: No module named 'yaml'`；应用代码与维护逻辑本身没有失败。

该测试的目标只是锁住 app 容器中的七个精确环境变量映射及其安全默认值，不是
验证 YAML 解析器。因此已改为标准库文本契约断言：每个变量必须以预期缩进、名称和
默认值出现在 `services.app.environment` 中，且删除开关仍为空默认值。这样本地与 CI
都无需隐式依赖，并避免为了一个测试把 PyYAML 加进生产容器。

### 本地清理脚本的 P0 安全修复

复核 `clean_outputs.ps1` 后发现其“未带 `-Delete` 不改动”的说明与实现不一致：
测量阶段虽禁用了未引用文件删除，但维护入口仍会删除过期 artifact 行、快照、审计行
和 oplog。现已增加 `maintenance_service --dry-run`：它计数每项保留策略的候选对象，
但绝不删除数据库行或文件；本地脚本的测量阶段显式传入该参数，`-Delete` 才运行现有
的正式保留策略。服务器的定时任务不传该参数，保持原定的正式清理行为。
