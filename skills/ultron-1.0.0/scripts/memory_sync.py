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


def api_request(method, endpoint, data=None):
    """Send an API request to Ultron."""
    url = f"{ULTRON_API_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data else None
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
        return {"success": False, "error": f"Connection failed: {e.reason}"}


def upload_shared(content, context="", resolution="", tags=None):
    """Upload objective experience to Ultron remote memory (type determined server-side)."""
    data = {
        "content": content,
        "context": context,
        "resolution": resolution,
        "tags": tags or [],
    }
    return api_request("POST", "/memory/upload", data)


def search_memory(query, limit=10, detail_level="l0"):
    """Search remote memories (all types). detail_level must be l0 or l1."""
    return api_request(
        "POST",
        "/memory/search",
        {"query": query, "limit": limit, "detail_level": detail_level},
    )


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "Usage: python memory_sync.py '<JSON>'",
            "available_actions": [
                "upload_shared",
                "search_memory",
            ],
            "hint": f"ULTRON_API_URL={ULTRON_API_URL}, ULTRON_HTTP_TIMEOUT={ULTRON_HTTP_TIMEOUT}",
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    try:
        params = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"JSON parse error: {e}"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    action = params.get("action")
    result = None

    if action == "upload_shared":
        content = params.get("content", "")
        if not content:
            result = {"success": False, "error": "upload_shared requires content param"}
        else:
            result = upload_shared(
                content=content,
                context=params.get("context", ""),
                resolution=params.get("resolution", ""),
                tags=params.get("tags", []),
            )

    elif action == "search_memory":
        query = params.get("query", "")
        if not query:
            result = {"success": False, "error": "search_memory requires query param"}
        else:
            result = search_memory(
                query=query,
                limit=params.get("limit", 10),
                detail_level=params.get("detail_level", "l0"),
            )

    else:
        result = {
            "success": False,
            "error": f"Unknown action: {action}",
            "available_actions": [
                "upload_shared",
                "search_memory",
            ],
        }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("success", False):
        sys.exit(1)


if __name__ == "__main__":
    main()
