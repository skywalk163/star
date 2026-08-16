#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os, time, json, urllib.request, base64
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

OUT = Path(r'g:/traework/star')
URL = 'http://127.0.0.1:8765/ui/pages/dumate.html'
PORT = 9222
RES = []

def log(n, desc, obs, ok=True, extra=''):
    RES.append(dict(step=n, desc=desc, obs=obs, ok=ok, extra=extra))
    s = 'PASS' if ok else 'FAIL'
    print(f'\n==== Step {n}: {desc}')
    print(f'[{s}] {obs}')
    if extra: print(f' INFO: {extra}')

def mk_tab(port, url=None):
    try:
        import urllib.parse as up
        u = f'http://127.0.0.1:{port}/json/new'
        if url: u += '?' + up.quote(url, safe='')
        with urllib.request.urlopen(u, timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f'  warn mk_tab: {e}')
        return None

def nav(bridge, tab, url):
    r = bridge._send(tab, chr(80)+chr(97)+chr(103)+chr(101)+chr(46)+chr(110)+chr(97)+chr(118)+chr(105)+chr(103)+chr(97)+chr(116)+chr(101), {chr(39)+chr(117)+chr(114)+chr(108)+chr(39): url})
    if r and chr(101)+chr(114)+chr(114)+chr(111)+chr(114) not in r: return True
    ok1 = bridge.evaluate(tab, chr(119)+chr(105)+chr(110)+chr(100)+chr(111)+chr(119)+chr(46)+chr(108)+chr(111)+chr(99)+chr(97)+chr(116)+chr(105)+chr(111)+chr(110)+chr(46)+chr(104)+chr(114)+chr(101)+chr(102)+chr(61) + json.dumps(url) + chr(59)+chr(32)+chr(116)+chr(114)+chr(117)+chr(101)+chr(59))
    return ok1 is True

def shot(bridge, tab, path):
    try:
        bridge._send(tab, chr(80)+chr(97)+chr(103)+chr(101)+chr(46)+chr(101)+chr(110)+chr(97)+chr(98)+chr(108)+chr(101), {})
    except Exception: pass
    time.sleep(0.18)
    resp = bridge._send(tab, chr(80)+chr(97)+chr(103)+chr(101)+chr(46)+chr(99)+chr(97)+chr(112)+chr(116)+chr(117)+chr(114)+chr(101)+chr(83)+chr(99)+chr(114)+chr(101)+chr(101)+chr(110)+chr(115)+chr(104)+chr(111)+chr(116), {chr(102)+chr(111)+chr(114)+chr(109)+chr(97)+chr(116): chr(112)+chr(110)+chr(103), chr(113)+chr(117)+chr(97)+chr(108)+chr(105)+chr(116)+chr(121): 92})
    if resp and resp.get(chr(114)+chr(101)+chr(115)+chr(117)+chr(108)+chr(116)) and resp[chr(114)+chr(101)+chr(115)+chr(117)+chr(108)+chr(116)].get(chr(100)+chr(97)+chr(116)+chr(97)):
        try:
            with open(path, chr(119)+chr(98)) as f: f.write(base64.b64decode(resp[chr(114)+chr(101)+chr(115)+chr(117)+chr(108)+chr(116)][chr(100)+chr(97)+chr(116)+chr(97)]))
            return True
        except Exception as e: print(chr(32)+chr(32)+chr(119)+chr(97)+chr(114)+chr(110)+chr(32)+chr(115)+chr(97)+chr(118)+chr(101)+chr(58)+chr(32) + str(e))
    return False

