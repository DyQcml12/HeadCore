# S3 多模态感知研究与工程映射

调研日期：2026-07-14

## 资料

1. Radford et al., *Robust Speech Recognition via Large-Scale Weak Supervision* (Whisper), 2022: https://arxiv.org/abs/2212.04356
   - 工程映射：ASR 输出不直接等同于事实；保留语言、置信度、质量与 provider trace。
2. Radford et al., *Learning Transferable Visual Models From Natural Language Supervision* (CLIP), 2021: https://arxiv.org/abs/2103.00020
   - 工程映射：视觉语义是模型观察而非确定事实，统一为带来源和置信度的 observation。
3. Liu et al., *Visual Instruction Tuning* (LLaVA), 2023: https://arxiv.org/abs/2304.08485
   - 工程映射：VLM 自由文本必须经过归一化和质量门，不允许失败时伪造描述。
4. FunASR: https://github.com/modelscope/FunASR
   - 工程映射：复用项目已有 `FunAsrFileEngine`，adapter 同时兼容字符串和结构化结果。
5. PaddleOCR: https://github.com/PaddlePaddle/PaddleOCR
   - 工程映射：OCR 被视为独立观察源；与 VLM 内容冲突时标记 `conflicted`，禁止自动写入确定记忆。
6. Ollama API: https://github.com/ollama/ollama/blob/main/docs/api.md
   - 工程映射：模型缺失、连接失败和超时进入结构化 trace；S3 不安装或注册模型。
7. OWASP SSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
   - 工程映射：只允许 HTTP(S)，拒绝凭据 URL、localhost 和非全局字面 IP；实际下载器仍须在 DNS 解析后及每次重定向时复验目标地址。

## 决策

- Observation 是可审计的感知结果，不是事实声明。
- `good` 且置信度不低于 0.6 才能得到 `memory=allow`；未提供置信度按未知值 `0.0` 处理。
- 低置信度、质量降级或 provider 冲突统一为 `review`；失败或空内容为 `deny`。
- provider 异常只保留脱敏错误和受控错误码，不生成替代内容。
- 用户附件只作为数据读取；S3 不执行附件、宏、脚本或嵌入式主动内容。
