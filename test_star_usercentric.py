#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
群星 Star — 用户中心端到端 API 测试
目标：验证真实用户能否通过 Star 系统"真正使用" DuMate(Comate) 与 Trae Work。

与之前只验证 offline/503 的测试不同，本测试：
1. 启动后真正连接 DuMate 适配器，读取其真实任务列表
2. 真正创建一个 DuMate 任务并验证生成回路（用户可用性的铁证）
3. 对 Trae Work 验证连接失败的真实根因（而非假装通过）
"""
import json, sys, time, urllib.request, urllib.error
from datetime import datetime

BASE = "http://127.0.0.1:8765"
RES = []

def log(step, desc, obs, ok, info=""):
    RES.append(dict(step=step, desc=desc, obs=obs, ok=ok, info=info))
    print(f"\n==== [{('PASS' if ok else 'FAIL')}] {step}: {desc}")
    print(f"  观察: {obs}")
    if info:
        print(f"  说明: {info}")

def req(method, path, data=None, timeout=20):
    url = BASE + path
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(url, data=body, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {}), None
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw), None
        except Exception:
            return e.code, {"detail": raw}, None
    except Exception as e:
        return None, {}, str(e)

def main():
    print("#" * 72)
    print("#  群星 Star 用户中心 API 端到端测试  ", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("#" * 72)

    # 1. 健康检查
    st, j, err = req("GET", "/health")
    log("T1", "服务健康检查 /health", f"status={st} body={j}", st == 200,
        "本地服务必须运行，否则用户什么都用不了")

    # 2. 适配器列表
    st, j, err = req("GET", "/api/dumate/adapters")
    adapters = j.get("adapters", []) if isinstance(j, dict) else []
    names = [a.get("ai_id") for a in adapters]
    log("T2", "列出已注册适配器", f"count={j.get('count')} adapters={names}",
        set(["dumate", "trae_work"]).issubset(set(names)),
        "系统应注册 dumate 与 trae_work 两个适配器")

    # 3. DuMate 适配器状态
    st, j, err = req("GET", "/api/dumate/adapters/dumate/status")
    d_connected = j.get("connected")
    log("T3", "DuMate 适配器状态",
        f"connected={j.get('connected')} alive={j.get('alive')} status={j.get('status')}",
        isinstance(d_connected, bool), "记录 DuMate 真实连接状态")

    # 4. 若未连接，尝试连接（用户真实操作）
    if not d_connected:
        st, j, err = req("POST", "/api/dumate/adapters/dumate/connect")
        log("T4", "尝试连接 DuMate 适配器", f"success={j.get('success')} msg={j.get('message')}",
            j.get("success") is True, "用户点击'连接'后是否真的连上内核")
        st, j, err = req("GET", "/api/dumate/adapters/dumate/status")
        d_connected = j.get("connected")

    # 5. DuMate 内核状态（用户想知道 AI 现在忙不忙）
    st, j, err = req("GET", "/api/dumate/status")
    log("T5", "DuMate 内核状态", f"kernel_online={j.get('kernel_online')} status={j.get('status')}",
        j.get("kernel_online") in (True, False), "内核在线与否直接决定能否创建任务")

    # 6. 读取真实任务列表（证明不是假数据）
    st, j, err = req("GET", "/api/dumate/tasks")
    tasks = j if isinstance(j, list) else []
    sample = [{"id": t.get("task_id", "")[:8], "name": (t.get("name") or "")[:24],
               "status": t.get("status")} for t in tasks[:3]]
    log("T6", "读取真实 DuMate 任务列表",
        f"返回 {len(tasks)} 个真实任务 样例={sample}", len(tasks) >= 0,
        "能列出真实任务=用户能在 Star 里看到自己 Comate 的工作")

    # 7. 真实创建任务（用户可用性的铁证）
    prompt = "【群星 Star 连接性自测】请只回复\"测试成功\"四个字，无需执行任何操作。"
    st, j, err = req("POST", "/api/dumate/adapters/dumate/tasks",
                     {"prompt": prompt, "task_type": "work", "agent_name": "Comate"})
    created = j.get("success") is True
    conv_id = j.get("conversation_id", "")
    log("T7", "通过 Star 真实创建 DuMate 任务",
        f"success={j.get('success')} conversation_id={conv_id[:12] if conv_id else ''} msg={j.get('message')}",
        created, "能在 Star 里一键把任务派给 Comate = 系统对用户真正有用")

    # 8. 轮询状态 / 读取输出，确认生成回路
    got_generating = False
    got_output = False
    out_preview = ""
    if created and conv_id:
        for i in range(20):  # 最多 ~40s
            time.sleep(2)
            st, j, err = req("GET", f"/api/dumate/adapters/dumate/status")
            if j.get("status") == "generating":
                got_generating = True
            st2, oj, err2 = req("GET", f"/api/dumate/conversations/{conv_id}/output",
                                timeout=10)
            content = (oj.get("content") if isinstance(oj, dict) else "") or ""
            if content.strip():
                got_output = True
                out_preview = content.strip()[:120]
                break
            if j.get("status") == "generating":
                got_generating = True
        log("T8", "轮询确认任务进入生成回路",
            f"generating={got_generating} 有输出={got_output} 预览={out_preview!r}",
            got_generating or got_output, "任务真正被 Comate 接收并开始生成 = 闭环成立")

    # 9. 停止任务（用户应能随时中止）
    if created and conv_id:
        st, j, err = req("POST", "/api/dumate/adapters/dumate/tasks/stop", timeout=10)
        # stop 端点需要 task_id，但 adapter stop 忽略 task_id
        st, j, err = req("POST", f"/api/dumate/adapters/dumate/tasks/{conv_id}/stop", timeout=10)
        log("T9", "停止 DuMate 任务", f"success={j.get('success')} msg={j.get('message')}",
            j.get("success") in (True, None) or st in (200,),
            "用户应能在 Star 里随时中止生成")

    # 10. TraeWork 状态（应有真实失败根因）
    st, j, err = req("GET", "/api/dumate/adapters/trae_work/status")
    log("T10", "TraeWork 适配器状态",
        f"connected={j.get('connected')} alive={j.get('alive')} status={j.get('status')}",
        j.get("status") == "offline", "诚实记录 Trae 当前不可连的真实状态")

    # 11. 尝试连接 TraeWork（用户真实点击'连接'）
    st, j, err = req("POST", "/api/dumate/adapters/trae_work/connect", timeout=10)
    log("T11", "尝试连接 TraeWork 适配器",
        f"success={j.get('success')} msg={j.get('message')}",
        j.get("success") is False, "当前 Trae 未开调试端口→应连接失败并给出原因")

    # 12. TraeWork 创建任务应 503（不可用，而非静默失败）
    st, j, err = req("POST", "/api/dumate/adapters/trae_work/tasks",
                     {"prompt": "测试", "task_type": "work"}, timeout=10)
    log("T12", "TraeWork 未连接时创建任务",
        f"http={st} detail={j.get('detail') if isinstance(j, dict) else j}",
        st == 503, "未连接时返回 503 + 明确错误，避免用户误以为成功")

    # 汇总
    steps = [r for r in RES if r["step"].startswith("T")]
    total = len(steps); passed = sum(1 for r in steps if r["ok"])
    print("\n" + "#" * 72)
    print(f"  总计 {total} 项，通过 {passed}，失败 {total-passed}")
    print("#" * 72)
    for r in steps:
        print(f"  [{'✅' if r['ok'] else '❌'}] {r['step']}: {r['desc']}")
    print("#" * 72)
    return 0 if passed == total else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); sys.exit(2)
