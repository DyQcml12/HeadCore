# QQ 与微信 Bot 归档说明

> 状态：2026-07-25 起停止作为主产品方向开发。

## 决策

HuTaoChatCore 的正式方向调整为 Web、PWA、桌面 App、移动 App、微信小程序和 HeadCore API。QQ / NapCat / OneBot 与微信 / Hermes / iLink Bot 不再是产品入口、控制台导航或发布目标。

## 当前处理原则

- 不启动、不维护、不在控制中心展示 Bot 状态。
- 不删除用户聊天数据、记忆数据或通用 HeadCore 能力。
- 不关闭用户电脑上的普通 QQ、微信客户端。
- 历史代码先保留在仓库中，等待引用迁移、测试替换和文档归档完成后再删除。

## 历史位置

- `integrations/qq_bot/`
- `app/channels/adapters/onebot.py`
- `app/control/hermes_weixin.py`
- `app/static/weixin/`
- QQ/微信专属控制台路由、服务管理、健康检查、脚本和测试。

## 重新启用前提

未来只有在以下条件都成立时才能重新评估：平台官方能力稳定、用户身份与授权模型可验证、消息和媒体能力有可靠验收、不会形成第二套人格或记忆、并且有明确产品需求。重新启用必须从独立适配器开始，不得回写为控制中心主结构。
