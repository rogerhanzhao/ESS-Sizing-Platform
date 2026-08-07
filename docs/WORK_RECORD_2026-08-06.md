# 执行记录与状态（2026-08-06）

**用途**：供 owner 与其他审阅者（含 CODEX）核对本轮改动。每一条结论都给出
**可自行复现的验证方式**，不要求相信本文——请直接跑验证命令。

**分支**：`ops/ubuntu-docker-coexist-20260311`（未新建分支）
**基线**：`1f053b7` → 分支末端，共 8 次提交
**测试**：起始 633 passed / 2 skipped → **末端 684 passed / 2 skipped**
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

配套：AC 页面保存成功后 `set_active_ac_run(新方案, clear_downstream=False)`。
`clear_downstream=False` 是必须的 —— 此时 session 里装的**就是**这个方案的结果。

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
