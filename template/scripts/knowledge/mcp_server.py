#!/usr/bin/env python3
# ADR-0001 — local docs+code knowledge graph
"""Thin stdlib stdio MCP server exposing the knowledge graph (no SDK).

Newline-delimited JSON-RPC 2.0. Tools: kg_query (scoped), kg_federated_query,
kg_trace. Degrades gracefully when the graph is unbuilt (empty results)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import query as query_mod  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
TOOLS = [
    {"name": "kg_query",
     "description": "Scoped content search within one namespace.",
     "inputSchema": {"type": "object",
                     "properties": {"scope": {"type": "string"},
                                    "query": {"type": "string"},
                                    "k": {"type": "integer"}},
                     "required": ["scope", "query"]}},
    {"name": "kg_federated_query",
     "description": "Content search across all namespaces.",
     "inputSchema": {"type": "object",
                     "properties": {"query": {"type": "string"},
                                    "k": {"type": "integer"}},
                     "required": ["query"]}},
    {"name": "kg_trace",
     "description": "Trace the ADR<->code<->test<->story chain for a node id.",
     "inputSchema": {"type": "object",
                     "properties": {"id": {"type": "string"},
                                    "scope": {"type": "string"}},
                     "required": ["id"]}},
]


def _text(obj):
    return {"content": [{"type": "text", "text": json.dumps(obj, indent=2)}]}


def call_tool(name, args):
    if name == "kg_query":
        kg = query_mod.open_scoped(args["scope"])
        if not kg.aliases:
            return _text({"results": [], "hint": query_mod.EMPTY_HINT})
        return _text(query_mod.search(kg, args["query"], args.get("k", 5)))
    if name == "kg_federated_query":
        kg = query_mod.open_federated()
        if not kg.aliases:
            return _text({"results": [], "hint": query_mod.EMPTY_HINT})
        return _text(query_mod.search(kg, args["query"], args.get("k", 5)))
    if name == "kg_trace":
        kg = query_mod.open_scoped(args["scope"]) if args.get("scope") else query_mod.open_federated()
        if not kg.aliases:
            return _text({"root": args["id"], "nodes": [], "edges": [], "hint": query_mod.EMPTY_HINT})
        return _text(query_mod.trace(kg, args["id"]))
    raise KeyError(name)


def handle(msg):
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "ai-sdlc-knowledge", "version": "1.0.0"}}}
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params") or {}
        try:
            res = call_tool(params.get("name"), params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": mid, "result": res}
        except Exception as ex:  # never crash the loop; surface as tool error
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": f"error: {ex}"}], "isError": True}}
    if mid is None:
        return None  # never reply to a notification (JSON-RPC 2.0 §4)
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(stdin=None, stdout=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            print("knowledge-mcp: skipping invalid JSON line", file=sys.stderr)
            continue
        resp = handle(msg)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()


if __name__ == "__main__":
    serve()
