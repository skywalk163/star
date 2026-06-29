#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trae Solo 多维度数据探索脚本
探索 PID 18424 (Trae Solo) 及其相关进程的通信和数据获取渠道。
"""

import os
import sys
import json
import glob as glob_mod
import datetime
import socket
import subprocess
import urllib.request
import urllib.error
import time

# ============================================================
# 辅助函数
# ============================================================

def section(title):
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def safe_read_file(path, max_bytes=4096):
    """安全读取文件，限制大小"""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read(max_bytes)
    except Exception as e:
        return f"[读取失败] {e}"


def safe_size(path):
    try:
        return os.path.getsize(path)
    except:
        return -1


def safe_mtime(path):
    try:
        return datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M:%S')
    except:
        return 'N/A'


# ============================================================
# 1. 日志文件分析
# ============================================================
def explore_logs(base_dir):
    section("1. 日志文件分析")
    log_patterns = ['*.log', '*.txt', '*.json']
    candidates = []
    for pattern in log_patterns:
        found = glob_mod.glob(os.path.join(base_dir, '**', pattern), recursive=True)
        candidates.extend(found)

    # 按修改时间排序，取最近修改的 30 个文件
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)

    print(f"  在 {base_dir} 下找到 {len(candidates)} 个日志/文本/JSON 文件\n")

    # 检查最近修改的 20 个
    examined = 0
    for fp in candidates[:20]:
        mtime = safe_mtime(fp)
        size = safe_size(fp)
        relpath = os.path.relpath(fp, base_dir)
        print(f"  [{mtime}] ({size:>8} bytes) {relpath}")
        content = safe_read_file(fp, max_bytes=2000)
        if content.strip():
            # 显示内容的前几行
            lines = content.splitlines()
            preview = '\n'.join(lines[:8])
            print(f"    --- 预览 (前 {min(8, len(lines))} 行) ---")
            for line in lines[:8]:
                print(f"    | {line.strip()}")
            print()
        examined += 1

    print(f"\n  共检查了 {examined} 个最近修改的文件\n")

    # 特别关注包含 task / conversation / dialogue / agent 等关键词的日志
    print("  --- 搜索包含关键词 (task/conversation/agent/dialogue/chat) 的日志文件 ---")
    keywords = ['task', 'conversation', 'agent', 'dialogue', 'chat', 'message', 'prompt']
    for fp in candidates:
        try:
            with open(fp, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read(50000)
                content_lower = content.lower()
                for kw in keywords:
                    if kw in content_lower:
                        relpath = os.path.relpath(fp, base_dir)
                        size = safe_size(fp)
                        mtime = safe_mtime(fp)
                        print(f"  [关键词:{kw}] [{mtime}] ({size} bytes) {relpath}")
                        # 找出关键词上下文
                        idx = content_lower.find(kw)
                        start = max(0, idx - 100)
                        end = min(len(content), idx + 200)
                        context = content[start:end].strip()
                        print(f"    上下文: ...{context}...")
                        print()
                        break
        except:
            continue


# ============================================================
# 2. Chrome DevTools Protocol（调试端口）
# ============================================================
def explore_cdp():
    section("2. Chrome DevTools Protocol (调试端口)")
    try:
        import psutil
        target_pid = 18424
        try:
            p = psutil.Process(target_pid)
            cmdline = p.cmdline()
            print(f"  PID {target_pid} 命令行:")
            for i, arg in enumerate(cmdline):
                print(f"    [{i}] {arg}")

            # 检查调试端口参数
            debug_flags = [a for a in cmdline if 'remote-debugging' in a.lower()]
            if debug_flags:
                print(f"\n  ✅ 发现 --remote-debugging-port 标志:")
                for f in debug_flags:
                    print(f"    {f}")
            else:
                print(f"\n  ❌ 未发现 --remote-debugging-port 标志")

            # 检查其他 Chrome/Electron 相关参数
            electron_flags = [a for a in cmdline if any(x in a.lower() for x in ['inspect', 'debug', 'devtools'])]
            if electron_flags:
                print(f"  其他调试相关参数:")
                for f in electron_flags:
                    print(f"    {f}")

        except psutil.NoSuchProcess:
            print(f"  ❌ PID {target_pid} 不存在")
    except ImportError:
        print("  ❌ psutil 未安装，跳过")


# ============================================================
# 3. agent-tool-host 进程分析
# ============================================================
def explore_agent_host():
    section("3. agent-tool-host 进程分析")
    try:
        import psutil
        agent_pids = [12808, 18596]
        for pid in agent_pids:
            try:
                p = psutil.Process(pid)
                print(f"\n  PID {pid} - {p.name()}")
                print(f"  状态: {p.status()}")
                print(f"  创建时间: {datetime.datetime.fromtimestamp(p.create_time()).strftime('%Y-%m-%d %H:%M:%S')}")
                cmdline = p.cmdline()
                print(f"  命令行:")
                for i, arg in enumerate(cmdline):
                    print(f"    [{i}] {arg}")

                # 检查端口相关的参数
                port_flags = [a for a in cmdline if any(x in a for x in ['port', 'Port', 'PORT', ':', 'http', 'socket'])]
                if port_flags:
                    print(f"  可能包含端口/服务信息的参数:")
                    for f in port_flags:
                        print(f"    {f}")

                # 检查环境变量
                try:
                    env = p.environ()
                    port_envs = {k: v for k, v in env.items() if any(x in k.lower() for x in ['port', 'host', 'addr', 'url', 'endpoint'])}
                    if port_envs:
                        print(f"  端口/地址相关的环境变量:")
                        for k, v in port_envs.items():
                            print(f"    {k} = {v}")
                except (psutil.AccessDenied, Exception) as e:
                    print(f"  无法读取环境变量: {e}")

                # 网络连接
                try:
                    conns = p.connections()
                    if conns:
                        print(f"  网络连接:")
                        for conn in conns:
                            print(f"    {conn.laddr} -> {conn.raddr}  status={conn.status}")
                    else:
                        print(f"  无网络连接")
                except (psutil.AccessDenied, Exception) as e:
                    print(f"  无法读取网络连接: {e}")

                # 打开的文件
                try:
                    open_files = p.open_files()
                    if open_files:
                        print(f"  打开的文件 (前 10 个):")
                        for f in open_files[:10]:
                            print(f"    {f.path}")
                        if len(open_files) > 10:
                            print(f"    ... 还有 {len(open_files) - 10} 个")
                except (psutil.AccessDenied, Exception) as e:
                    print(f"  无法读取打开的文件: {e}")

            except psutil.NoSuchProcess:
                print(f"  ❌ PID {pid} 不存在")
    except ImportError:
        print("  ❌ psutil 未安装，跳过")


# ============================================================
# 4. 本地 Web 服务扫描
# ============================================================
def explore_web_services():
    section("4. 本地 Web 服务扫描")
    ports_to_check = [8312, 8313, 8322, 3000, 5173, 5174, 9222, 9223, 9229, 9230]

    def check_port(port):
        """先检查端口是否开放（TCP 连接测试）"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result == 0

    def http_get(url, timeout=2):
        """尝试 HTTP GET 请求"""
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=timeout)
            status = resp.status
            content_type = resp.headers.get('Content-Type', '')
            body = resp.read(3000).decode('utf-8', errors='replace')
            return status, content_type, body
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get('Content-Type', ''), e.read(500).decode('utf-8', errors='replace')
        except Exception as e:
            return None, str(e), ''

    print(f"  将扫描端口: {ports_to_check}\n")
    for port in ports_to_check:
        if check_port(port):
            print(f"  🔓 端口 {port} 开放")
            # 尝试 HTTP
            status, ctype, body = http_get(f"http://localhost:{port}")
            if status:
                print(f"    HTTP 响应: status={status}, Content-Type={ctype}")
                # 显示部分内容
                body_preview = body[:500].strip()
                if body_preview:
                    print(f"    响应体预览: {body_preview[:300]}")
                print()
                # 尝试几个常见路径
                for path in ['/api', '/health', '/status', '/v1', '/api/v1']:
                    s, ct, b = http_get(f"http://localhost:{port}{path}")
                    if s and s != status:  # 不同的响应码
                        print(f"    {path} -> status={s}, type={ct}")
                    elif s and b != body:  # 不同的内容
                        print(f"    {path} -> status={s}, preview={b[:200]}")
            else:
                print(f"    HTTP 请求失败: {ctype}\n")
        else:
            print(f"  🔒 端口 {port} 关闭")


