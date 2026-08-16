import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://127.0.0.1:49152"
    try:
        async with websockets.connect(uri) as ws:
            print("WebSocket 连接成功!")
            # 接收欢迎消息
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=3)
                print("收到:", msg[:500])
            except asyncio.TimeoutError:
                print("无欢迎消息")
            
            # 发送探测
            await ws.send(json.dumps({"type": "ping"}))
            try:
                resp = await asyncio.wait_for(ws.recv(), timeout=3)
                print("Ping 响应:", resp[:500])
            except asyncio.TimeoutError:
                print("无 Ping 响应")
            
            # 发送获取会话列表
            await ws.send(json.dumps({
                "type": "get_sessions",
                "payload": {}
            }))
            try:
                resp = await asyncio.wait_for(ws.recv(), timeout=3)
                print("会话列表:", resp[:1000])
            except asyncio.TimeoutError:
                print("无会话列表响应")
    except Exception as e:
        print("WebSocket 连接失败:", e)

asyncio.run(test_ws())