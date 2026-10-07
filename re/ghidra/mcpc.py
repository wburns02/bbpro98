#!/usr/bin/env python3
"""mcpc.py TOOL [json-args]  -- call a pyghidra-mcp tool on 127.0.0.1:18765 ('tools' lists them)"""
import sys,json,asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
async def main():
    async with streamablehttp_client("http://127.0.0.1:18765/mcp") as (r,w,_):
        async with ClientSession(r,w) as s:
            await s.initialize()
            if sys.argv[1]=='tools':
                for t in (await s.list_tools()).tools: print(t.name,'-',(t.description or '').splitlines()[0][:100], list((t.inputSchema or {}).get('properties',{}).keys()))
                return
            res=await s.call_tool(sys.argv[1],json.loads(sys.argv[2]) if len(sys.argv)>2 else {})
            for c in res.content: print(getattr(c,'text',c))
asyncio.run(main())