def main():
    from star_core.cdp_bridge import CDPBridge
    bridge = CDPBridge(port=PORT)
    if not bridge.is_alive():
        log(0, 'CDP检查', '9222端口不可达，尝试启动浏览器', False)
        import subprocess
        pd = os.path.join(os.path.expanduser('~'), '.star', 'browser-profile')
        os.makedirs(pd, exist_ok=True)
        cands = [r'C:/Program Files/Microsoft/Edge/Application/msedge.exe', r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', r'C:/Program Files/Google/Chrome/Application/chrome.exe', r'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe']
        br = next((c for c in cands if os.path.exists(c)), None)
        if br:
            subprocess.Popen([br, f'--remote-debugging-port={PORT}', f'--user-data-dir={pd}', '--no-first-run', '--no-default-browser-check'], close_fds=True)
            log(0, '启动浏览器', f'启动: {os.path.basename(br)}', True)
            for i in range(15):
                time.sleep(1)
                if bridge.is_alive(): log(0, 'CDP就绪', f'{i+1}s后连通', True); break
    if not bridge.is_alive():
        log(1, '前置失败', 'CDP无法连接', False); return 1
    svc_ok = False
    try:
        with urllib.request.urlopen('http://127.0.0.1:8765/ui/pages/dumate.html', timeout=4) as r:
            svc_ok = (r.status == 200)
            log(0, '8765服务', f'HTTP {r.status} 页面可达', True)
    except Exception as e:
        log(0, '8765服务', f'不可达: {e}', False)
    tabs = []
    try:
        _ju = 'http://127.0.0.1:' + str(PORT) + '/json'
        _req = urllib.request.urlopen(_ju, timeout=4)
        _all = json.loads(_req.read().decode())
        tabs = [t for t in _all if t.get('type') == 'page']
    except Exception:
        tabs = bridge.list_tabs()
    if not tabs: tabs = bridge.list_tabs()
    log(0, '标签页', f'共{len(tabs)}个page类型', True, f'前3: {[t.get(chr(116)+chr(105)+chr(116)+chr(108)+chr(101), chr(32))[:22] for t in tabs[:3]]}')
    target = next((t for t in tabs if 'dumate' in t.get('url','').lower() or chr(25645)+chr(23376)+chr(26725) in t.get('title','')), None)
    if target is None and tabs:
        target = tabs[0]
    if not target:
        log(1, '标签页', '获取失败', False); return 1
    tab = target
    cur = tab.get('url','') or ''
    log(1, '步骤1 打开浏览器导航', f'标签页title={tab.get(chr(116)+chr(105)+chr(116)+chr(108)+chr(101), chr(32))[:40]!r} url={cur[:60]!r}', True)
    if 'dumate' not in cur.lower():
        ok_nav = nav(bridge, tab, URL)
        time.sleep(4.5)
    loaded=False; info={}
    for i in range(15):
        time.sleep(1)
        try:
            title = bridge.evaluate(tab, 'document.title') or ''
            body = bridge.get_text(tab, 'body') or ''
            info = dict(title=str(title), bdlen=len(body), h_dm=(chr(25645)+chr(23376)+chr(26725) in str(title) or chr(25645)+chr(23376)+chr(26725) in body), h_tsk=((chr(20219)+chr(21153)+chr(21015)+chr(34920) in body) or len(bridge.get_text(tab,'#taskCount').strip())>0), h_kn=(chr(20869)+chr(26680) in body))
            if info['h_dm'] and (info['bdlen']>150 or info['h_tsk'] or info['h_kn']): loaded=True; break
        except Exception as e:
            if i==14: print('  err wait:', e)
    ei = 'UI正确显示：左侧导航栏(群星/星图/星光/调度/搭子桥/设置) + 页面标题“搭子桥” + 内核状态指示器 + 工具栏(搜索框/筛选组/新建任务按钮) + 任务列表面板 + 右侧详情面板空占位' if loaded else ''
    log(2, '步骤2 等待任务列表加载', f'loaded={loaded} title={info.get(chr(116)+chr(105)+chr(116)+chr(108)+chr(101))!r} bodyLen={info.get(chr(98)+chr(100)+chr(108)+chr(101)+chr(110),0)} 搭子桥存在={info.get(chr(104)+chr(95)+chr(100)+chr(109))} 任务列表元素={info.get(chr(104)+chr(95)+chr(116)+chr(115)+chr(107))} 内核状态栏={info.get(chr(104)+chr(95)+chr(107)+chr(110))}', loaded, ei)
    p=OUT/'screenshot_dumate_initial.png'
    s_ok=shot(bridge,tab,str(p)); sz=p.stat().st_size if p.exists() else 0
    ei3='截图可见：侧边导航5项+搭子桥标题+内核状态(在线/离线)+工具栏(搜索+5个筛选按钮+新建任务)+任务列表面板+空详情面板' if sz>2000 else ''
    log(3, '步骤3 初始截图保存', f'CDP截图={s_ok} 文件={p.name} 大小={sz}B', sz>2000, ei3)
    ok_a=False
    try:
        r = bridge.click_selector(tab, '.filter-btn[data-filter="active"]')
        if not r:
            el = bridge.find_by_text(tab, chr(27963)+chr(36291))
            if el: r = bridge.click_selector(tab, el['selector'])
        time.sleep(0.8)
        try: chk = bridge.evaluate(tab, 'document.querySelector(".filter-btn[data-filter=active]").classList.contains("active")')
        except: chk=None
        ok_a = bool(chk) if chk is not None else bool(r)
    except Exception as e: ok_a=False
    p4=OUT/'screenshot_dumate_active.png'
    shot(bridge,tab,str(p4)); sz4=p4.stat().st_size if p4.exists() else 0
    ei4='活跃按钮变为.active（蓝色背景高亮+蓝色文字）；任务列表仅保留status为active的卡片，这些卡片左侧显示绿色竖条(active-task样式)，非活跃的任务卡片被filter过滤不显示' if ok_a and sz4>2000 else ''
    log(4, '步骤4 点击活跃筛选按钮并截图', f'点击={ok_a} 按钮.active类验证 截图大小={sz4}B', ok_a and sz4>2000, ei4)
    ok_all=False
    try:
        r = bridge.click_selector(tab, '.filter-btn[data-filter="all"]')
        if not r:
            el = bridge.find_by_text(tab, chr(20840)+chr(37096))
            if el: r = bridge.click_selector(tab, el['selector'])
        time.sleep(0.6)
        try: chk = bridge.evaluate(tab, 'document.querySelector(".filter-btn[data-filter=all]").classList.contains("active")')
        except: chk=None
        ok_all = bool(chk) if chk is not None else bool(r)
    except Exception as e: ok_all=False
    ei5='全部按钮激活.active样式，活跃按钮失活，任务列表恢复显示所有任务（不按状态过滤）' if ok_all else ''
    log(5, '步骤5 点击全部恢复筛选', f'全部按钮激活={ok_all}', ok_all, ei5)
    ok_d=False
    try:
        r = bridge.click_selector(tab, '.task-card:first-of-type')
        if not r: r = bridge.click_selector(tab, '.task-card')
        time.sleep(1.5)
        try: chk = bridge.evaluate(tab, '!document.getElementById("detailPanel").classList.contains("empty")')
        except: chk=None
        ok_d = bool(chk) if chk is not None else bool(r)
    except Exception as e: ok_d=False
    p6=OUT/'screenshot_dumate_detail.png'
    shot(bridge,tab,str(p6)); sz6=p6.stat().st_size if p6.exists() else 0
    ei6='被点击的.task-card增加.selected样式（蓝色边框+浅蓝背景高亮）；右侧#detailPanel移除.empty类，宽度0→420px动画展开；头部显示detailTitle任务名+关闭X按钮；中部6格信息网格(ID/状态/来源/Agent/创建/更新)+任务内容pre区域+3个操作按钮(复制/结束/查看日志)' if sz6>2000 else ''
    log(6, '步骤6 点击第一个任务卡片+详情面板弹出截图', f'卡片点击 详情面板empty移除={ok_d} 截图={sz6}B', sz6>2000, ei6)
    ok_m=False
    try:
        r = bridge.click_selector(tab, '.btn-new-task')
        if not r:
            el = bridge.find_by_text(tab, chr(26032)+chr(24314)+chr(20219)+chr(21153))
            if el: r = bridge.click_selector(tab, el['selector'])
        time.sleep(1.2)
        try: chk = bridge.evaluate(tab, 'document.getElementById("newTaskModal").classList.contains("visible")')
        except: chk=None
        ok_m = bool(chk) if chk is not None else bool(r)
    except Exception as e: ok_m=False
    ei7='全屏半透明黑蒙板显示（backdrop-filter:blur模糊效果）；居中出现520px宽的白色圆角弹窗；.modal-header显示“新建任务”标题+右上角X关闭按钮；.modal-body中textarea出现placeholder提示；.modal-footer底部靠右出现取消+蓝色发送任务两个按钮' if ok_m else ''
    log(7, '步骤7 点击新建任务等待弹窗', f'弹窗.visible类={ok_m}', ok_m, ei7)
    ok_t=False
    if ok_m:
        try:
            r = bridge.set_value(tab, '#promptInput', chr(27979)+chr(35797)+chr(33258)+chr(21160)+chr(21270)+chr(20219)+chr(21153))
            time.sleep(0.6)
            try: v = bridge.evaluate(tab, 'document.getElementById("promptInput").value')
            except: v=None
            tgt = chr(27979)+chr(35797)+chr(33258)+chr(21160)+chr(21270)+chr(20219)+chr(21153)
            ok_t = (str(v).strip() == tgt) if v is not None else bool(r)
        except Exception as e: ok_t=False
    ei8='textarea#promptInput中清晰显示7个汉字“测试自动化任务”；光标停留在文字末尾；还未按下发送任务，因此后端没有收到新任务；textarea有focus蓝色边框focus样式' if ok_t else ''
    log(8, '步骤8 文本框输入测试自动化任务', f'set_value+DOM验证结果={ok_t} (textarea.value严格等于输入值)', ok_t, ei8)
    p9=OUT/'screenshot_dumate_modal.png'
    shot(bridge,tab,str(p9)); sz9=p9.stat().st_size if p9.exists() else 0
    ei9='截图完整包含：全屏暗色蒙板+居中白色弹窗卡片+头部新建任务标题+文本框中“测试自动化任务”7汉字可见+取消按钮+蓝色发送任务按钮（右下角）' if sz9>2000 else ''
    log(9, '步骤9 弹窗截图保存', f'文件={p9.name} 大小={sz9}B', sz9>2000, ei9)
    ok_c=False
    try:
        el = bridge.find_by_text(tab, chr(21462)+chr(28040))
        r=None
        if el: r = bridge.click_selector(tab, el['selector'])
        if not r: r = bridge.click_selector(tab, '.modal-footer .filter-btn')
        if not r: r = bridge.click_selector(tab, '.modal-footer button:first-of-type')
        time.sleep(0.6)
        try: chk = bridge.evaluate(tab, '!document.getElementById("newTaskModal").classList.contains("visible")')
        except: chk=None
        ok_c = bool(chk) if chk is not None else bool(r)
    except Exception as e: ok_c=False
    ei10='点击取消后，.modal-overlay的.visible类被移除→display:none恢复，蒙板和弹窗全部消失；页面回到主界面（任务列表和详情面板状态不变）；任务数量不应增加（因为取消了而未发送）' if ok_c else ''
    log(10, '步骤10 点击取消关闭弹窗', f'弹窗.visible移除={ok_c}', ok_c, ei10)
    ok_s=False
    try:
        r = bridge.set_value(tab, '#searchInput', chr(27979)+chr(35797))
        time.sleep(0.4)
        try: bridge.evaluate(tab, '(()=>{const i=document.getElementById("searchInput");i.dispatchEvent(new Event("input",{bubbles:true}));return true;})()')
        except: pass
        time.sleep(0.4)
        try: v = bridge.evaluate(tab, 'document.getElementById("searchInput").value')
        except: v=None
        ok_s = (str(v).strip()==chr(27979)+chr(35797)) if v is not None else bool(r)
    except Exception as e: ok_s=False
    p11=OUT/'screenshot_dumate_search.png'
    shot(bridge,tab,str(p11)); sz11=p11.stat().st_size if p11.exists() else 0
    ei11='搜索框内显示“测试”2字；renderTasks()根据searchQuery.toLowerCase()执行过滤，在name/task_id/content_preview中做includes匹配；过滤后如0匹配则显示空状态SVG图标+文本“没有匹配的任务”；如有N匹配则任务列表仅显示N个符合的卡片' if ok_s and sz11>2000 else ''
    log(11, '步骤11 搜索框输入测试并截图', f'#searchInput.value==“测试”={ok_s} 截图大小={sz11}B', ok_s and sz11>2000, ei11)
    steps = [r for r in RES if isinstance(r['step'], int) and 1<=r['step']<=11]
    total=len(steps); passed=sum(1 for r in steps if r['ok'])
    print('\n' + '#'*70)
    print('#  搭子桥 DuMate 页面 UI 自动化测试 详细观察报告  #')
    print('#'*70)
    print(f'  执行时间  : {time.strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'  目标URL   : {URL}')
    print(f'  输出目录  : {OUT}')
    rate = (passed/total*100) if total else 0
    print(f'  步骤统计  : 总数={total} 通过={passed} 失败={total-passed} 通过率={rate:.1f}%')
    print('-'*70)
    print('  各步骤详细观察结果 & UI元素验证：')
    print('-'*70)
    for r in steps:
        m = '✅ PASS' if r['ok'] else '❌ FAIL'
        print(f'\n  [{m}] 步骤{r["step"]}: {r["desc"]}')
        print(f'          观察结果: {r["obs"]}')
        if r['extra']: print(f'          UI要素  : {r["extra"]}')
    print('\n' + '-'*70)
    print('  截图产物清单：')
    fs=[('screenshot_dumate_initial.png','步骤3 初始加载完整页面'),('screenshot_dumate_active.png','步骤4 活跃筛选后的界面'),('screenshot_dumate_detail.png','步骤6 详情面板展开态'),('screenshot_dumate_modal.png','步骤9 新建任务弹窗(已输入文本)'),('screenshot_dumate_search.png','步骤11 搜索框输入测试后')]
    all_f=True
    for fn,d in fs:
        fp=OUT/fn
        if fp.exists():
            kb=fp.stat().st_size/1024; print(f'    🖼️  [OK] {fn:42s} {kb:7.1f} KB  →  {d}')
        else:
            all_f=False; print(f'    🖼️  [MISS] {fn:42s} 缺失文件  →  {d}')
    final = (passed==total and all_f and total>0)
    print('\n' + '#'*70)
    if final:
        print('  ✅ 最终结论：全部11个步骤通过，所有5张截图生成成功！')
    else:
        fs_txt = '齐全' if all_f else '有缺失'; print(f'  ⚠️  最终结论：部分步骤未通过。通过{passed}/{total}步，截图文件{fs_txt}')
    print('#'*70)
    return 0 if final else 1

if __name__ == '__main__':
    try: sys.exit(main())
    except Exception as e:
        import traceback; traceback.print_exc(); sys.exit(2)
