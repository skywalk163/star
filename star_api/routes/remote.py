"""
远程控制路由（Remote Routes）

提供窗口截图、热点点击、指令发送等远程控制接口
"""

import os
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from star_api import state
from star_api.auth import require_read, require_write, require_control, get_current_user
from star_core.star_auditor import audit

router = APIRouter()


def _get_screenshot_manager():
    if not hasattr(state, 'screenshot_manager') or state.screenshot_manager is None:
        from star_core.remote_screenshot import RemoteScreenshotManager
        state.screenshot_manager = RemoteScreenshotManager()
    return state.screenshot_manager


def _get_window_controller():
    if not hasattr(state, 'window_controller') or state.window_controller is None:
        from star_core.window_controller import WindowController
        state.window_controller = WindowController()
    return state.window_controller


@router.get("/screenshot/{hwnd}", dependencies=[Depends(require_read)])
async def get_screenshot(hwnd: int, force: bool = False):
    mgr = _get_screenshot_manager()
    img_path = mgr.capture(hwnd, force=force)

    if not img_path or not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="截图不可用")

    status = mgr.get_status(hwnd)
    return FileResponse(
        img_path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-cache",
            "X-Interval": str(status['current_interval']),
            "X-Last-Update": str(status['last_screenshot_time']),
        }
    )


@router.get("/screenshot/{hwnd}/status", dependencies=[Depends(require_read)])
async def get_screenshot_status(hwnd: int):
    mgr = _get_screenshot_manager()
    return mgr.get_status(hwnd)


@router.post("/screenshot/{hwnd}/refresh", dependencies=[Depends(require_control)])
async def refresh_screenshot(hwnd: int):
    mgr = _get_screenshot_manager()
    mgr.capture(hwnd, force=True)
    audit('refresh_screenshot', hwnd=hwnd)
    return mgr.get_status(hwnd)


@router.get("/hotspots/{star_type}", dependencies=[Depends(require_read)])
async def get_hotspots(star_type: str):
    ctrl = _get_window_controller()
    hotspots = ctrl.get_hotspots(star_type)
    return {
        'star_type': star_type,
        'hotspots': {
            name: {
                'name': hs.name,
                'label': hs.label,
                'position': hs.position,
                'width_ratio': hs.width_ratio,
                'height_ratio': hs.height_ratio,
                'offset_x': hs.offset_x,
                'offset_y': hs.offset_y,
            }
            for name, hs in hotspots.items()
        }
    }


@router.post("/click/{hwnd}", dependencies=[Depends(require_control)])
async def click_window(hwnd: int, x_ratio: float = 0.5, y_ratio: float = 0.5):
    ctrl = _get_window_controller()

    if not ctrl.activate(hwnd):
        raise HTTPException(status_code=500, detail="无法激活窗口")

    rect = ctrl.get_window_rect(hwnd)
    if not rect:
        raise HTTPException(status_code=500, detail="无法获取窗口位置")

    left, top, right, bottom = rect
    x = left + int((right - left) * x_ratio)
    y = top + int((bottom - top) * y_ratio)

    if not ctrl.click_at(x, y):
        raise HTTPException(status_code=500, detail="点击失败")

    audit('click', hwnd=hwnd, params={'x_ratio': x_ratio, 'y_ratio': y_ratio, 'x': x, 'y': y})
    return {"success": True, "x": x, "y": y}


@router.post("/send/{hwnd}", dependencies=[Depends(require_control)])
async def send_to_window(hwnd: int, text: str, hotspot: str = "input_box", press_enter: bool = True):
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")

    star = state.orbit_engine.star_seeker.get_star(hwnd)
    star_type = star.star_type if star else "default"

    ctrl = _get_window_controller()
    hotspots = ctrl.get_hotspots(star_type)

    if hotspot not in hotspots:
        raise HTTPException(status_code=400, detail="未知热点: %s" % hotspot)

    hs = hotspots[hotspot]

    success = ctrl.send_to_hotspot(hwnd, hs, text)

    if success and press_enter:
        ctrl.press_enter()

    if not success:
        raise HTTPException(status_code=500, detail="发送失败")

    audit('send_text', hwnd=hwnd, params={'hotspot': hotspot, 'text_length': len(text), 'press_enter': press_enter})
    return {"success": True, "hotspot": hotspot, "text_length": len(text)}


# ==================== 键盘操作 ====================

