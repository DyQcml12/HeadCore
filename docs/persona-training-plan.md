# 胡桃人格训练路线

## 结论

当前不建议直接训练一个模型替代现有链路。

更稳的路线是：

1. 继续用 DeepSeek + prompt + 记忆 + 门禁作为主链路。
2. 先沉淀高质量人格样本和失败样本。
3. 导出微调候选 JSONL。
4. 用固定人格回归集评估。
5. 指标稳定后，再考虑微调或蒸馏。

## 直接训练会怎么样

优点：

- 角色语气可能更稳定。
- prompt 可以变短，延迟和 token 成本可能下降。
- 常见场景不需要每次塞大量规则。

风险：

- 数据不够时会过拟合，变成固定话术。
- 坏样本会被学进去，比 prompt 更难修。
- 胡桃这种 IP 角色不能直接抓官方台词或同人语料硬训，必须确认数据来源许可。
- 训练后仍然需要记忆、撤销、门禁和场景规则；模型不会自动知道用户刚撤销了什么。
- 如果底座模型换代，微调模型可能落后于新底座能力。

## 数据格式

候选数据采用 chat JSONL：

```json
{"messages":[{"role":"system","content":"..."},{"role":"user","content":"少说点。"},{"role":"assistant","content":"好，收声。"}]}
```

当前脚本：

```powershell
D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe scripts\export_persona_finetune_dataset.py
```

输出：

- `data/fine_tune/<timestamp>/train.jsonl`
- `data/fine_tune/<timestamp>/validation.jsonl`
- `data/fine_tune/<timestamp>/manifest.json`
- `data/fine_tune/<timestamp>/dataset-report.md`

## 开训门槛

开训前至少需要：

- 200 条以上人工认可的单轮短回复样本。
- 50 条以上多轮样本，覆盖纠正、撤销、短回复偏好、debug、项目、严肃生死话题。
- 50 条负样本说明，标注为什么不像胡桃。
- 固定回归测试通过：真实长聊、流式输出、记忆撤销、职业梗场景允许度。

## 推荐训练阶段

### 阶段 1：样本库

先做人工可读的 `persona_training_seed.json`，只放确认过的短回复。

### 阶段 2：蒸馏候选

用当前通过门禁的 DeepSeek 输出作为候选，但必须人工抽检，不能直接全量纳入。

### 阶段 3：微调

如果供应商支持 fine-tuning，则上传 `train.jsonl` 和 `validation.jsonl`。
训练后不能直接上线，必须跑当前全部人格测试。

### 阶段 4：A/B 对比

同一批用户输入分别跑：

- 当前 prompt 链路
- 微调模型链路

比较：

- 是否更短
- 是否更像胡桃
- 是否更少兜底
- 是否更少乱用职业梗
- 是否仍尊重记忆撤销

## 当前判断

现在最有价值的不是马上训练，而是继续积累可控样本。
当样本量不足时，直接训练大概率只会把“短、俏皮、别话痨”学成几个模板。
