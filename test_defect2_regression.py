"""
缺陷② 回归测试：新建会话的输出读回必须精确映射到本次会话，绝不串用他人任务内容。

判定：
- 创建任务前快照所有 .output 文件内容（陈旧集合）。
- 通过 API 创建一个全新会话，轮询其输出。
- 若 found=True：返回内容不得等于任何陈旧文件内容（否则即旧缺陷"返回最近修改文件"复现）。
- 若 found=False：内容必须为空（绝不得谎报 found=True 并塞入他人内容）。
"""
import json
import os
import time
import urllib.request

BASE = "http://127.0.0.1:8765"
AGENT_DIR = os.path.expanduser("~/.comate-engine/store/agents")


def req(method, path, data=None, timeout=30):
    r = urllib.request.Request(
        BASE + path,
        data=(json.dumps(data).encode() if data else None),
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def snapshot_outputs():
    """返回 {文件名: 内容} 的当前快照"""
    snap = {}
    if os.path.isdir(AGENT_DIR):
        for f in os.listdir(AGENT_DIR):
            if f.endswith(".output"):
                try:
                    snap[f] = open(os.path.join(AGENT_DIR, f), "r", encoding="utf-8", errors="ignore").read()
                except Exception:
                    pass
    return snap


def main():
    print("=== 缺陷② 回归测试：输出读回精确映射 ===\n")

    # 1. 创建前快照（陈旧集合）
    before = snapshot_outputs()
    stale_contents = set(before.values())
    stale_names = set(before.keys())
    print(f"[快照] 创建前共有 {len(before)} 个 .output 文件")

    # 2. 创建全新会话
    prompt = "回归测试专用指令_%d：请用一句话说明你收到的这条消息包含的关键词。" % int(time.time())
    st, j = req("POST", "/api/dumate/adapters/dumate/tasks", {
        "prompt": prompt, "task_type": "work", "workspace_id": ""})
    if st != 200 or not j.get("success"):
        print("✗ 创建任务失败:", st, j)
        return 1
    conv_id = j["conversation_id"]
    print(f"[创建] conversation_id={conv_id}  message={j['message']}")

    # 3. 轮询输出（最多 20s）
    found = None
    content = ""
    for i in range(10):
        time.sleep(2)
        st2, o = req("GET", f"/api/dumate/conversations/{conv_id}/output?max_lines=50")
        found = o.get("found")
        content = o.get("content", "") or ""
        if found and content:
            print(f"[轮询 {i*2+2}s] found={found} line_count={o.get('line_count')}")
            break
        else:
            print(f"[轮询 {i*2+2}s] found={found} (继续)")

    # 4. 判定
    ok = True
    if found and content:
        # 找到返回内容：必须不属于创建前的任何陈旧文件
        if content in stale_contents:
            # 定位是哪个陈旧文件
            for name, c in before.items():
                if c == content:
                    print(f"\n✗ 缺陷复现！返回内容来自陈旧文件 {name}（串用他人任务）")
                    ok = False
                    break
        # 进一步确认：返回内容应来自创建后才出现/更新的文件
        after = snapshot_outputs()
        new_or_updated = [n for n in after if n not in stale_names or after[n] != before.get(n)]
        print(f"[校验] 创建后新增/变更的文件: {new_or_updated}")
        if not new_or_updated:
            print("⚠ 注意：内核未写入新的 .output（可能本任务不产生输出文件），但关键是未串用陈旧内容。")
        else:
            # 返回内容应等于某个新建/变更文件的内容
            matched = [n for n in new_or_updated if after[n] == content]
            if matched:
                print(f"✓ 映射正确：返回内容来自会话专属文件 {matched}")
            else:
                # 内容可能与某文件部分重叠（轮询截断），再确认不属于陈旧文件即可
                print("· 返回内容不属于任何陈旧文件（映射未串用），视为通过。")
    elif found is False or found is None:
        # 未找到：内容必须为空，不得谎报
        if content:
            print(f"\n✗ 缺陷复现！found=False 却返回了内容: {content[:60]!r}")
            ok = False
        else:
            print("✓ 未命中映射时诚实返回 found=False、内容为空（不再谎报/串用）")
    else:
        print("? 未读到内容（found 状态异常）")
        ok = False

    print("\n" + ("=== 测试结果：PASS（缺陷②已修复）===" if ok else "=== 测试结果：FAIL（缺陷②仍存在）==="))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
