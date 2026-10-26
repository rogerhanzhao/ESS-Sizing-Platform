# D1a：逐箱、逐输出域的 AC 连接校验（本地）

主线继续是314Ah / 416S / 20ft的12簇主箱加一个10簇或8簇尾箱。D1a已实现独立的显式连接合同与诊断，不替换旧的DC/AC公式、1:1–1:8分组页面或SLD生成器。尚未开放新组合的正式采用、图纸和报告。

## 1. 本轮执行顺序

先复验C2b及标准路径：299项通过，107.95秒；冻结七模块及`calb_diagrams/`无差异。通过后开始D1a。

新增职责如下，均为默认流程以外的本地接口：

| 模块 | 职责 |
|---|---|
| `schemas/dc_ac_allocation.py` | 严格版本1连接合同；拒绝未知字段、类型强转及含糊设备身份 |
| `services/dc_ac_allocation_source_service.py` | 绑定已保留C2b比较SHA，重验当前产品/父子关系，重建BOM并重算DC duty |
| `services/dc_ac_allocation_topology.py` | 纯连接、完整性、物理边界与母线冲突校验 |
| `services/dc_ac_allocation_service.py` | 前后来源复验、DC功率逐端口/PCS/绕组/AC Block归集与诊断签名 |
| `ui/dc_ac_allocation_review_view.py` | 英文、无Arrow的独立结果展示；不改变当前运行或原页面路由 |
| `scripts/rehearse_dc_ac_allocation.py` | 在新建output目录生成独立SYNTHETIC库及正常/异常场景，不读写生产 |

## 2. 连接合同

`dc_ac_allocation_v1`包括：源manifest与comparison签名；AC Block、PCS、输入端口、变压器及LV绕组注册表；物理箱体所属AC Block；每个DC域接入哪个PCS端口；每台PCS接入哪个变压器绕组。

输入端口明确DC bus身份，绕组明确LV bus身份。数量和连接均显式给出，不从簇数推输出路数，不用平均箱数代替异构设备。全部设备必须有连接；本阶段不注册备用空置设备。

校验拒绝：缺失/额外/重复箱体与输出域、一个域多重连接、同箱跨AC Block、不同PCS共享DC bus、不同绕组/变压器共享LV bus、PCS与变压器不属同一AC Block、未知端口/绕组及闲置注册设备。每台PCS只接一个明确LV绕组。

同一PCS接多个域即使带有并联证据引用，仍保持适用性待核实。设备包的code/revision/hash/evidence只作引用，不能凭任意JSON的存在、Active、Published或文字说明获得兼容批准。

## 3. 源结果与过期检查

调用方必须提供独立保留的`expected_comparison_sha256`，不能默认从上传对象自身提取。校验用C2b原有JSON规则重算内容SHA；内存Pydantic结果与JSON下载再载入保持一致。

随后用当前产品修订和父子关系重建相同顺序的BOM、显式输出分区及scope，并比较整个manifest。重新计算完整DC dispatch，不能只验证dispatch输入hash后信任可变的逐箱输出。连接校验完成后再做一次来源复验，发现期间修改或撤回审核则拒绝返回结果。

SHA是版本/内容一致性检查，不认证厂家批准。D1a重新验证当前DC产品及配置关系；曲线适用证据继承自已保留C2b比较，未再次认证曲线审批生命周期。两个检查点也不构成事务式工程发布。

## 4. 有意分开的结果

| 结果字段 | 含义 |
|---|---|
| `topology_valid` | 声明的连接完整、无已知物理边界冲突；不等于厂家拓扑适用批准 |
| `dc_duty_status` | 原清单逐箱、逐域的声明DC放电限制检查 |
| `source_energy_requirement_met` | 被绑定的C2b比较是否满足保证年POI能量 |
| `discharge_feasibility_status=not_evaluated` | 尚未评估完整PCS/变压器能力及AC交付 |
| `downstream_ready=false` | 不能正式采用或进入SLD/Layout/技术方案 |

端口、PCS处显示`requested_dc_discharge_kw`。绕组和AC Block处只显示`upstream_dc_reference_kw`，用于检查同一来源DC功率有没有遗漏/重复；不是AC输出、变压器kVA或绕组负载率。不会把域直流电流相加成绕组交流电流。

正常SYNTHETIC示例：一台12簇加一台10簇，在2,000kW DC参考下各承担1,090.91和909.09kW；各接一个独立PCS，接到同一明确LV绕组，归集2,000kW。这个示例未提供PCS/变压器额定数据，所以能力结论始终pending。把10簇箱的声明限制改为400kW后，即使能量满足、全站声明总功率足够且拓扑有效，也必须报DC限制失败。

## 5. 本地验收

新机制全部使用SYNTHETIC参数、曲线、证据引用和隔离数据库，不能用于客户保证。浏览器验证页为loopback端口8525，原8523工程草案页与原Sizing页面均保留。

已建立正常、尾箱功率不足、跨PCS共DC bus、同箱跨AC Block、跨LV绕组共bus及缺失显式输出六类演练。四个新演练库的`integrity_check=ok`，无FK错误。自动检查另覆盖当前性撤回、来源篡改、JSON往返、畸形输入、逐层守恒及不写当前运行状态。

最终全量回归1,614项通过（404.45秒），其中本轮新增141项；编译、差异及冻结模块/原制图模块检查通过。浏览器六类场景逐一点击复核，下载诊断后预览保留；页面使用英文及两位小数功率表，无数据库UUID/签名串。当前原库只读检查仍为0010版本、完整性ok，16条历史FK异常另行保留，不作全库健康通过结论。

完整测试与边界记录见`output/flexible_dc_phase_d1a_20261021/validation-result.json`。本轮无源库/生产库迁移、产品激活、GitHub推送或部署。

## 6. 后续顺序

下一步D1b补独立版本化PCS/变压器能力包：每输入端口及整机电压/持续电流/充放电功率、独立/共母线适用条件、各LV绕组容量与电压、总kVA、向量组、P/Q和温度工况。新能力审核资格不能借用旧目录匹配的`engineering_data_status=complete`。

能力验证器稳定后进入D2有界推荐，每个自动方案共同调用同一连接及能力验证器。D3接正式采用身份、过期图纸失效；最后E提供专用异构SLD/Layout/报告适配，原5MWh引擎继续保留。
