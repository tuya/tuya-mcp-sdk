# Tuya MCP SDK

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Go](https://img.shields.io/badge/Go-1.24+-00ADD8?style=flat&logo=go)](https://golang.org/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python)](https://www.python.org/)
[![C#](https://img.shields.io/badge/.NET-10+-512BD4?style=flat&logo=dotnet)](https://dotnet.microsoft.com/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-green)](https://modelcontextprotocol.io/)


A comprehensive SDK that empowers developers to integrate their custom capabilities with Tuya Cloud through the standardized Model Context Protocol (MCP), ensuring seamless connectivity and interoperability.

[🚀 Quick Start](#-quick-start) •
[📖 Documentation](#-documentation) •

## ✨ Features

- 🔌 **Easy Integration**: Simple SDK for connecting Tuya Developer Platform to MCP servers
- 🐍 **Multi-Language Support**: Available in Python, Go, and C#
- 🔒 **Secure Authentication**: Robust authentication with Tuya Cloud
- 📱 **Real-time Communication**: WebSocket-based real-time interaction
- 🎯 **Production Ready**: Comprehensive error handling and retry mechanisms

## 🏗️ Architecture

The Tuya MCP SDK bridges the gap between Custom MCP Server and Tuya Developer Platform by implementing the Model Context Protocol standard:

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

## 🚀 Quick Start

### Prerequisites

- [Tuya Developer Account](https://platform.tuya.com/) with MCP service enabled
- Python >= 3.10 and pip >= 21.3, or Go >= 1.24
- Access credentials (Access ID, Access Secret, Endpoint)

### 1. Setup Tuya Developer Platform

1. Visit [Tuya Developer Platform](https://platform.tuya.com/)
2. Navigate to **MCP Management** → **Custom MCP Service**
3. Create a new MCP service and note down your credentials
4. Follow the detailed [setup instructions](docs/instructions.md)

### 2. Choose Your SDK

#### 🐍 Python SDK Example
- [Python SDK Example](mcp-python)

#### 🐹 Go SDK Example
- [Golang SDK Example](mcp-golang)

#### 🔷 C# SDK Example
- [C# SDK Example](mcp-csharp)

## 📖 Documentation

| Resource | Description |
|----------|-------------|
| [📋 Setup Instructions](docs/instructions.md) | Complete setup guide for Tuya Developer Platform |
| [🐍 Python SDK Docs](mcp-python/README.md) | Python SDK documentation and examples |
| [🐹 Go SDK Docs](mcp-golang/README.md) | Go SDK documentation and examples |
| [🔷 C# SDK Docs](mcp-csharp/README.md) | C# SDK documentation and examples |
| [🏗️ Architecture](docs/architecture_diagram/) | System architecture diagrams |

## 📁 Project Structure

```text
tuya-mcp-sdk/
├── 📄 README.md                 # This file
├── 📄 License                   # Apache 2.0 License
├── 📁 docs/                     # Documentation
│   ├── instructions.md          # Setup instructions
│   └── architecture_diagram/    # Architecture diagrams
├── 📁 mcp-python/              # Python SDK
│   ├── src/mcp_sdk/            # Core SDK modules
│   ├── examples/               # Python examples
│   └── README.md               # Python-specific docs
├── 📁 mcp-golang/              # Go SDK
│   ├── pkg/                    # Go packages
│   ├── examples/               # Go examples
│   └── README.md               # Go-specific docs
└── 📁 mcp-csharp/              # C# SDK
    ├── src/Tuya.McpSdk/        # Core SDK library (.NET 10)
    ├── examples/               # C# examples
    └── README.md               # C#-specific docs
```

## 📜 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](License) file for details.

## Pip Installation
Now the sdk can be installed via pip（https://pypi.org/project/tuya-developer-agent-mcp-sdk/0.1.0/）
## 🆘 Support

- 📚 **Documentation**: Check our [docs](docs/) for detailed guides
- 🐛 **Bug Reports**: [Open an issue](https://github.com/tuya/tuya-mcp-sdk/issues)
- 💬 **Questions**: [Tuya Developer Community](https://www.tuyaos.com/)
- 🏢 **Enterprise**: Contact [Tuya Support](https://service.console.tuya.com/)


