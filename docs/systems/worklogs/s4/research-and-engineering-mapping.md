# S4 记忆与画像生命周期研究映射

日期：2026-07-14

## 参考资料

1. Park et al., *Generative Agents: Interactive Simulacra of Human Behavior* (UIST 2023)  
   https://arxiv.org/abs/2304.03442
2. Packer et al., *MemGPT: Towards LLMs as Operating Systems* (2023)  
   https://arxiv.org/abs/2310.08560
3. Letta documentation, memory concepts and archival memory  
   https://docs.letta.com/
4. Zep documentation, temporal knowledge graph and memory  
   https://help.getzep.com/

## 工程映射

| 研究/项目机制 | S4 映射 | 采用边界 |
| --- | --- | --- |
| Generative Agents 的观察来源、重要度与检索 | `source_type/source_id`、`confidence`、观察质量门槛 | 本阶段不实现向量检索或反思生成 |
| MemGPT/Letta 的分层记忆与显式管理 | `MemoryScope`、候选审批、active projection | 不允许模型直接覆盖长期记忆 |
| Zep 的时间有效性与事实演进 | `expires_at`、`superseded`、显式冲突事件 | 不引入图数据库或外部网络服务 |
| 数据最小化原则 | `MemoryProjection` 不含原始 source id/type | prompt 不读取私密原始记录 |
| 可撤销性和可追责性 | revoke/delete/expire 状态及追加审计事件 | 不物理擦除审计；真实删除策略由数据库集成决定 |

## 本地安全决策

- blocked profile、无长期记忆权限主体和低质量观察在候选入口即拒绝。
- 未验证用户提出的关系或管理员身份变化只进入 review，不能自行生效。
- 冲突事实不会静默覆盖；需要显式 `supersede_conflicts` 决策。
- 账号仅作为行为主体信息，记忆所有权使用 `profile_id`，因此多账号绑定后共享、不同 profile 隔离。
- 投影按 admin/profile/persona/safe preference 四类 scope 执行本地权限判断。
