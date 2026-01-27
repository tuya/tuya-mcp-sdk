# Tuya MCP SDK

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Go](https://img.shields.io/badge/Go-1.24+-00ADD8?style=flat&logo=go)](https://golang.org/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-green)](https://modelcontextprotocol.io/)

一个帮助开发者快速通过标准化的模型上下文协议（MCP）将自定义MCP工具集成到涂鸦云平台，确保无缝连接和互操作性。

[🚀 快速开始](#-快速开始) •
[📖 文档说明](#-文档说明) •

## ✨ 特性

- 🔌 **简单集成**：SDK用于连接涂鸦开发者平台与自定义MCP服务器
- 🐍 **多语言支持**：支持Python和Go两种语言
- 🔒 **安全认证**：与涂鸦云平台的强大身份验证
- 📱 **实时通信**：基于WebSocket的实时交互
- 🎯 **生产就绪**：全面的错误处理和重试机制

## 🏗️ 架构

Tuya MCP SDK通过实现模型上下文协议标准，在自定义MCP服务器和涂鸦开发者平台之间建立桥梁：

```text
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Your App      │───▶│    MCP SDK       │───▶│  MCP Gateway    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │   MCP Server     │
                       └──────────────────┘
```

## 🚀 快速开始

### 前置条件

- 已启用MCP服务的[涂鸦开发者账户](https://platform.tuya.com/)
- Python >= 3.10 与 pip >= 21.3, 或者 Go >= 1.24
- 访问凭证（Access ID、Access Secret、Endpoint）

### 1. 设置涂鸦开发者平台

1. 访问[涂鸦开发者平台](https://platform.tuya.com/)
2. 导航到 **MCP管理** → **自定义MCP服务**
3. 创建新的MCP服务并记录您的凭证
4. 按照详细的[设置说明](docs/instructions-zh.md)操作

### 2. 选择您的SDK

#### 🐍 Python SDK Example
- [Python SDK 示例](mcp-python)


#### 🐹 Go SDK Example
- [Golang SDK 示例](mcp-golang)

## 📖 文档说明

| 资源 | 描述 |
|------|------|
| [📋 设置说明](docs/instructions-zh.md) | 涂鸦开发者平台完整设置指南 |
| [🐍 Python SDK 文档](mcp-python/README-zh.md) | Python SDK文档和示例 |
| [🐹 Go SDK 文档](mcp-golang/README-zh.md) | Go SDK文档和示例 |
| [🏗️ 架构图](docs/architecture_diagram/) | 系统架构图 |

## 📁 项目结构

```text
tuya-mcp-sdk/
├── 📄 README.md                 # 英文说明文件
├── 📄 README-zh.md             # 中文说明文件（本文件）
├── 📄 License                   # Apache 2.0 许可证
├── 📁 docs/                     # 文档
│   ├── instructions.md          # 英文设置说明
│   ├── instructions-zh.md       # 中文设置说明
│   └── architecture_diagram/    # 架构图
├── 📁 mcp-python/              # Python SDK
│   ├── src/mcp_sdk/            # 核心SDK模块
│   ├── examples/               # Python示例
│   └── README-zh.md            # Python专用中文文档
└── 📁 mcp-golang/              # Go SDK
    ├── pkg/                    # Go包
    ├── examples/               # Go示例
    └── README-zh.md            # Go专用中文文档
```

## 📜 许可证

本项目采用Apache License 2.0许可证 - 详见[LICENSE](License)文件。

## 🆘 支持

- 📚 **文档**：查看我们的[文档](docs/)获取详细指南
- 🐛 **问题报告**：[提交问题](https://github.com/tuya/tuya-mcp-sdk/issues)
- 💬 **疑问**：[涂鸦开发者社区](https://www.tuyaos.com/)
- 🏢 **企业支持**：联系[涂鸦支持](https://service.console.tuya.com/)
