# S3 多模态感知系统测试报告

日期：2026-07-14

解释器：`D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`

## 结果

| 检查 | 结果 |
| --- | --- |
| `python -m compileall -q app/perception` | PASS |
| `python -m pytest tests/perception -q` | PASS，27 passed |
| `python -m pytest tests/test_audio_pipeline.py -q -p no:cacheprovider` | PASS，19 passed |
| `python -m pytest tests/test_qq_bot.py -q -k "vision or ocr or image"` | PASS，15 passed，67 deselected |
| `python -m compileall -q app/perception tests/perception` | PASS |
| 缺输入的可选真实 smoke | SKIP，`audio_file_missing`，符合预期 |
| 项目标准 Markdown 全量测试 | FAIL，513 passed，1 个 QQ TTS 回归失败 |

全量报告：`logs/test-runs/2026-07-14_221848/all/all.test-report.md`。

唯一失败为 `tests/test_qq_bot.py::test_qq_voice_reply_builds_record_part_when_tts_succeeds`：预期 voice record，实际回退到 text。该用例不调用 `app/perception`，且修改 `integrations/qq_bot/voice_reply.py` 超出 S3 独占范围，因此本次没有越界修复。

## 覆盖

- ASR string/object 返回兼容。
- 空音频、超大图片、错误 MIME、私网/凭据 URL。
- provider 模型缺失、超时、fallback trace 与错误脱敏。
- OCR/VLM 冲突及视觉 fallback。
- S2 attachment 与 S6 trace 映射。
- 现有 QQ `VisionObservation` 到统一 observation 的兼容归一化。
- `allow/review/deny` 记忆资格矩阵。
- 缺少真实 smoke 输入时的明确 SKIP。

## 环境说明

pytest 仍报告既有 `.pytest_cache` 路径拒绝写入警告，不影响测试执行。本次未安装或修改任何依赖。
