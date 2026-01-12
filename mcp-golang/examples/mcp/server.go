package mcp

import (
	"log"
	"net/url"

	"github.com/mark3labs/mcp-go/server"
)

type Tools func(mcpServer *server.MCPServer)

// MCPServer MCP server structure
type MCPServer struct {
	server *server.MCPServer
}

// NewMCPServer creates a new MCP server instance
func NewMCPServer() *MCPServer {
	mcpServer := server.NewMCPServer(
		"custom_mcp_server",
		"1.0.0",
		server.WithToolCapabilities(true),
		server.WithLogging(),
	)

	registerTool(mcpServer, new(Music).Register)
	registerTool(mcpServer, new(Photo).Register)

	return &MCPServer{
		server: mcpServer,
	}
}

func registerTool(mcpServer *server.MCPServer, tool Tools) {
	tool(mcpServer)
}

// StartHTTP starts MCP server in HTTP mode
func (s *MCPServer) StartHTTP(customMcpServerEndpoint string) {
	log.Printf("Starting MCP Server (HTTP mode)...")
	log.Printf("Server address: %s", customMcpServerEndpoint)
	log.Printf("Available tools:")
	log.Printf("   - play_music: Play music, you can play music by name's keyword, e.g. 'classic'")
	log.Printf("   - stop_music: Stop playing music")
	log.Printf("   - take_photo: Take a photo")
	log.Printf("   - view_photo: View a photo, you can view a photo by name's keyword, e.g. 'photo1'")

	httpServer := server.NewSSEServer(s.server)

	u, err := url.Parse(customMcpServerEndpoint)
	if err != nil {
		log.Fatalf("Failed to parse custom MCP server endpoint: %v", err)
	}

	port := u.Port()
	if port == "" {
		port = "8080"
	}

	if err := httpServer.Start(":" + port); err != nil {
		log.Fatalf("Failed to start MCP server: %v", err)
	}
}
