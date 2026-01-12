# Custom MCP SDK

## 1. Overview

### 1.1. SDK Usage

- Init SDK Config
> Before initialization, you need to obtain AccessId, AccessSecret, and Endpoint from the Tuya developer platform.
```go
mcpsdk, err := sdk.NewMCPSdk(
    // Set custom MCP server hosts
    sdk.WithMCPServerEndpoint(conf.CustomMcpServerEndpoint),
    // Set Access ID, Access secret and Endpoint
    sdk.WithAccessParams(conf.AccessId, conf.AccessSecret, conf.Endpoint),
)
```
- Running SDK
```go
err = mcpsdk.Run()
if err != nil {
    log.Fatal(err)
}
```



### 1.2. Architecture Diagram
<!-- <img src="../docs/pic/00.architechture-en.png" height="550" align=center> -->
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


## 2. Quick Start 
**Prerequisites:**
> The machine has Golang 1.24 environment for Go source code compilation and building.

**Run SDK**
1. Checkout source code
    ```shell
    git clone https://github.com/tuya/tuya-mcp-sdk.git

    cd mcp-golang
    ```

2. Modify Configuration File `examples/config.example.yaml `
    ```yaml
    access_id: xxxx
    access_secret: xxx
    endpoint: https://${xxx}
    custom_mcp_server_endpoint: http://localhost:8080/sse
    ```
    
    - Configuration Description
        - access_id: Tuya developer platform MCP access id
        - access_secret: Tuya developer platform MCP access secret
        - endpoint: Tuya developer platform MCP endpoint
        - custom_mcp_server_endpoint: Address of custom MCP Server declared in SDK; current demo includes an MCP Server example `http://localhost:8080/sse`




3. Run SDK Example
    ```shell
    go mod tidy

    go build -o mcp_sdk examples/main.go

    CONFIG_PATH=./examples/config.example.yaml ./mcp_sdk
    ```


## 3. Develop Custom MCP Server
> Developers develop custom MCP Servers based on business to provide capabilities for their devices.

### 3.1. Develop By [mcp-go](https://github.com/mark3labs/mcp-go)

- Create a New MCP Server
```go
s := server.NewMCPServer(
    "Demo",
    "1.0.0",
    server.WithToolCapabilities(false),
)
```
- Create a Tool
```go
func helloHandler(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
    name, err := request.RequireString("name")
    if err != nil {
        return mcp.NewToolResultError(err.Error()), nil
    }

    return mcp.NewToolResultText(fmt.Sprintf("Hello, %s!", name)), nil
}
```

- Add tool to MCP Server
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

### 3.2. Run MCP Server
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

### 3.3. Examples

- [Examples](examples/README.md)