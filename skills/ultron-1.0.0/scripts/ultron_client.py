#!/usr/bin/env python3
import sys
import json
import os
import urllib.request
import urllib.error


ULTRON_API_URL = os.environ.get("ULTRON_API_URL", "https://writtingforfun-ultron.ms.show")


def _http_timeout_seconds() -> float:
    raw = os.environ.get("ULTRON_HTTP_TIMEOUT", "120")
    try:
        v = float(raw)
        return v if v > 0 else 120.0
    except ValueError:
        return 120.0


ULTRON_HTTP_TIMEOUT = _http_timeout_seconds()


def api_request(method: str, endpoint: str, data: dict = None) -> dict:
    """Send an API request to Ultron."""
    url = f"{ULTRON_API_URL}{endpoint}"
    
    headers = {"Content-Type": "application/json"}
    
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    else:
        body = None
    
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req, timeout=ULTRON_HTTP_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        try:
            return json.loads(error_body)
        except json.JSONDecodeError:
            return {"success": False, "error": f"HTTP {e.code}: {error_body}"}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"Connection failed: {e.reason}. Check ULTRON_API_URL env var and whether the service is running."}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "Usage: python ultron_client.py '<JSON>'",
            "hint": f"ULTRON_API_URL={ULTRON_API_URL}, ULTRON_HTTP_TIMEOUT={ULTRON_HTTP_TIMEOUT}"
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    
    try:
        params = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(json.dumps({
            "success": False,
            "error": f"JSON parse error: {e}"
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    
    action = params.get("action")
    if not action:
        print(json.dumps({
            "success": False,
            "error": "Missing required param: action",
            "available_actions": [
                "search_skills",
                "install_skill", "upload_skill",
                "get_stats", "list_skills",
                "upload_memory", "search_memory",
                "get_memory_details",
                "memory_stats",
                "ingest", "ingest_text",
            ]
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    
    result = None
    
    try:
        if action == "search_skills":
            query = params.get("query", "")
            if not query:
                result = {"success": False, "error": "search_skills requires query param"}
            else:
                result = api_request("POST", "/skills/search", {
                    "query": query,
                    "limit": params.get("limit", 5),
                })
        
        elif action == "install_skill":
            full_name = params.get("full_name", "")
            target_dir = params.get("target_dir", "")
            if not full_name or not target_dir:
                result = {"success": False, "error": "install_skill requires full_name and target_dir params"}
            else:
                result = api_request("POST", "/skills/install", {
                    "full_name": full_name,
                    "target_dir": target_dir,
                })

        elif action == "upload_skill":
            # Upload skills from filesystem paths
            paths = params.get("paths", [])
            if not paths:
                result = {"success": False, "error": "upload_skill needs paths param (list of skill directory paths)"}
            else:
                result = api_request("POST", "/skills/upload", {
                    "paths": paths,
                })
        

        elif action == "get_stats":
            result = api_request("GET", "/stats")

        elif action == "list_skills":
            result = api_request("GET", "/skills")


        # memory system

        elif action == "upload_memory":
            content = params.get("content", "")
            if not content:
                result = {"success": False, "error": "upload_memory requires content param"}
            else:
                result = api_request("POST", "/memory/upload", {
                    "content": content,
                    "context": params.get("context", ""),
                    "resolution": params.get("resolution", ""),
                    "tags": params.get("tags", []),
                })

        elif action == "search_memory":
            q = params.get("query", "")
            if not q:
                result = {"success": False, "error": "search_memory requires query param"}
            else:
                result = api_request("POST", "/memory/search", {
                    "query": q,
                    "tier": params.get("tier"),
                    "limit": params.get("limit", 10),
                    "detail_level": params.get("detail_level", "l0"),
                })

        elif action == "get_memory_details":
            memory_ids = params.get("memory_ids", [])
            if not memory_ids:
                result = {"success": False, "error": "get_memory_details requires memory_ids param (list of IDs)"}
            else:
                result = api_request("POST", "/memory/details", {
                    "memory_ids": memory_ids,
                })

        elif action == "memory_stats":
            result = api_request("GET", "/memory/stats")

        # smart ingestion

        elif action == "ingest":
            paths = params.get("paths", [])
            agent_id = params.get("agent_id", "")
            if not paths:
                result = {"success": False, "error": "ingest requires paths param (list of paths)"}
            elif not agent_id:
                result = {"success": False, "error": "ingest requires agent_id param"}
            else:
                result = api_request("POST", "/ingest", {
                    "paths": paths,
                    "agent_id": agent_id,
                })

        elif action == "ingest_text":
            text = params.get("text", "")
            if not text:
                result = {"success": False, "error": "ingest_text requires text param"}
            else:
                result = api_request("POST", "/ingest/text", {
                    "text": text,
                })

        else:
            result = {
                "success": False,
                "error": f"Unknown action: {action}",
                "available_actions": [
                    "search_skills",
                    "get_skill", "upload_skill",
                    "get_stats", "list_skills",
                    "upload_memory", "search_memory",
                    "get_memory_details",
                    "memory_stats",
                    "ingest", "ingest_text",
                ]
            }
    
    except Exception as e:
        result = {"success": False, "error": str(e)}
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    if not result.get("success", False):
        sys.exit(1)


if __name__ == "__main__":
    main()