# ============================================================
# 5. AppData 目录结构
# ============================================================
def explore_appdata_structure(base_dir):
    section("5. AppData 目录结构")
    if not os.path.exists(base_dir):
        print(f"  ❌ 目录不存在: {base_dir}")
        return

    print(f"  根目录: {base_dir}\n")

    # 列出直接子目录和文件
    entries = sorted(os.listdir(base_dir))
    print(f"  直接子项目 ({len(entries)} 个):")
    for entry in entries:
        full = os.path.join(base_dir, entry)
        mtime = safe_mtime(full)
        if os.path.isdir(full):
            # 计算目录大小
            try:
                size = sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, fn in os.walk(full) for f in fn)
            except:
                size = -1
            print(f"    📁 [{mtime}] ({_fmt_size(size)}) {entry}/")
        else:
            print(f"    📄 [{mtime}] ({_fmt_size(safe_size(full))}) {entry}")

    # 查找最近 7 天内修改过的文件
    print(f"\n  最近 7 天内修改过的文件:")
    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(days=7)
    recent_files = []
    for root, dirs, files in os.walk(base_dir):
        # 跳过 node_modules 等大目录
        skip_dirs = {'node_modules', '.git', '__pycache__', 'Cache', 'code_cache'}
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            fp = os.path.join(root, f)
            try:
                mtime = os.path.getmtime(fp)
                if datetime.datetime.fromtimestamp(mtime) > cutoff:
                    rel = os.path.relpath(fp, base_dir)
                    recent_files.append((mtime, safe_size(fp), rel))
            except:
                pass

    recent_files.sort(key=lambda x: x[0], reverse=True)
    for mtime, size, relpath in recent_files[:30]:
        dt = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        print(f"    [{dt}] ({_fmt_size(size)}) {relpath}")

    print(f"\n  (共 {len(recent_files)} 个最近修改的文件，显示前 30 个)")