@router.post("/keyboard/{hwnd}/hotkey", dependencies=[Depends(require_control)])
async def keyboard_hotkey(hwnd: int, keys: str):
    """
    发送组合键
    
    Args:
        hwnd: 窗口句柄
        keys: 逗号分隔的键名，如 "ctrl,s" 表示 Ctrl+S
    """
    ctrl = _get_window_controller()
    key_list = [k.strip() for k in keys.split(',')]
    result = ctrl.keyboard_operation(hwnd, 'hotkey', {'keys': key_list})
    if not result.get('success'):
        raise HTTPException(status_code=500, detail="按键失败")
    audit('hotkey', hwnd=hwnd, params={'keys': keys})
    return result


@router.post("/keyboard/{hwnd}/press", dependencies=[Depends(require_control)])
async def keyboard_press(hwnd: int, key: str):
    """
    按下单个键
    
    Args:
        hwnd: 窗口句柄
        key: 键名，如 "enter", "tab", "escape"
    """
    ctrl = _get_window_controller()
    result = ctrl.keyboard_operation(hwnd, 'press_key', {'key': key})
    if not result.get('success'):
        raise HTTPException(status_code=500, detail="按键失败: " + key)
    audit('press_key', hwnd=hwnd, params={'key': key})
    return result


@router.post("/keyboard/{hwnd}/send", dependencies=[Depends(require_control)])
async def keyboard_send(hwnd: int, text: str):
    """
    发送文本（键盘输入）
    
    Args:
        hwnd: 窗口句柄
        text: 要发送的文本
    """
    ctrl = _get_window_controller()
    result = ctrl.keyboard_operation(hwnd, 'send_text', {'text': text})
    if not result.get('success'):
        raise HTTPException(status_code=500, detail="文本输入失败")
    audit('keyboard_send', hwnd=hwnd, params={'text_length': len(text)})
    return result


@router.post("/keyboard/{hwnd}/sequence", dependencies=[Depends(require_control)])
async def keyboard_sequence(hwnd: int, sequence: list):
    """
    执行复合操作序列

    Args:
        hwnd: 窗口句柄
        sequence: 操作序列，如 [["ctrl","a"], "delete", "hello", ["ctrl","v"]]
    """
    ctrl = _get_window_controller()
    result = ctrl.keyboard_operation(hwnd, 'sequence', {'sequence': sequence})
    if not result.get('success'):
        raise HTTPException(status_code=500, detail="序列执行失败")
    audit('sequence', hwnd=hwnd, params={'sequence_length': len(sequence)})
    return result


# ==================== 标签页切换 ====================

@router.post("/tab/{hwnd}/switch", dependencies=[Depends(require_control)])
async def switch_tab(hwnd: int, index: int):
    """
    切换到指定标签页

    Args:
        hwnd: 窗口句柄
        index: 标签页索引（1-6）
    """
    ctrl = _get_window_controller()
    success = ctrl.switch_to_tab(hwnd, index)
    if not success:
        raise HTTPException(status_code=500, detail="标签页切换失败")
    audit('switch_tab', hwnd=hwnd, params={'index': index})
    return {'success': True, 'operation': 'switch_tab', 'index': index}


@router.post("/tab/{hwnd}/next", dependencies=[Depends(require_control)])
async def next_tab(hwnd: int):
    """切换到下一个标签页"""
    ctrl = _get_window_controller()
    success = ctrl.switch_to_next_tab(hwnd)
    if not success:
        raise HTTPException(status_code=500, detail="标签页切换失败")
    audit('next_tab', hwnd=hwnd)
    return {'success': True, 'operation': 'next_tab'}


@router.post("/tab/{hwnd}/prev", dependencies=[Depends(require_control)])
async def prev_tab(hwnd: int):
    """切换到上一个标签页"""
    ctrl = _get_window_controller()
    success = ctrl.switch_to_prev_tab(hwnd)
    if not success:
        raise HTTPException(status_code=500, detail="标签页切换失败")
    audit('prev_tab', hwnd=hwnd)
    return {'success': True, 'operation': 'prev_tab'}


@router.get("/tab/{hwnd}/region", dependencies=[Depends(require_read)])
async def get_tab_region(hwnd: int):
    """获取标签页区域配置"""
    ctrl = _get_window_controller()
    return ctrl.get_tab_region()


# ==================== 热点校准 ====================

@router.post("/calibrate/{hwnd}", dependencies=[Depends(require_control)])
async def calibrate_hotspots(hwnd: int, star_type: str = "trae"):
    """
    通过 OCR 自动识别输入框位置并校准热点

    Args:
        hwnd: 窗口句柄
        star_type: 星体类型（trae/default/...）
    """
    # 1. 获取截图
    mgr = _get_screenshot_manager()
    img_path = mgr.capture(hwnd, force=True)
    if not img_path or not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="截图不可用")

    # 2. 执行校准
    ctrl = _get_window_controller()
    result = ctrl.calibrate_hotspots(img_path, star_type)

    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error', '校准失败'))

    audit('calibrate', hwnd=hwnd, params={'star_type': star_type, 'success': True})
    return result


