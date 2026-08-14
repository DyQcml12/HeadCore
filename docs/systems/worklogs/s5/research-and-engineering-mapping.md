# S5 人格管理研究与工程映射

日期：2026-07-14

## 参考来源

1. Bai et al., [Constitutional AI: Harmlessness from AI Feedback](https://arxiv.org/abs/2212.08073)：将不可被普通人格配置覆盖的系统安全原则视为高优先级 constitution。
2. Ouyang et al., [Training language models to follow instructions with human feedback](https://arxiv.org/abs/2203.02155)：发布前使用离线评估和人工审批，而不是把草稿直接投入生产。
3. Open Policy Agent, [Policy Language](https://www.openpolicyagent.org/docs/policy-language)：策略输入与策略判定分离；S5 将绑定上下文与优先级解析保持为纯函数。
4. Unleash, [Activation strategies](https://docs.getunleash.io/reference/activation-strategies)：借鉴按环境和上下文逐层选择配置的做法，形成人格绑定作用域。
5. Kubernetes, [Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)：版本对象不可变，发布、替换和回滚以独立审计事件表达。

## 工程映射

| 研究或实践 | S5 实现 |
| --- | --- |
| 高优先级安全原则 | `SYSTEM_REQUIRED_GATES` 与人格请求 gate 分离；缺失任何系统 gate 时拒绝审批 |
| 发布前评估 | 草稿必须通过 schema、gate 和 regression 才能审批为不可变版本 |
| 策略输入与判定分离 | `BindingContext`、`PersonaBinding` 和 `resolve_binding()` 均为独立 typed contract/纯函数 |
| 上下文定向配置 | `conversation > profile > relationship > platform > global` |
| 不可变版本与审计事件 | frozen dataclass；version、release 分离；supersede、rollback、archive 保留历史 |

## 本阶段边界

- 只实现后端领域契约、内存 fake 和只读 runtime projection，不提供 API/UI。
- 不保存完整 prompt 或私密记忆。
- 不直接接入现有 registry、prompt builder 或 ChatService。
- live acceptance 作为公开验证结果类型保留；真实模型验收由集成阶段使用现有 adversarial runner 执行。