def _fmt_size(size):
    if size < 0:
        return 'N/A'
    if size < 1024:
        return f'{size} B'
    elif size < 1024**2:
        return f'{size/1024:.1f} KB'
    else:
        return f'{size/1024**2:.1f} MB'


# ============================================================
# 6. 进程网络连接
# ============================================================
def explore_network_connections():
    section("6. 进程网络连接")
    try:
        import psutil
        target_pids = {
            18424: 'Trae Solo',
            12808: 'agent-tool-host (1)',
            18596: 'agent-tool-host (2)',
        }

        for pid, label in target_pids.items():
            try:
                p = psutil.Process(pid)
                print(f"\n  {label} (PID {pid}):")
                conns = p.connections()
                if conns:
                    for conn in conns:
                        raddr_str = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "N/A"
                        laddr_str = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "N/A"
                        print(f"    {laddr_str:>22} -> {raddr_str:<22}  type={conn.type.name}  status={conn.status}")
                else:
                    print(f"    无网络连接")

            except psutil.NoSuchProcess:
                print(f"\n  {label} (PID {pid}): ❌ 不存在")

    except ImportError:
        print("  ❌ psutil 未安装，跳过")


# ============================================================
# 7. 额外：检查 Trae Solo 进程详情
# ============================================================
def explore_process_details():
    section("额外：Trae Solo 进程详情 (PID 18424)")
    try:
        import psutil
        p = psutil.Process(18424)

        # 基本信息
        print(f"  名称: {p.name()}")
        print(f"  可执行文件: {p.exe()}")
        print(f"  工作目录: {p.cwd()}")
        print(f"  状态: {p.status()}")
        print(f"  创建时间: {datetime.datetime.fromtimestamp(p.create_time()).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  CPU 使用率: {p.cpu_percent(interval=0.1)}%")
        print(f"  内存使用: {_fmt_size(p.memory_info().rss)}")
        print(f"  子进程数: {len(p.children())}")

        # 子进程
        children = p.children()
        if children:
            print(f"\n  子进程:")
            for child in children:
                try:
                    print(f"    PID {child.pid:>6} - {child.name()} ({child.status()})")
                except:
                    print(f"    PID {child.pid:>6} - (无法访问)")

        # 打开的文件
        try:
            open_files = p.open_files()
            if open_files:
                print(f"\n  打开的文件 (前 20 个):")
                # 按路径排序
                sorted_files = sorted(open_files, key=lambda x: x.path)
                for f in sorted_files[:20]:
                    print(f"    {f.path}")
                if len(open_files) > 20:
                    print(f"    ... 还有 {len(open_files) - 20} 个")
                print(f"  总计: {len(open_files)} 个打开的文件")
        except psutil.AccessDenied:
            print(f"\n  打开的文件: 访问被拒绝")

        # 尝试获取环境变量中的关键信息
        try:
            env = p.environ()
            interesting_vars = ['NODE_ENV', 'ELECTRON_', 'TRAE_', 'VSCODE_', 'PORT', 'HOST', 'HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA']
            print(f"\n  相关环境变量:")
            for k, v in sorted(env.items()):
                if any(k.startswith(prefix) for prefix in interesting_vars):
                    print(f"    {k} = {v}")
        except (psutil.AccessDenied, Exception) as e:
            print(f"\n  环境变量: {e}")

    except psutil.NoSuchProcess:
        print("  ❌ PID 18424 不存在")
    except ImportError:
        print("  ❌ psutil 未安装，跳过")


# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    APP_DATA_DIR = r'C:\Users\Admin\AppData\Roaming\TRAE SOLO CN'
    print(f"Trae Solo 探索脚本")
    print(f"运行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"AppData 目录: {APP_DATA_DIR}")
    print(f"目标 PID: 18424 (Trae Solo), 12808/18596 (agent-tool-host)\n")

    # 确保 psutil 可用
    try:
        import psutil
    except ImportError:
        print("⚠️  psutil 未安装，尝试安装...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'psutil'])
        print("✅ psutil 安装完成\n")

    # 确保 requests 可用
    try:
        import requests
        HAS_REQUESTS = True
    except ImportError:
        HAS_REQUESTS = False

    # 执行各项探索
    # 这些任务之间无依赖，可以顺序执行
    explore_process_details()
    explore_cdp()
    explore_agent_host()
    explore_network_connections()
    explore_web_services()

    if os.path.exists(APP_DATA_DIR):
        explore_appdata_structure(APP_DATA_DIR)
        explore_logs(APP_DATA_DIR)
    else:
        print(f"\n⚠️  AppData 目录不存在: {APP_DATA_DIR}")

    print("\n" + "=" * 70)
    print("  探索完成")
    print("=" * 70)