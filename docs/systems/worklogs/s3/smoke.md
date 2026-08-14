# S3 可选真实 Smoke

真实 smoke 不属于单元测试，不会自动安装模型或发起下载。

```powershell
& 'D:\Tool\Progrmming-Tool\anaconda\python.exe' -m app.perception.smoke --audio D:\path\sample.wav --device cpu
```

结果语义：

- `PASS`：真实 ASR 返回了通过管线的 observation。
- `FAIL`：输入存在，但 provider/模型/结果失败；JSON 会给出非敏感错误码。
- `SKIP`：输入文件不存在，明确报告 `audio_file_missing`。

视觉真实 smoke 当前不执行：项目记录显示 Ollama 未注册视觉模型。S3 不允许安装或注册模型，因此应明确记为 `SKIP: model_not_registered`，待集成人员配置真实模型后再通过 S6 provider health 执行。

