# S4 记忆与画像生命周期实现测试报告

日期：2026-07-14  
结果：PASS

## 实现范围

- typed contract：candidate、record、portrait patch、decision、projection、audit event。
- 生命周期：candidate、active、superseded、revoked、expired、deleted。
- 策略：blocked、长期记忆权限、低质量观察、跨 profile 写入、管理员/关系变更。
- scope 投影：admin private、profile private、persona specific、safe preference。
- Repository Protocol、并发保护的内存 fake、追加式审计。
- 冲突 review 与显式 supersede、撤销传播、UTC 过期边界。

## 执行环境

- Python：`D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`
- pytest：项目既有环境
- 未安装新依赖，未修改 C 盘或系统环境。

## 验证结果

1. 语法检查

   `python -m compileall -q app\knowledge tests\knowledge`

   结果：PASS。

2. S4 聚焦测试

   `D:\Tool\Progrmming-Tool\anaconda\python.exe -m pytest tests\knowledge -q -p no:cacheprovider`

   结果：`9 passed in 0.05s`。

3. S4 与相邻 memory/Database V2 回归

   `D:\Tool\Progrmming-Tool\anaconda\python.exe -m pytest tests\knowledge tests\test_persona_memory.py tests\test_database_v2.py -q -p no:cacheprovider`

   结果：`91 passed in 0.64s`。

4. 项目全量回归

   `D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe -m pytest tests -q -p no:cacheprovider`

   结果：`429 passed in 12.43s`。

## 覆盖的验收场景

- candidate 审批为 active，保留 source 和 confidence。
- 冲突在未显式授权时进入 review，授权后旧记录 superseded。
- revoke 后 projection 立即不可见，重复非法转换被拒绝。
- scope/relationship/persona 权限矩阵。
- `expires_at` 前一微秒仍有效，到达边界即 expired。
- 多账号同 profile 共享，不同 profile 隔离。
- blocked 和低质量多模态观察不可进入 active。
- 未验证用户不能自行改变关系或管理员身份。
- projection 不暴露原始 `source_id` 与 `source_type`。

## 已知集成边界

- 未接入 ChatService、现有 memory service、FastAPI、QQ 命令或真实数据库。
- Database V2 adapter、事务和并发激活约束见 `integration-notes.md`。
- README 与 AGENTS 属于并行开发冻结文件，本次不直接修改；集成人员应按 integration notes 登记。
