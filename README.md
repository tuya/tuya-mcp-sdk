# Tuya MCP SDK

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Go](https://img.shields.io/badge/Go-1.24+-00ADD8?style=flat&logo=go)](https://golang.org/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-green)](https://modelcontextprotocol.io/)


A comprehensive SDK that empowers developers to integrate their custom capabilities with Tuya Cloud through the standardized Model Context Protocol (MCP), ensuring seamless connectivity and interoperability.

[🚀 Quick Start](#-quick-start) •
[📖 Documentation](#-documentation) •
[🛠️ Examples](#️-examples) 


## ✨ Features

- 🔌 **Easy Integration**: Simple SDK for connecting Tuya Developer Platform to MCP servers
- 🐍 **Multi-Language Support**: Available in Python and Go
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

```bash
# Clone the repository
git clone https://github.com/tuya/tuya-mcp-sdk.git
cd tuya-mcp-sdk/mcp-python

# Install dependencies
pip install -e .

# Run the example
python examples/quick_start.py
```

**Python SDK Usage:**

```python
from mcp_sdk import create_mcpsdk

# Initialize SDK
async with create_mcpsdk(
    endpoint="your-endpoint",
    access_id="your-access-id", 
    access_secret="your-access-secret",
    custom_mcp_server_endpoint="http://localhost:8765/mcp"
) as sdk:
    # Your MCP server is now connected to Tuya Cloud!
    await sdk.run()
```

#### 🐹 Go SDK Example

```bash
# Navigate to Go SDK
cd tuya-mcp-sdk/mcp-golang

# Install dependencies
go mod tidy

# Run the example
go run examples/main.go
```

**Go SDK Usage:**

```go
import "mcp-sdk/pkg/mcpsdk"

// Initialize SDK
mcpsdk, err := sdk.NewMCPSdk(
    sdk.WithMCPServerEndpoint("http://localhost:8765/mcp"),
    sdk.WithAccessParams("access-id", "access-secret", "endpoint"),
)
if err != nil {
    log.Fatal(err)
}

// Start the SDK
err = mcpsdk.Run()
```

## 📖 Documentation

| Resource | Description |
|----------|-------------|
| [📋 Setup Instructions](docs/instructions.md) | Complete setup guide for Tuya Developer Platform |
| [🐍 Python SDK Docs](mcp-python/README.md) | Python SDK documentation and examples |
| [🐹 Go SDK Docs](mcp-golang/README.md) | Go SDK documentation and examples |
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
└── 📁 mcp-golang/              # Go SDK
    ├── pkg/                    # Go packages
    ├── examples/               # Go examples
    └── README.md               # Go-specific docs
```

## 🛠️ Examples
- [Golang SDK Example](mcp-golang/examples)
- [Python SDK Example](mcp-python/examples)

## 📜 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](License) file for details.

## Pip Installation
Now the sdk can be installed via pip（https://pypi.org/project/tuya-developer-agent-mcp-sdk/0.1.0/）
## 🆘 Support

- 📚 **Documentation**: Check our [docs](docs/) for detailed guides
- 🐛 **Bug Reports**: [Open an issue](https://github.com/tuya/tuya-mcp-sdk/issues)
- 💬 **Questions**: [Tuya Developer Community](https://www.tuyaos.com/)
- 🏢 **Enterprise**: Contact [Tuya Support](https://service.console.tuya.com/)


