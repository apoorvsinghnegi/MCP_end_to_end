import os
import json
import requests
import time
from typing import Dict, List, Any, Optional

CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:5001")

# Handles communication with the Claude API and tool call orchestration.


class ClaudeClient:
    def __init__(self, api_key: str = CLAUDE_API_KEY, model: str = "claude-3-opus-20240229"):
        self.api_key = api_key
        self.model = model
        self.headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        self.tools = [{
            "name": "fetch_web_content",
            "description": "Retrieves info from website based on user queries",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "the search query or website to look up information about"
                    }
                },
                "required": ["query"]
            }
        }]

        self._check_mcp_server()
    
    def _check_mcp_server(self):
        try:
            response = requests.get(f"{MCP_SERVER_URL}/health", timeout=2)
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            print(f"[MCP Check] Error: {e}")
            return False
        
    def send_message(self, message: str, conversation_history: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        # to send message to claude with optional conversation history, suports tool calls and handles them automatically
      
        if not self.api_key:
            raise ValueError("Claude API key is required")

        if conversation_history is None:
            conversation_history = []

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": conversation_history + [{"role": "user", "content": message}],
            "tools": self.tools
        }

        print("Sending request to Claude...")

        try:
            response = requests.post(
                CLAUDE_API_URL,
                headers=self.headers,
                json=payload
            )

            if response.status_code != 200:
                print("Error response from Claude:", response.json())

            response.raise_for_status()
            result = response.json()
            print(f"Claude response: {result}")

            # Tool call detection
            has_tool_call = False
            if "content" in result:
                for content_block in result.get("content", []):
                    if content_block.get("type") == "tool_use":
                        has_tool_call = True
                        print("Tool call detected")

                        tool_call = {
                            "name": content_block.get("name", ""),
                            "parameters": {
                                "query": content_block.get("input", {}).get("query", {})
                            }
                        }
                        print(f"Tool call details: {tool_call}")

                        # Call MCP server tool handler
                        tool_response = self._handle_tool_call(tool_call)
                        print(f"Tool response: {tool_response}")

                        # Safely extract tool response description
                        description = ""
                        if tool_response.get("results") and len(tool_response["results"]) > 0:
                            description = tool_response["results"][0].get("description", "")

                        # Append conversation with tool call result
                        conversation_history.extend([
                            {"role": "user", "content": message},
                            {
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": (
                                            result.get("content", [{}])[0].get("text", "") +
                                            "\n\nThe tool call was successful and here is the information from the tool call: " +
                                            description
                                        )
                                    }
                                ]
                            }
                        ])

                        # Ask Claude to summarize results without further tool calls
                        return self.send_message(
                            "Please summarize the information from the tool call and don't send any more tool calls",
                            conversation_history
                        )

            if not has_tool_call:
                print("No tool calls detected.")

            return result

        except Exception as e:
            print(f"Error while sending message to Claude: {e}")
            return {"error": str(e)}
        
# Accepts query from Claude’s tool call. Uses ClaudeMCPBridge → MCPClient → DuckDuckGo API to get search results. Converts WebResult dataclasses to dicts (asdict).
# Returns them to the MCP server.
    def _handle_tool_call(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = tool_call.get("name")
        tool_params = tool_call.get("parameters")

        if not self._check_mcp_server():
            return {"error": "MCP server not available"}

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                response = requests.post(
                    f"{MCP_SERVER_URL}/tool_call",
                    json={"name": tool_name, "parameters": tool_params},
                    timeout=10
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.RequestException as e:
                retry_count += 1
                print(f"Error calling MCP server: {e}. Retry {retry_count}/{max_retries}...")
                
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count
                    time.sleep(wait_time)
                else:
                    return {"error": "MCP server not responding after retries"}
        return {"error": "Unknown error in _handle_tool_call"}

    def get_final_answer(self, message: str) -> str:
        try:
            response = self.send_message(message)

            if "content" in response:
                for content_block in response.get("content", []):
                    if content_block.get("type") == "text":
                        return content_block.get("text", "")
            return "No clear answer found"
        
        except Exception as e:
            return f"Error: {e}"
