# working of the code:
# we send the query from the cli using python ask_claude.py "query_name"
# then it goes to the send message, where we send request to claude to check whether the user query needs tool call or not
# claude client detects the tool call and calls MCP server
# if tool call request is there, then we call the MCP server, we then append the results of the tool call and ask claude to summarize the results and don't call tool further
# MCP server → handle_claude_tool_call() → MCPClient.search() → DuckDuckGo API → gets results.
# MCP server returns JSON results back to ClaudeClient.
# ClaudeClient gives these results to Claude → asks for summary without more tool calls.
# Claude returns a nice summarized answer → CLI prints it.



import sys
import os
import requests
import argparse
from claude_mcp_client import ClaudeClient


def check_mcp_server():
    mcp_url = os.environ.get("MCP_SERVER_URL", "http://localhost:5001")
    try:
        response = requests.get(f"{mcp_url}/health", timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to MCP server: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Ask Claude questions with web search capability")
    parser.add_argument("query", nargs="*", help="the question to ask claude")
    args = parser.parse_args()

    if not os.environ.get("CLAUDE_API_KEY"):
        print("Error in getting claude api key")
        sys.exit(1)

    if args.query:
        query = " ".join(args.query)
    else:
        query = input("Ask claude")

    client = ClaudeClient()

    print(f"Searching for {query}")

    try:
        answer = client.get_final_answer(query)
        print("Answer", answer)
    except Exception as e:
        print(f" Error while getting answer: {type(e).__name__} - {e}")


if __name__ == "__main__":
    main()

    
