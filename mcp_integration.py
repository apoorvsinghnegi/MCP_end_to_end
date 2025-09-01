import os
import re
import json
import requests
from typing import Dict, List, Any, Optional, Literal
from dataclasses import dataclass, asdict
import openai
import anthropic

DUCKDUCKGO_ENDPOINT = "https://api.duckduckgo.com"
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")

LLMProvider = Literal["claude"]

@dataclass
class DDGRequest:
    q: str
    format: str = "json"
    no_html: int = 1
    skip_disambig: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
       
@dataclass
class WebResult:
    title: str
    url: str
    description: str


# search for DDG endpoint, Handles DuckDuckGo API search.
class MCPClient:
    def __init__(self, endpoint: str = DUCKDUCKGO_ENDPOINT):
        self.endpoint = endpoint

    def search(self, query: str, count: int = 10) -> List[WebResult]:
        request = DDGRequest(q=query)

        try:
            response = requests.get(
                self.endpoint,
                params=request.to_dict()
            )

            response.raise_for_status()

            data = response.json()
            results = []

            if data.get("Abstract"):
                results.append(WebResult(
                    title=data.get("Heading", ""),
                    url = data.get("AbstractURL", ""),
                    description=data.get("Abstract", "")
                ))
            return results
        except Exception as e:
            print(e)
            return []

# Acts as a bridge between Claude and MCPClient.

     
class ClaudeMCPBridge:

    def __init__(self, llm_provider: LLMProvider = "claude"):
        self.mcp_client = MCPClient()
        self.llm_provider = llm_provider

        if llm_provider == "claude":
            self.claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    def extract_website_queries_with_llm(self, user_message: str) -> List[str]: #to get the website queries from user message which would be given to claude
        if self.llm_provider == "claude":
            return self._extract_with_claude(user_message)
        else:
            return ["error"]
        
    def _extract_with_claude(self, user_message: str) -> List[str]: # a specialized query extractor that asks Claude (Anthropic's LLM) to read a user's message and pull out search queries from it in JSON format.

        try:
            response = self.claude_client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=1000,
                temperature=0.1,
                system="You are a helpful assistant that identifies web search queries in user message. Extract any specific website or topic queries the user wants information about. Return results as a JSON object with a 'queries' field containing an array of strings. If no queries are found, return an empty array.",
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )

            content = response.content[0].text  # send to claude client
            json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', content, re.DOTALL)
            json_str = json_match.group(1) if json_match else content.strip()
            try:
                result =  json.loads(json_str)
            except json.JSONDecodeError:
                return "error"
            queries = result.get("queries", [])
            return queries
        
        except Exception as e:
            print(e)
            return []
        
# send a call to MCP client search to DDG end point and get the answer back 


def handle_claude_tool_call(tool_params: Dict[str, Any]) -> Dict[str, Any]:
    query = tool_params.get("query", "")
    if not query:
        return {"error": "no query"}
    
    bridge = ClaudeMCPBridge()
    results = bridge.mcp_client.search(query)

    return {
        "results": [asdict(result) for result in results]
    }
    

        
    