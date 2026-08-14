# S2 统一平台事件系统测试报告

日期：2026-07-14

## 测试环境

- Python：`D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe`
- 工作目录：`D:\Programming-file\Graduation-Project\HutaoChatCore`

## 已执行检查

### S2 聚焦测试

```powershell
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m pytest tests/channels -q
```

结果：`12 passed`。

覆盖范围：

- 契约 JSON 往返兼容和平台大整数 ID 字符串化；
- 时间戳时区约束和事件载荷不变量；
- OneBot 私聊、群聊、引用、撤回、图片、语音、文件和未知 segment；
- URL/token 不进入附件安全契约；
- Core API 平台身份和内部身份回退；
- QQ、Weixin、Core API capability matrix；
- Weixin 缺失能力的稳定降级和明确不支持结果。

### QQ 回归测试

```powershell
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m pytest tests/test_qq_bot.py -q
```

结果：`81 passed`。

### 编译检查

```powershell
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' -m compileall -q app/channels tests/channels
```

结果：PASS。

### 项目标准全量测试

```powershell
& 'D:\Tool\Progrmming-Tool\anaconda\envs\new\python.exe' scripts\run_tests_with_md_log.py --module all
```

结果：`429 passed`，PASS。

生成报告：`logs/test-runs/2026-07-14_174056/all/all.test-report.md`。

## 已知环境提示

pytest 报告既有 `.pytest_cache` 路径拒绝写入警告。测试收集和执行均成功，该警告不影响结果。本次没有修改或删除该目录。

项目标准运行器只收集 `tests/`，全量 429 项均通过。