@router.post("/calibrate/{hwnd}/apply", dependencies=[Depends(require_control)])
async def apply_calibration(hwnd: int, star_type: str = "trae"):
    """
    执行校准并应用结果到热点配置

    返回校准后的热点配置，可直接用于前端渲染
    """
    # 1. 获取截图
    mgr = _get_screenshot_manager()
    img_path = mgr.capture(hwnd, force=True)
    if not img_path or not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="截图不可用")

    # 2. 执行校准
    ctrl = _get_window_controller()
    result = ctrl.calibrate_hotspots(img_path, star_type)

    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error', '校准失败'))

    # 3. 提取校准后的热点，转换为前端可用的格式
    calibrated = {}

    if 'input_box' in result:
        ib = result['input_box']
        calibrated['input_box'] = {
            'name': ib['name'],
            'label': ib['label'],
            'x_ratio': round(ib['x_ratio'], 4),
            'y_ratio': round(ib['y_ratio'], 4),
            'width_ratio': round(ib['width_ratio'], 4),
            'height_ratio': round(ib['height_ratio'], 4),
            'offset_x': -10,
            'offset_y': -20,
            'position': 'calibrated',
            'confidence': round(ib['confidence'], 3),
            'matched_text': ib['matched_text'],
        }

    if 'task_list' in result and result['task_list']:
        tl = result['task_list']
        calibrated['task_list'] = {
            'name': tl['name'],
            'label': tl['label'],
            'x_ratio': round(tl['x_ratio'], 4),
            'y_ratio': round(tl['y_ratio'], 4),
            'width_ratio': round(tl['width_ratio'], 4),
            'height_ratio': round(tl['height_ratio'], 4),
            'offset_x': 10,
            'offset_y': 80,
            'position': 'calibrated',
            'confidence': round(tl['confidence'], 3),
            'matched_text': tl['matched_text'],
        }

    audit('calibrate_apply', hwnd=hwnd, params={'star_type': star_type})

    return {
        'success': True,
        'star_type': star_type,
        'hwnd': hwnd,
        'calibrated_hotspots': calibrated,
        'all_candidates': result.get('all_candidates', []),
        'image_width': result.get('image_width'),
        'image_height': result.get('image_height'),
    }


# ==================== 认证 ====================

@router.get("/auth/status")
async def auth_status(current_user: dict = Depends(get_current_user)):
    """获取认证状态和当前用户信息"""
    from star_api.auth import is_auth_enabled
    return {
        'auth_enabled': is_auth_enabled(),
        'authenticated': current_user.get('authenticated', False),
        'role': current_user.get('role', 'admin'),
        'name': current_user.get('name', 'default'),
        'permissions': ['read', 'write', 'control', 'admin'] if current_user.get('role') == 'admin' else ['read'],
    }


# ==================== 审计日志 ====================

from star_core.star_auditor import get_audit_logger

@router.get("/audit/logs", dependencies=[Depends(require_read)])
async def get_audit_logs(
    limit: int = 50,
    offset: int = 0,
    operation: str = None,
    hwnd: int = None,
    result_filter: str = None,
):
    """查询审计日志"""
    logger = get_audit_logger()
    return {
        'success': True,
        'logs': logger.query(
            limit=limit,
            offset=offset,
            operation=operation,
            hwnd=hwnd,
            result=result_filter,
        ),
    }


@router.get("/audit/stats", dependencies=[Depends(require_read)])
async def get_audit_stats():
    """获取审计统计"""
    logger = get_audit_logger()
    return logger.stats()


# ==================== 星群状态总览 ====================

