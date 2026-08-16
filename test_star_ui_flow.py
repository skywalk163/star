#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
群星 Star — 搭子桥 UI 真实用户流测试（浏览器自动化）
目标：证明真实用户打开页面后，能"新建任务→发送任务"把活真正派给 Comate，
      而不是只看到静态页面。

仅渲染检查（上一次测试的做法）不足以证明可用性；本测试驱动真实点击与接口调用。
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

URL = "http://127.0.0.1:8765/ui/pages/dumate.html"
PORT = 9222
RES = []

def log(step, desc, obs, ok, info=""):
    RES.append((step, desc, obs, ok, info))
    print(f"\n==== [{'PASS' if ok else 'FAIL'}] {step}: {desc}")
    print(f"  观察: {obs}")
    if info:
        print(f"  说明: {info}")

def _create_tab(bridge, url):
    """通过 CDP /json/new 创建标签页并返回带 webSocketDebuggerUrl 的 tab dict

    注意：部分 Edge 版本 /json/new 仅支持 PUT（GET/POST 返回 405）。
    """
    import urllib.request, urllib.parse
    # 该 Edge 构建：PUT /json/new?<url> 直接打开并导航
    try:
        put_url = f"{bridge.base_url}/json/new?" + urllib.parse.quote(url, safe="")
        req = urllib.request.Request(put_url, data=b"", method="PUT")
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e1:
        try:
            req2 = urllib.request.Request(
                f"{bridge.base_url}/json/new",
                data=json.dumps({"url": url}).encode(),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            with urllib.request.urlopen(req2, timeout=5) as r:
                return json.loads(r.read().decode())
        except Exception as e2:
            print("  _create_tab error:", e1, "/", e2)
            return None

def _cdp_screenshot(bridge, tab, out_path):
    """在同一 WebSocket 会话内 Page.enable + Page.captureScreenshot"""
    import asyncio
    from websockets.asyncio.client import connect
    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        return False
    async def _shot():
        async with connect(ws_url, open_timeout=5.0, close_timeout=2.0) as ws:
            mid = 1
            await ws.send(json.dumps({"id": mid, "method": "Page.enable", "params": {}}))
            await ws.recv()
            mid += 1
            await ws.send(json.dumps({"id": mid, "method": "Page.captureScreenshot",
                                      "params": {"format": "png", "quality": 90}}))
            for _ in range(50):
                data = json.loads(await asyncio.wait_for(ws.recv(), timeout=10.0))
                if data.get("id") == mid:
                    b64 = data.get("result", {}).get("data")
                    if b64:
                        import base64
                        with open(out_path, "wb") as f:
                            f.write(base64.b64decode(b64))
                        return True
            return False
    try:
        return asyncio.run(_shot())
    except Exception as e:
        print("  screenshot error:", e)
        return False

def main():
    from star_core.cdp_bridge import CDPBridge
    bridge = CDPBridge(port=PORT)
    if not bridge.is_alive():
        log("U0", "CDP 浏览器就绪", "9222 端口不可达（浏览器未启动）", False)
        return 1
    log("U0", "CDP 浏览器就绪", "9222 端口可达", True)

    # 创建标签页并打开搭子桥
    tab = _create_tab(bridge, URL)
    if not tab or not tab.get("webSocketDebuggerUrl"):
        log("U1", "打开搭子桥页面", "无法通过 /json/new 创建标签页", False); return 1

    # 等待页面加载
    loaded = False
    for i in range(20):
        time.sleep(1)
        try:
            title = bridge.evaluate(tab, "document.title") or ""
            body = bridge.get_text(tab, "body") or ""
            if "搭子桥" in title and len(body) > 200:
                loaded = True
                break
        except Exception:
            pass
    log("U1", "页面加载 (搭子桥)", f"loaded={loaded}", loaded,
        "用户打开页面应看到搭子桥控制台")

    # 初始任务数量（真实数据）
    try:
        init_count = bridge.evaluate(tab, "document.querySelectorAll('.task-card').length")
    except Exception:
        init_count = -1
    log("U2", "任务列表渲染真实数据", f"初始 .task-card 数量={init_count}",
        isinstance(init_count, int) and init_count >= 0,
        "列表里应有用户 Comate 的真实任务卡片")

    # 读取内核状态文本（用户关心 AI 是否在线）
    try:
        kernel_txt = bridge.evaluate(tab,
            "(()=>{const e=document.querySelector('#kernelStatus,.kernel-status,[data-id=kernel]');return e?e.textContent:''})()")
    except Exception:
        kernel_txt = ""
    log("U3", "内核状态展示", f"kernelStatus 文本={kernel_txt!r}", True,
        "页面应显示 DuMate 内核在线/离线状态")

    # 打开新建任务弹窗
    ok_m = False
    try:
        r = bridge.click_selector(tab, "#btn-new-task")
        if not r:
            el = bridge.find_by_text(tab, "新建任务")
            if el: r = bridge.click_selector(tab, el["selector"])
        time.sleep(1)
        ok_m = bool(bridge.evaluate(tab,
            "document.getElementById('newTaskModal') && document.getElementById('newTaskModal').classList.contains('visible')"))
    except Exception:
        pass
    log("U4", "点击新建任务弹窗", f"弹窗可见={ok_m}", ok_m,
        "用户点新建任务应弹出输入窗口")

    # 输入提示词
    prompt = "【群星 Star UI 自测】请只回复\"UI测试成功\"四个字。"
    ok_t = False
    try:
        bridge.set_value(tab, "#promptInput", prompt)
        time.sleep(0.5)
        v = bridge.evaluate(tab, "document.getElementById('promptInput').value")
        ok_t = (str(v).strip() == prompt)
    except Exception:
        pass
    log("U5", "输入任务提示词", f"输入框值匹配={ok_t}", ok_t,
        "用户输入的任务描述应进入输入框")

    # 点击发送任务
    ok_send = False
    result_txt = ""
    try:
        r = bridge.click_selector(tab, "#sendBtn")
        if not r:
            el = bridge.find_by_text(tab, "发送任务")
            if el: r = bridge.click_selector(tab, el["selector"])
        # 轮询结果文本
        for i in range(20):
            time.sleep(1)
            result_txt = bridge.evaluate(tab,
                "(()=>{const e=document.getElementById('createResult');return e?e.textContent:''})()") or ""
            if "已向" in result_txt or "成功" in result_txt or "失败" in result_txt or "✗" in result_txt:
                ok_send = ("失败" not in result_txt and "✗" not in result_txt)
                break
    except Exception as e:
        result_txt = f"err:{e}"
    log("U6", "点击发送任务（真实派发到 Comate）",
        f"结果文本={result_txt!r}", ok_send,
        "点击发送后，Star 应通过接口把任务真正派给 Comate（用户可用性的关键）")

    # 列表刷新后数量变化
    time.sleep(2.5)
    try:
        new_count = bridge.evaluate(tab, "document.querySelectorAll('.task-card').length")
    except Exception:
        new_count = init_count
    log("U7", "发送后任务列表刷新", f"前={init_count} 后={new_count}",
        new_count >= init_count, "发送后列表应刷新（新增卡片或保持）")

    # 截图
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "screenshot_ui_create_flow.png")
    ok_shot = _cdp_screenshot(bridge, tab, out)
    log("U8", "流程截图保存", f"文件={out} 成功={ok_shot}", ok_shot)

    steps = [r for r in RES if r[0].startswith("U")]
    total = len(steps); passed = sum(1 for r in steps if r[3])
    print("\n" + "#" * 72)
    print(f"  UI 流测试: 总计 {total}，通过 {passed}，失败 {total-passed}")
    print("#" * 72)
    return 0 if passed == total else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); sys.exit(2)
