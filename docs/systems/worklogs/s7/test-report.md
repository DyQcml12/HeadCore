# S7 表达计划系统测试报告

日期：2026-07-14

## 环境

- 工作目录：`D:\Programming-file\Graduation-Project\HutaoChatCore`
- Python：`D:\Tool\Progrmming-Tool\anaconda\python.exe`
- 完整项目环境：`D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`
- 当前默认 `C:\Python314\python.exe` 没有 pytest，因此未用于执行测试。

## 聚焦测试

命令：

```powershell
& 'D:\Tool\Progrmming-Tool\anaconda\python.exe' -m pytest tests/expression -q
```

结果：`13 passed`。

覆盖 owner-only voice、群聊语音降级、provider/平台能力、TTS 回退、文本语音去重、表情 cooldown、附件降级、平台 segment limit、受控绝对路径以及现有 QQ dialogue decision 映射。

## 相关回归

命令：

```powershell
& 'D:\Tool\Progrmming-Tool\anaconda\python.exe' -m pytest tests/test_dialogue_policy.py tests/test_qq_bot.py -q
```

结果：`88 passed, 1 failed`。

失败：`test_qq_preflight_module_check_sees_nonebot`。当前 Anaconda 测试解释器无法导入 `nonebot`。该检查不执行 S7 代码，其余 dialogue/QQ 表达行为均通过。未为消除环境失败而安装依赖或写入 C 盘。

两次测试均出现现有 `.pytest_cache` 拒绝写入警告，不影响用例执行结果。

## S2/S6/S7 契约集成测试

命令：

```powershell
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m pytest tests/expression tests/channels tests/providers -q
```

结果：`57 passed`。

新增覆盖：

- S2 private/group event 到 S7 delivery context；
- QQ native voice 与 Weixin audio attachment 的差异化转换；
- S6 TTS capability 与 provider health 组合；
- ready voice 不重复输出文本；
- provider/channel 状态变化后的稳定文本回退和最终能力校验。

### 最终 S7 与 QQ 回归

```powershell
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m pytest tests/expression -q
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m pytest tests/test_qq_bot.py -q
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m compileall -q app/expression tests/expression
```

结果：S7 `24 passed`；QQ `81 passed`；编译检查 PASS。完整项目环境中的 NoneBot 检查正常通过。

## QQ 运行时集成回归

```powershell
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m pytest tests/expression tests/test_qq_bot.py -q
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' scripts\run_tests_with_md_log.py --module all
```

结果：S7/QQ `106 passed`；项目标准全量 `515 passed`。全量报告：`logs/test-runs/2026-07-14_222000/all/all.test-report.md`。

运行时回归额外覆盖 TTS 产物越过配置输出根目录时拒绝语音并回退文本。

## Core API 运行时集成回归

```powershell
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m pytest tests/expression tests/test_api.py -q
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' scripts\run_tests_with_md_log.py --module all
```

结果：expression/API `43 passed`；项目标准全量 `543 passed`。全量报告：`logs/test-runs/2026-07-14_231549/all/all.test-report.md`。

覆盖普通文本、V2 预处理文本、流式 chunk/空白保持、非文本 bundle 拒绝以及现有 OpenAI-compatible/Hermes 行为。

## 2026-07-15 表达契约完整性复核

本轮完善了以下边界：

1. 请求 sticker 但没有 asset id 时产生明确 `sticker_asset_missing` fallback，不再静默不发送。
2. `voice_format` 限定为 `wav`、`mp3`、`ogg`、`opus`，并在 contract 入口规范化大小写与空白。
3. TTS fallback detail 只保留短小的机器原因码；异常文本、token、路径等自由文本不进入
   `ResponseBundle`。
4. `VoicePlan.READY` 必须携带绝对路径，其他状态禁止携带 output path。
5. 只有 READY voice 可以设置 `suppress_display_text`，防止手工 bundle 静默丢失文本。

曾验证“READY 前要求文件现场存在”，但现有 QQ adapter 的公开测试契约以
`VoiceSynthesisResult.send_path` 作为合成成功凭据，fake adapter 不实际落盘。为保持现有行为，
最终边界仍为：S7 强制绝对受控路径，文件生成与真实性由 TTS adapter 负责。

最终验证：

- `compileall app/expression tests/expression -q`：PASS。
- S7 聚焦测试：当前范围 `30 passed`。
- S2/S6/S7 核心联合回归：`66 passed in 0.34s`。
- S7、QQ、Core API 相邻回归：`131 passed in 6.83s`。
- 项目标准全量测试：`565 passed, 1 skipped in 13.54s`。

联合测试期间曾观察到一次并行 S3 视觉 observation 尚未映射的失败；随后全量测试通过，
本轮没有跨 S7 独占范围修改 perception 或 QQ vision 实现。
