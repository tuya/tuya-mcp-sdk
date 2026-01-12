# 自定义MCP Server

## 1. 概览

### 1.1. SDK使用说明

- 初始化SDK配置
> 初始化SDK配置前，需要从涂鸦开发者平台获取 AccessId，AccessSecret，Endpoint

```go
mcpsdk, err := sdk.NewMCPSdk(
    // Set custom MCP server hosts
    sdk.WithMCPServerEndpoint(conf.CustomMcpServerEndpoint),
    // Set Access ID, Access secret and Endpoint
    sdk.WithAccessParams(conf.AccessId, conf.AccessSecret, conf.Endpoint),
)
```
- 运行SDK
```go
err = mcpsdk.Run()
if err != nil {
    log.Fatal(err)
}
```

### 1.2. 架构图
 <!-- <img src="../docs/pic/00.architechture-zh.png" height="550" align=center> -->

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Your App      │───▶│    MCP SDK       │───▶│  MCP Gateway    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │   MCP Server     │
                       └──────────────────┘
```
## 2. 快速启动
**先决条件：**
> 机器存在Golang 1.24环境，可以做Go源码编译构建。

1. 检出源码
    ```shell
    # 检出代码
    git clone https://github.com/tuya/tuya-mcp-sdk.git
    # 进入Golang SDK目录
    cd mcp-golang
    ```
2. 修改配置文件 `examples/config.example.yaml `
    ```yaml
    access_id: xxxx
    access_secret: xxx
    endpoint: https://${xxx}
    custom_mcp_server_endpoint: http://localhost:8080/sse
    ```
    - 配置说明：
        - access_id: 涂鸦开发者自定义MCP接入标识
        - access_secret: 涂鸦开发者自定义MCP接入秘钥
        - endpoint: 涂鸦开发者自定义MCP接入点
        - custom_mcp_server_endpoint: SDK中自定义MCP Server的接入点；当前Demo中包含一个MCP Server示例`http://localhost:8080/sse`


3. 运行
    ```shell
    go mod tidy

    go build -o mcp_sdk examples/main.go

    CONFIG_PATH=./examples/config.example.yaml ./mcp_sdk
    ```


## 3. 自定义MCP Server开发
> 开发者基于业务开发自定义的MCP Server，为其设备提供能力。

### 3.1. 基于[mcp-go](https://github.com/mark3labs/mcp-go)开发MCP Server

- 创建一个MCP Server
```go
s := server.NewMCPServer(
    "Demo",
    "1.0.0",
    server.WithToolCapabilities(false),
)
```
- 开发一个工具
```go
func helloHandler(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
    name, err := request.RequireString("name")
    if err != nil {
        return mcp.NewToolResultError(err.Error()), nil
    }

    return mcp.NewToolResultText(fmt.Sprintf("Hello, %s!", name)), nil
}
```

- 添加工具
```go 
tool := mcp.NewTool("hello_world",
    mcp.WithDescription("Say hello to someone"),
    mcp.WithString("name",
        mcp.Required(),
        mcp.Description("Name of the person to greet"),
    ),
)

s.AddTool(tool, helloHandler)
```

### 3.2. 运行MCP Server
```go
package main

import (
    "context"
    "fmt"

    "github.com/mark3labs/mcp-go/mcp"
    "github.com/mark3labs/mcp-go/server"
)

func main() {
    // Create a new MCP server
    s := server.NewMCPServer(
        "Demo",
        "1.0.0",
        server.WithToolCapabilities(false),
    )

    // Add tool
    tool := mcp.NewTool("hello_world",
        mcp.WithDescription("Say hello to someone"),
        mcp.WithString("name",
            mcp.Required(),
            mcp.Description("Name of the person to greet"),
        ),
    )

    // Add tool handler
    s.AddTool(tool, helloHandler)

    // Start the stdio server
    if err := server.ServeStdio(s); err != nil {
        fmt.Printf("Server error: %v\n", err)
    }
}

func helloHandler(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
    name, err := request.RequireString("name")
    if err != nil {
        return mcp.NewToolResultError(err.Error()), nil
    }

    return mcp.NewToolResultText(fmt.Sprintf("Hello, %s!", name)), nil
}
```

### 3.2. Examples

- [Examples](examples/README-zh.md)