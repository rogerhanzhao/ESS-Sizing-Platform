# DC场景比较、活动结果与下游交接修复

范围：DC/AC网页、恢复摘要适配与持久化失败保护。冻结场景计算、优先级、阈值、SOH/RTE及AC柜分组语义不变。

## 实际问题

1. Enable Cabinet-Only Mode勾选只是将柜场景加入计算，Container Only始终计算；二者都是互不排斥的比较路径。旧标签容易被理解为排他选择。
2. 活动方案采用first_success_key及原优先级Hybrid→Cabinet→Container，但st.tabs只是浏览控件，不能更改活动方案。原页签无角色标记，重算仍可能保留先前查看位置。
3. 48×0.418=4×5.016=20.064MWh，两种方案铭牌相同，光看容量无法判断方案。用户本例保存的确为cabinet_only，48柜、0箱，不是算术把柜变箱。
4. 历史恢复build_dc_result_summary缺mode字段，虽然数量及stage13有依据，但恢复摘要与新计算摘要不一致。
5. AC页面将任何cabinet_count>0描述为hybrid tail，纯柜同样会被误标。
6. 保存失败或保存后恢复失败仍可能进入后续结果打包，造成新显示值与旧/无持久化运行的交接不一致。

## 修复

- 保留checkbox状态键与场景算法，标签改Include ... comparison，解释Container始终计算及当前场景优先级。
- 活动结果数量/类型持续显示；标签区分Active for AC / SLD与Comparison only；活动结果排首并设置default，不把浏览页签作为方案选择器。
- 历史显示同样标明活动模式及柜箱数，摘要补回快照mode。
- 纯柜AC说明独立于hybrid，明确当前AC仍以物理柜计数。十柜母线组自动AC尚未激活，不把本轮UI修复当作已批准该架构升级。
- 保存未取得run_id、恢复失败或持久化异常时停止当前交接展示，不把未保存的新结果标为活动结果或显示继续按钮。

## 验证

新增AppTest：柜模式运行→活动页签→保存→新会话恢复到AC，核对模式、柜箱数及没有hybrid尾柜误标；持久化返回空结果时没有活动成功提示/继续入口。既有恢复测试保证无重新计算和无再次写库。

真实Chrome在本地test/11原输入8MW/16MWh、保证年5、S&C3月上复核，仍为48柜、0箱、20.064MWh；新运行默认柜活动页签、集装箱标为Comparison only。AC收到48物理柜、0箱，纯柜说明正确。截图与DOM：output/local_web_20261017_human/cabinet-active-fixed.*、ac-cabinet-handoff-fixed.txt。

没有加入点击页签即可替换活动方案的行为；将比较方案提升为活动运行需要独立的受控保存流程，不通过静默切换改变原合同。没有把48柜变成5个同质DC组，也没有上线柜级自动AC。

本地修复，不部署生产。完整回归结果在完成后补记。

最终验证：compileall通过；全套806 passed（269.93秒），包括7个冻结模块守卫。diff --check通过。外部Chrome已登录并恢复最新48柜方案，停留DC结果页，见cabinet-restored-fixed.png；原参数新计算与AC页面交接已在同一本地环境实际点击验证。模块职责未跨域迁移，不修改模块地图；未提交或部署生产。
