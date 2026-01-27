# 自定义 MCP SDK

## 1. 概述

### 1.1. SDK 使用方法

- 初始化 SDK 配置  
> 初始化前，您需要从开发者平台获取 AccessId、AccessSecret 和 Endpoint。
```python
from mcp_sdk import create_mcpsdk

# 使用配置创建 MCP SDK
mcpsdk = await create_mcpsdk(
    # 设置自定义 MCP 服务器端点
    custom_mcp_server_endpoint="http://localhost:8765/mcp",
    # 设置 Access ID、Access secret 和 Endpoint
    endpoint="your-endpoint",
    access_id="your-access-id", 
    access_secret="your-access-secret",
    # 可选: 自定义 MCP 客户端请求头, 默认为 None,
    # 可以设置为: {"Authorization":"Bearer test_server_token"}
    headers=None,
    # 可选: 动态请求头提供函数, 默认为 None,
    # 可以设置为定义的函数:
    """
    def headers_provider() -> dict[str, str]:
        return {"Token": os.getenv("MCP_TOKEN", "")}
    """
    headers_provider=None,
)
```

- 运行 SDK
```python
import asyncio

async def main():
    async with mcpsdk:
        print("MCP SDK 连接成功！")
        await mcpsdk.start_background()
        
        # 保持运行
        while mcpsdk.is_running:
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
```

### 1.2. 架构图
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   您的应用      │───▶│    MCP SDK       │───▶│  MCP 网关      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │   MCP 服务器     │
                       └──────────────────┘
```

## 2. 快速开始 
**前置条件：**
> 机器需要 Python 3.10+ 环境用于 Python 开发，以及 pip >= 21.3。

- 检出源代码
    ```shell
    git clone https://github.com/tuya/tuya-mcp-sdk.git

    cd mcp-python
    ```
  
- 运行 SDK 示例
    ```shell
    # 创建虚拟环境
    python -m venv .venv 
    # 或 `python3 -m venv .venv`
    
    # 激活虚拟环境
    source .venv/bin/activate  # Linux/Mac

    # 安装开发依赖
    pip install -e ".[dev]"

    # 使用自定义参数运行
    python -m examples all --endpoint your-endpoint --access-id your-access-id --access-secret your-access-secret --custom-mcp-server-endpoint http://localhost:8765/mcp
    ```
  - 参数说明
    - endpoint: Tuya 开发者平台 MCP 端点
    - access-id: Tuya 开发者平台 MCP 访问 ID
    - access-secret: Tuya 开发者平台 MCP 访问密钥
    - custom-mcp-server-endpoint: SDK 中声明的自定义 MCP 服务器端点地址；当前演示包含一个 MCP 服务器示例 `http://localhost:8765/mcp`
    - static-mcp-headers (可选): MCP 客户端携带静态自定义Header; e.g. `--static-mcp-headers '{"Authorization":"Bearer test_server_token"}'`

## 3. 开发自定义 MCP 服务器
> 开发者基于业务开发自定义 MCP 服务器，为其设备提供能力。

### 3.1. 使用 [FastMCP](https://github.com/jlowin/fastmcp) 开发

- 创建新的 MCP 服务器
```python
from fastmcp import FastMCP

mcp_server = FastMCP("演示")
```

- 创建工具
```python
@mcp_server.tool()
def hello_world(name: str) -> str:
    """向某人问好
    
    参数:
        name: 要问候的人的名字
    """
    return f"你好，{name}！"
```

### 3.2. 运行 MCP 服务器
```python
from fastmcp import FastMCP

def main():
    # 创建新的 MCP 服务器
    mcp_server = FastMCP("演示")

    # 添加工具
    @mcp_server.tool()
    def hello_world(name: str) -> str:
        """向某人问好
        
        参数:
            name: 要问候的人的名字
        """
        return f"你好，{name}！"

    # 启动服务器
    mcp_server.run()

if __name__ == "__main__":
    main()
```

### 3.3. 示例

- [示例](examples/README.md)