@router.get("/stars/status", dependencies=[Depends(require_read)])
async def get_stars_status():
    """
    获取所有 AI Agent 的状态总览

    Returns:
        星体列表，每个包含：类型、进程信息、窗口数、状态、工作任务等
    """
    from datetime import datetime
    from star_core.star_emissary import StarAdapter, PRESET_ADAPTERS

    if state.orbit_engine is None or state.orbit_engine.star_seeker is None:
        raise HTTPException(status_code=503, detail="星核未初始化")

    seeker = state.orbit_engine.star_seeker
    stars = seeker.scan_skies(force=True)

    # 获取 OCR 分析器用于状态检测
    try:
        from star_core.ocr_gazer import OCRGazer
        ocr = OCRGazer()
    except Exception:
        ocr = None

    star_statuses = []

    for star in stars:
        star_info = {
            'star_type': star.star_type,
            'pid': star.pid,
            'title': star.title,
            'description': seeker.STAR_SIGNATURES.get(star.star_type, {}).get('description', ''),
            'window_count': len(star.windows),
            'windows': [],
            'overall_status': 'unknown',
            'active_count': 0,
            'idle_count': 0,
            'working_count': 0,
            'timestamp': datetime.now().isoformat()
        }

        # 分析每个窗口的状态
        for window in star.windows:
            window_info = {
                'hwnd': window.hwnd,
                'title': window.title,
                'is_visible': window.is_visible,
                'status': 'unknown',
                'is_active': False,
                'current_task': None,
                'progress': None,
                'last_keywords': []
            }

            # 使用 OCR 检测状态
            if ocr:
                try:
                    status_data = ocr.get_current_status(star)
                    window_info['status'] = status_data.get('status', 'unknown')
                    window_info['is_active'] = status_data.get('is_active', False)
                    window_info['current_task'] = status_data.get('current_task')
                    window_info['progress'] = status_data.get('progress')
                except Exception:
                    pass

            # 更新窗口计数
            if window_info['status'] in ['working', 'running', 'processing', 'thinking', 'generating']:
                star_info['working_count'] += 1
                window_info['status_category'] = 'working'
            elif window_info['status'] in ['idle', 'ready', 'waiting']:
                star_info['idle_count'] += 1
                window_info['status_category'] = 'idle'
            elif window_info['status'] in ['completed', 'done', 'success']:
                star_info['active_count'] += 1
                window_info['status_category'] = 'completed'
            else:
                star_info['idle_count'] += 1
                window_info['status_category'] = 'unknown'

            star_info['windows'].append(window_info)

        # 确定星体总体状态
        if star_info['working_count'] > 0:
            star_info['overall_status'] = 'working'
        elif star_info['active_count'] > 0 and star_info['idle_count'] == 0:
            star_info['overall_status'] = 'completed'
        elif star_info['idle_count'] > 0:
            star_info['overall_status'] = 'idle'
        else:
            star_info['overall_status'] = 'unknown'

        star_statuses.append(star_info)

    return {
        'success': True,
        'count': len(star_statuses),
        'stars': star_statuses,
        'summary': {
            'total_stars': len(star_statuses),
            'total_windows': sum(s['window_count'] for s in star_statuses),
            'working': sum(1 for s in star_statuses if s['overall_status'] == 'working'),
            'idle': sum(1 for s in star_statuses if s['overall_status'] == 'idle'),
            'completed': sum(1 for s in star_statuses if s['overall_status'] == 'completed'),
            'unknown': sum(1 for s in star_statuses if s['overall_status'] == 'unknown'),
        },
        'timestamp': datetime.now().isoformat()
    }


@router.get("/stars/brief", dependencies=[Depends(require_read)])
async def get_stars_brief():
    """
    获取星体简要信息（轻量级，用于导航列表）
    """
    if state.orbit_engine is None or state.orbit_engine.star_seeker is None:
        raise HTTPException(status_code=503, detail="星核未初始化")

    seeker = state.orbit_engine.star_seeker
    stars = seeker.scan_skies(force=True)

    return {
        'success': True,
        'stars': [
            {
                'star_type': s.star_type,
                'pid': s.pid,
                'title': s.title,
                'window_count': len(s.windows),
                'description': seeker.STAR_SIGNATURES.get(s.star_type, {}).get('description', ''),
            }
            for s in stars
        ]
    }


# ==================== 批量群发指令 ====================

