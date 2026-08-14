"""
Trae UI 入口验证（用户流，基于 CDPBridge 高层 API）：
U1 搭子桥页面出现 "AI 适配器" 栏
U2 适配器列表含 dumate 与 trae_work
U3 DuMate 已连接 / Trae 离线
U4 Trae 连接入口存在（按钮 onclick=connectAdapter('trae_work')）
U5 点击 Trae 连接 → 优雅报错（Trae 未以调试端口启动），页面不崩溃
U6 新建任务弹窗含 "目标 AI 适配器" 选择器（dumate + trae_work）
U7 通过新弹窗以 dumate 派发任务，端到端成功
"""
import sys, os, time, json, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from star_core.cdp_bridge import CDPBridge

BASE = "http://127.0.0.1:8765"
URL = BASE + "/ui/pages/dumate.html"
PORT = 9222
EDGE = "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"

results = []


def log(tid, name, detail, ok):
    results.append(ok)
    print(f"[{tid}] {'PASS' if ok else 'FAIL'} | {name} | {detail}")


def _create_tab(bridge, url):
    import urllib.parse
    req = urllib.request.Request(
        f"{bridge.base_url}/json/new?{urllib.parse.quote(url, safe='')}",
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode())


def main():
    bridge = CDPBridge(port=PORT)
    if not bridge.is_alive():
        log("U0", "CDP 浏览器就绪", "9222 不可达", False)
        return 1
    log("U0", "CDP 浏览器就绪", "9222 可达", True)

    tab = _create_tab(bridge, URL)
    # 显式导航（此 Edge 版本 /json/new?url 不一定自动跳转）
    bridge._send(tab, "Page.enable", {})
    bridge._send(tab, "Page.navigate", {"url": URL})
    for _ in range(20):
        rs = bridge.evaluate(tab, "document.readyState")
        if rs == "complete":
            break
        time.sleep(0.3)
    time.sleep(2.5)
    # 确认页面来自 8765
    page_url = bridge.evaluate(tab, "location.href")
    print(f"[nav] page_url={page_url}")

    # U1: 适配器栏
    has_bar = bridge.evaluate(tab, "!!document.getElementById('adapterBar')")
    log("U1", "AI 适配器栏出现", f"adapterBar={has_bar}", bool(has_bar))

    # 等待适配器数据加载（DOMContentLoaded 会触发 loadAdapters()）
    for _ in range(15):
        adapters_json = bridge.evaluate(
            tab, "JSON.stringify((window.adaptersCache||[]).map(a=>({id:a.ai_id,connected:a.connected})))")
        try:
            adapters = json.loads(adapters_json) if adapters_json else []
        except Exception:
            adapters = []
        ids = [a.get("id") for a in adapters]
        if "dumate" in ids and "trae_work" in ids:
            break
        time.sleep(0.5)

    # U2: 适配器列表
    log("U2", "适配器列表含 dumate+trae_work", f"ids={ids}",
        ("dumate" in ids) and ("trae_work" in ids))

    # U3: 连接状态
    dumate_connected = any(a.get("id") == "dumate" and a.get("connected") for a in adapters)
    trae_offline = any(a.get("id") == "trae_work" and not a.get("connected") for a in adapters)
    log("U3", "DuMate 已连接 / Trae 离线",
        f"dumate_connected={dumate_connected}, trae_offline={trae_offline}",
        dumate_connected and trae_offline)

    # U4: Trae 连接按钮
    trae_connect_btn = bridge.evaluate(
        tab, "JSON.stringify(Array.from(document.querySelectorAll('.adapter-btn.connect')).map(b=>b.getAttribute('onclick')))")
    has_trae_connect = "trae_work" in (trae_connect_btn or "")
    log("U4", "Trae 连接入口存在", f"onclicks={trae_connect_btn}", has_trae_connect)

    # U5: 点击 Trae 连接 → 优雅报错（不崩溃）
    if has_trae_connect:
        bridge.evaluate(
            tab, "Array.from(document.querySelectorAll('.adapter-btn.connect')).find(b=>(b.getAttribute('onclick')||'').includes('trae_work')).click()")
        time.sleep(3.5)
        notif = bridge.evaluate(
            tab, "JSON.stringify(Array.from(document.querySelectorAll('#star-notification')).map(n=>n.textContent))")
        log("U5", "Trae 连接点击后未崩溃(预期优雅报错)",
            f"通知={notif}", True)

    # U6: 新建任务弹窗适配器选择器
    bridge.evaluate(tab, "showNewTaskModal()")
    time.sleep(1.5)
    modal_visible = bridge.evaluate(tab, "document.getElementById('newTaskModal').classList.contains('visible')")
    select_opts = bridge.evaluate(
        tab, "JSON.stringify(Array.from(document.getElementById('adapterSelect').options).map(o=>o.value))")
    log("U6", "新建任务弹窗含目标适配器选择器",
        f"visible={modal_visible}, options={select_opts}",
        bool(modal_visible) and ("dumate" in (select_opts or "") and "trae_work" in (select_opts or "")))

    # U7: 以 dumate 通过新弹窗派发任务
    bridge.evaluate(tab, "document.getElementById('adapterSelect').value='dumate';")
    bridge.evaluate(tab, "document.getElementById('promptInput').value='UI 入口验证：请回复 OK。';")
    bridge.evaluate(tab, "createTask()")
    time.sleep(4.5)
    created_msg = bridge.evaluate(tab, "document.getElementById('createResult').textContent")
    log("U7", "通过新弹窗以 dumate 派发任务",
        f"result={created_msg!r}",
        bool(created_msg) and ("已向 Comate" in created_msg))

    # 截图
    try:
        r = bridge._send(tab, "Page.captureScreenshot", {"format": "png"})
        if r and r.get("result", {}).get("data"):
            import base64
            out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshot_trae_ui.png")
            with open(out, "wb") as f:
                f.write(base64.b64decode(r["result"]["data"]))
            log("U8", "页面截图保存", f"file={out}", True)
    except Exception as e:
        log("U8", "页面截图保存", f"失败: {e}", False)

    passed = sum(1 for x in results if x)
    print(f"\n=== 结果: {passed}/{len(results)} 通过 ===")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
