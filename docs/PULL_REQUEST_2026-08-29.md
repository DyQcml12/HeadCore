# PR：提升官网动态交互并修复控制日志读取

## 概要

本 PR 在不开放公网、不重新启用视觉模块的前提下，提升 HutaoChatCore 官网的动态反馈、可操作性与无障碍行为，并修复控制中心服务日志路径不一致的问题。

## 主要变更

- 增加页面滚动进度、滚动后导航收缩、当前章节高亮和返回顶部按钮。
- 将认知处理链路改为可点击、键盘可操作、可暂停自动演示的交互组件。
- 增加步骤展开详情、ARIA 关联、移动菜单焦点约束和背景滚动锁定。
- 保留 Three.js 粒子场、GSAP reveal 和卡片指针倾斜；触屏与减少动态模式自动降级。
- 移除官网对视觉能力的当前可用描述，保持视觉模块封存边界。
- 统一控制日志文件名：`core_api.log` 与 `gpt_sovits_api.log`。
- 增加可版本化开发日志，并记录 DeepSeek Harness 的真实协作边界。

## DeepSeek Harness 协作

DeepSeek Harness 会话“为官网交互契约补充测试”只修改了 `tests/test_public_site.py`，新增 4 组生产构建契约测试。生产交互、视觉实现、浏览器验证、Git 分支和提交由 Codex 完成并复核。

## 验证

- `npm.cmd run build`
- `python -m pytest -q -p no:cacheprovider tests/test_public_site.py`：7 passed
- `python -m pytest -q -p no:cacheprovider tests/test_control_log_reader.py`：1 passed
- Edge + Playwright：1440x900 与 390x844 均无控制台错误和横向溢出
- 已验证章节高亮、步骤展开/暂停、ARIA 关联、移动菜单焦点约束和返回顶部交互

## 已知提示

- Vite 对约 705 KB 的 Three.js 动态模块给出包体提示。该模块按需加载，不阻塞首屏主包。
- FastAPI 现有 `on_event` 使用会产生弃用警告，与本 PR 无关。

## 安全与部署

- 未添加密钥、凭据、遥测或新的公网请求。
- 当前服务仍只面向本机运行；本 PR 不包含公网部署配置。