@router.post("/broadcast/send", dependencies=[Depends(require_control)])
async def broadcast_send(
    hwids: list[int],
    text: str,
    parallel: bool = True,
):
    """
    批量发送指令到多个窗口
    
    Args:
        hwids: 窗口句柄列表
        text: 要发送的指令文本
        parallel: 是否并行发送（默认 True）
    """
    from star_core.star_emissary import StarEmissary
    from star_core.star_seeker import StarSeeker
    import asyncio

    if state.orbit_engine is None or state.orbit_engine.star_seeker is None:
        raise HTTPException(status_code=503, detail="星核未初始化")

    seeker = state.orbit_engine.star_seeker
    results = []

    async def send_to_hwnd(hwnd: int):
        try:
            star = seeker.get_star(hwnd)
            if not star:
                return {"hwnd": hwnd, "success": False, "error": "Star not found"}

            # 获取适配器
            from star_core.star_emissary import StarAdapter
            adapter = StarAdapter.from_star_type(star.star_type)
            emissary = StarEmissary(star=star, adapter_name=adapter.config.name)

            # 发送指令
            success = emissary.send_prompt(text)
            audit('broadcast_send', hwnd=hwnd, params={'text_length': len(text)})

            return {
                "hwnd": hwnd,
                "success": success,
                "star_type": star.star_type,
                "title": star.title
            }
        except Exception as e:
            return {"hwnd": hwnd, "success": False, "error": str(e)}

    # 并行或串行执行
    if parallel:
        tasks = [send_to_hwnd(hwnd) for hwnd in hwids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # 处理异常
        results = [
            r if not isinstance(r, Exception) else {"error": str(r)}
            for r in results
        ]
    else:
        for hwnd in hwids:
            results.append(await send_to_hwnd(hwnd))

    return {
        "success": True,
        "total": len(hwids),
        "sent": sum(1 for r in results if r.get("success")),
        "failed": sum(1 for r in results if not r.get("success")),
        "results": results
    }


@router.get("/broadcast/status/{hwnd}", dependencies=[Depends(require_read)])
async def get_broadcast_status(hwnd: int):
    """
    获取窗口当前状态（用于轮询批量指令结果）
    """
    try:
        from star_core.ocr_gazer import OCRGazer
        from star_core.star_seeker import StarSeeker

        if state.orbit_engine is None:
            raise HTTPException(status_code=503, detail="星核未初始化")

        seeker = state.orbit_engine.star_seeker
        star = seeker.get_star(hwnd)

        if not star:
            raise HTTPException(status_code=404, detail="窗口未找到")

        ocr = OCRGazer()
        status = ocr.get_current_status(star)

        return {
            "hwnd": hwnd,
            "status": status.get("status", "unknown"),
            "is_active": status.get("is_active", False),
            "current_task": status.get("current_task"),
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"hwnd": hwnd, "status": "error", "error": str(e)}


# ==================== 配置管理 ====================

@router.get("/config/agents")
async def list_agent_configs():
    """获取所有 Agent 配置"""
    from star_core.config_service import get_config_service
    config_svc = get_config_service()
    config_svc.reload_if_changed()
    agents = config_svc.get_all_agents()
    return {
        "total": len(agents),
        "agents": [
            {
                "id": aid,
                "name": a.get("name"),
                "vendor": a.get("vendor"),
                "category": a.get("category"),
                "description": a.get("description"),
            }
            for aid, a in agents.items()
        ]
    }


@router.get("/config/agents/{agent_id}")
async def get_agent_config(agent_id: str):
    """获取指定 Agent 的完整配置"""
    from star_core.config_service import get_config_service
    config_svc = get_config_service()
    config_svc.reload_if_changed()
    agent = config_svc.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"agent": agent}


@router.post("/config/reload")
async def reload_config():
    """强制重新加载配置"""
    from star_core.config_service import get_config_service
    config_svc = get_config_service()
    success = config_svc.load()
    return {"success": success, "agent_count": len(config_svc.get_all_agents())}


# ==================== 任务历史 ====================

@router.get("/tasks")
async def list_tasks(status: str = None, limit: int = 100, offset: int = 0):
    """获取任务历史列表"""
    from star_core.database import get_db_service
    db = get_db_service()
    tasks, total = db.list_tasks(status=status, limit=limit, offset=offset)
    return {"tasks": tasks, "total": total}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """获取单个任务详情"""
    from star_core.database import get_db_service
    db = get_db_service()
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": task}


@router.post("/tasks")
async def upsert_task(task_data: dict):
    """创建或更新任务"""
    from star_core.database import get_db_service
    db = get_db_service()
    task_id = db.upsert_task(task_data)
    audit('task_upsert', params={'task_id': task_id, 'title': task_data.get('title')})
    return {"success": True, "task_id": task_id}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    from star_core.database import get_db_service
    db = get_db_service()
    success = db.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    audit('task_delete', params={'task_id': task_id})
    return {"success": True}


# ==================== 系统健康检查 ====================

@router.get("/health")
async def health_check():
    """系统健康检查"""
    from star_core.database import get_db_service
    db_ok = False
    try:
        db_ok = get_db_service().health_check()
    except Exception:
        pass
    
    return {
        "status": "ok",
        "database": "healthy" if db_ok else "degraded",
        "timestamp": datetime.now().isoformat()
    }
