# Retired QQ/Weixin Bot Configuration

## Status

QQ/Weixin Bot support is retired from the current HutaoChatCore product and is
not deployed by the current Docker staging stack. The active product boundary is
Web, PWA, desktop application, mobile application, mini-program clients, and
their shared HeadCore HTTP API.

The legacy adapters and their tests remain in source control as historical
technical material. They are deliberately not removed in this release because
their configuration, platform SDKs, and integration assumptions require a
separate migration and deletion review.

## Configuration Boundary

The current `.env.example` is the only template for active local and staging
Core deployments. It must not contain Bot platform tokens, Bot account IDs, or
Bot runtime switches.

Historical Bot settings include platform connection credentials, voice-reply
providers, image-reading providers, message adapters, and pairing services.
They are inactive and must not be copied into `deploy/.env.staging`.

## Reactivation Requirements

Reactivation is a separate product decision. It requires a new architecture
review, legal and privacy review, platform account testing, a dedicated secret
template, and isolated acceptance tests before any Bot process can be deployed.
