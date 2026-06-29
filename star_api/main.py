"""
星光接口主入口（Star API Main）- FastAPI 应用

提供 RESTful API 和 WebSocket 接口
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from typing import Optional

import yaml

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from star_api import state

from star_core import (
    StarSeeker, StarAssigner, StarGazer, OrbitEngine,
    Nova, StarStatus, StarPriority, Constellation, ConstellationStatus,
    ConstellationStorage, ResultComparator
)
from star_core.plugin_system import PluginManager
from star_core.analytics import HistoryStore, StarAnalytics


# ==================== 配置加载 ====================

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config.yaml")


def load_config() -> dict:
    """加载 YAML 配置文件"""
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def setup_logging(config: dict):
    """配置日志系统（轮转 + 归档）"""
    log_cfg = config.get("logging", {})
    log_dir = os.path.join(_PROJECT_ROOT, config.get("directories", {}).get("logs", "logs"))
    os.makedirs(log_dir, exist_ok=True)

    # 移除默认 handler
    logger.remove()

    # 控制台输出
    logger.add(
        sys.stderr,
        level=config.get("server", {}).get("log_level", "INFO"),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    # 文件输出（带轮转）
    logger.add(
        os.path.join(log_dir, "star_{time:YYYY-MM-DD}.log"),
        level="DEBUG",
        rotation=log_cfg.get("rotation", "100 MB"),
        retention=log_cfg.get("retention", "30 days"),
        compression=log_cfg.get("compression", "zip"),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        encoding="utf-8",
    )

    # 错误日志单独输出
    logger.add(
        os.path.join(log_dir, "star_error_{time:YYYY-MM-DD}.log"),
        level="ERROR",
        rotation=log_cfg.get("rotation", "100 MB"),
        retention=log_cfg.get("retention", "30 days"),
        compression=log_cfg.get("compression", "zip"),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        encoding="utf-8",
    )

    logger.info(f"📝 日志目录: {log_dir}")


# ==================== 应用初始化 ====================

_config = load_config()
setup_logging(_config)

# 保存到全局 state
state.config = _config
state.project_root = _PROJECT_ROOT

_server_cfg = _config.get("server", {})
_OCR_ENABLED = _config.get("ocr", {}).get("enabled", False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    
    # 启动时初始化
    logger.info("⭐ 星光接口启动 - Initializing Star API")
    
    # 初始化插件管理器
    state.plugin_manager = PluginManager(plugin_dir="star_plugins")
    logger.info(f"🔌 插件管理器就绪 - 发现 {len(state.plugin_manager.discover_plugins())} 个插件")
    
    # 初始化引擎（带插件管理器）
    state.orbit_engine = OrbitEngine(
        star_seeker=StarSeeker(plugin_manager=state.plugin_manager),
        star_assigner=StarAssigner(),
        star_gazer=StarGazer()
    )
    
    # 初始化历史存储和统计
    state.history_store = HistoryStore()
    state.analytics = StarAnalytics(state.history_store)
    logger.info("📊 统计系统就绪 - Analytics Ready")
    
    # 设置回调
    state.orbit_engine.set_callbacks(
        on_status_change=_broadcast_nova_status,
        on_starlight=_broadcast_starlight
    )
    
    # 启动队列处理任务
    asyncio.create_task(state.orbit_engine.process_queue())
    
    # 启动星体扫描
    asyncio.create_task(_scan_stars_periodically())
    
    logger.info("✨ 星核已就绪 - Star Core Ready")
    
    yield
    
    # 关闭时清理
    logger.info("🌑 星光接口关闭 - Shutting Down")


app = FastAPI(
    title=_config.get("server", {}).get("name", "群星 Star API"),
    description="AI Agent 调度中心 - 星光接口",
    version=_config.get("server", {}).get("version", "0.1.0"),
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== WebSocket 广播 ====================

async def _broadcast_nova_status(nova: Nova):
    """广播新星状态变化"""
    message = {
        "type": "nova_status_change",
        "data": {
            "id": nova.id,
            "status": nova.status.value,
            "title": nova.title,
            "updated_at": nova.updated_at.isoformat()
        }
    }
    await _broadcast(message)


async def _broadcast_starlight(nova: Nova, content: str):
    """广播星光内容"""
    message = {
        "type": "starlight_received",
        "data": {
            "nova_id": nova.id,
            "content": content,
            "timestamp": nova.updated_at.isoformat()
        }
    }
    await _broadcast(message)


async def _broadcast_star_change():
    """广播星体变化"""
    if state.orbit_engine is None:
        return
    
    stars = state.orbit_engine.star_seeker.scan_skies(force=True)
    message = {
        "type": "stars_updated",
        "data": [
            {
                "pid": s.pid,
                "star_type": s.star_type,
                "title": s.title,
                "is_shining": s.is_shining
            }
            for s in stars
        ]
    }
    await _broadcast(message)


async def _broadcast_constellation_status(constellation: Constellation):
    """广播星座状态变化"""
    message = {
        "type": "constellation_status_change",
        "data": {
            "id": constellation.id,
            "name": constellation.name,
            "status": constellation.status.value,
            "completed_count": len(constellation.completed_novas),
            "shining_count": len(constellation.get_shining_novas()),
            "total_novas": len(constellation.novas),
            "updated_at": constellation.updated_at.isoformat()
        }
    }
    await _broadcast(message)


async def _broadcast_constellation_complete(constellation: Constellation):
    """广播星座完成"""
    message = {
        "type": "constellation_complete",
        "data": {
            "id": constellation.id,
            "name": constellation.name,
            "status": constellation.status.value,
            "completed_novas": [
                {
                    "id": n.id,
                    "title": n.title,
                    "assigned_star": n.assigned_star
                }
                for n in constellation.novas
            ],
            "updated_at": constellation.updated_at.isoformat()
        }
    }
    await _broadcast(message)


async def _broadcast(message: dict):
    """广播消息到所有 WebSocket 连接"""
    if not state.websocket_connections:
        return
    
    dead_connections = []
    for ws in state.websocket_connections:
        try:
            await ws.send_json(message)
        except Exception:
            dead_connections.append(ws)
    
    # 清理断开的连接
    for ws in dead_connections:
        state.websocket_connections.remove(ws)


async def _scan_stars_periodically():
    """定期扫描星体"""
    while True:
        await asyncio.sleep(5)
        try:
            if state.orbit_engine:
                state.orbit_engine.star_seeker.scan_skies(force=True)
                await _broadcast_star_change()
        except Exception:
            pass


# ==================== WebSocket 端点 ====================

@app.websocket("/ws/starlight")
async def websocket_starlight(websocket: WebSocket):
    """星光流 WebSocket 端点"""
    await websocket.accept()
    state.websocket_connections.append(websocket)
    
    try:
        if state.orbit_engine:
            await websocket.send_json({
                "type": "connected",
                "data": {
                    "stats": state.orbit_engine.get_stats()
                }
            })
        
        while True:
            data = await websocket.receive_text()
            
            if data == "ping":
                await websocket.send_text("pong")
                
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in state.websocket_connections:
            state.websocket_connections.remove(websocket)


# ==================== OCR 实时流 ====================

_ocr_stream_clients: dict[str, list[WebSocket]] = {}
_ocr_stream_tasks: dict[str, asyncio.Task] = {}


async def _start_ocr_stream(star_id: str, interval: float = 3.0):
    """启动 OCR 实时流任务"""
    if star_id in _ocr_stream_tasks:
        return
    
    async def _stream_loop():
        from star_core import StarEmissary
        
        ocr_gazer = None
        target_star = None
        
        while star_id in _ocr_stream_clients and _ocr_stream_clients[star_id]:
            try:
                if state.orbit_engine is None:
                    await asyncio.sleep(interval)
                    continue
                
                if target_star is None:
                    stars = state.orbit_engine.star_seeker.scan_skies()
                    for s in stars:
                        if s.star_id == star_id or str(s.pid) == star_id:
                            try:
                                if int(star_id) == s.pid:
                                    target_star = s
                                    break
                            except ValueError:
                                if s.star_id == star_id:
                                    target_star = s
                                    break
                
                if target_star is None:
                    await asyncio.sleep(interval)
                    continue
                
                if ocr_gazer is None:
                    from star_core import OCRGazer
                    ocr_gazer = OCRGazer(
                        lang="ch",
                        det_limit_side_len=640,
                        use_incremental=True,
                        change_threshold=0.01,
                    )
                
                # 执行 OCR
                try:
                    result = ocr_gazer.gaze_detail(target_star, region="center_content")
                    
                    # 推送到所有订阅者
                    message = {
                        "type": "ocr_update",
                        "star_id": star_id,
                        "data": {
                            "text": result.text,
                            "line_count": len(result.lines),
                            "region": result.region,
                            "capture_time": result.capture_time,
                            "recognize_time": result.recognize_time,
                            "timestamp": result.timestamp.isoformat(),
                            "lines": [
                                {
                                    "text": l.text,
                                    "confidence": round(l.confidence, 3),
                                    "y": round(l.y_center, 1),
                                }
                                for l in result.lines[:50]
                            ]
                        }
                    }
                    
                    dead_clients = []
                    for client in _ocr_stream_clients.get(star_id, []):
                        try:
                            await client.send_json(message)
                        except Exception:
                            dead_clients.append(client)
                    
                    for dead in dead_clients:
                        if star_id in _ocr_stream_clients:
                            if dead in _ocr_stream_clients[star_id]:
                                _ocr_stream_clients[star_id].remove(dead)
                    
                except Exception:
                    pass
                
                await asyncio.sleep(interval)
                
            except Exception:
                await asyncio.sleep(interval)
    
    task = asyncio.create_task(_stream_loop())
    _ocr_stream_tasks[star_id] = task


async def _stop_ocr_stream_if_empty(star_id: str):
    """如果没有订阅者则停止 OCR 流"""
    if star_id in _ocr_stream_clients and not _ocr_stream_clients[star_id]:
        if star_id in _ocr_stream_tasks:
            _ocr_stream_tasks[star_id].cancel()
            del _ocr_stream_tasks[star_id]
        del _ocr_stream_clients[star_id]


@app.websocket("/ws/ocr/{star_id}")
async def websocket_ocr_stream(websocket: WebSocket, star_id: str, interval: float = 3.0):
    """
    OCR 实时流 WebSocket 端点
    
    Args:
        star_id: 星体 ID 或 PID
        interval: 识别间隔（秒），默认3秒
    """
    await websocket.accept()
    
    if star_id not in _ocr_stream_clients:
        _ocr_stream_clients[star_id] = []
    
    _ocr_stream_clients[star_id].append(websocket)
    
    try:
        await websocket.send_json({
            "type": "connected",
            "star_id": star_id,
            "interval": interval,
        })
        
        # 启动流
        await _start_ocr_stream(star_id, interval)
        
        # 保持连接
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
                
    except WebSocketDisconnect:
        pass
    finally:
        if star_id in _ocr_stream_clients:
            if websocket in _ocr_stream_clients[star_id]:
                _ocr_stream_clients[star_id].remove(websocket)
            await _stop_ocr_stream_if_empty(star_id)


# ==================== 导入路由 ====================

from star_api.routes.stars import router as stars_router
from star_api.routes.novas import router as novas_router
from star_api.routes.constellations import router as constellations_router
from star_api.routes.history import router as history_router
from star_api.routes.plugins import router as plugins_router
from star_api.routes.emissary import router as emissary_router
from star_api.routes.config import router as config_router
from star_api.routes.work import router as work_router
from star_api.routes.remote import router as remote_router

app.include_router(stars_router, prefix="/api/stars", tags=["星体"])
app.include_router(novas_router, prefix="/api/novas", tags=["新星"])
app.include_router(constellations_router, prefix="/api/constellations", tags=["星座"])
app.include_router(history_router, prefix="/api/history", tags=["历史与统计"])
app.include_router(plugins_router, prefix="/api/plugins", tags=["插件管理"])
app.include_router(emissary_router, prefix="/api/emissary", tags=["星使交互"])
app.include_router(config_router)
app.include_router(work_router)
app.include_router(remote_router, prefix="/api/remote", tags=["远程控制"])


# ==================== 静态文件 & 控制面板 ====================

# star-ui 设计面板（主面板 - 三页面设计）
_ui_dir = os.path.join(_PROJECT_ROOT, "star-ui")
if os.path.exists(_ui_dir):
    app.mount("/ui", StaticFiles(directory=_ui_dir), name="static_ui")

# star-web SPA 前端（备用）
_web_spa_dir = os.path.join(_PROJECT_ROOT, "star-web")
if os.path.exists(_web_spa_dir):
    app.mount("/spa", StaticFiles(directory=_web_spa_dir), name="static_spa")

# 旧版控制面板（备用）
_web_legacy_dir = os.path.join(_PROJECT_ROOT, "web")
if os.path.exists(_web_legacy_dir):
    app.mount("/legacy", StaticFiles(directory=_web_legacy_dir), name="static_legacy")


@app.get("/")
async def root():
    """星光接口根路径 - 返回 star-ui 星图控制面板"""
    index_path = os.path.join(_PROJECT_ROOT, "star-ui", "pages", "starmap.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "name": "群星 Star API",
        "version": "0.1.0",
        "status": "shining"
    }


@app.get("/remote")
async def remote_control():
    """远程控制页面"""
    remote_path = os.path.join(_PROJECT_ROOT, "star-ui", "pages", "remote.html")
    if os.path.exists(remote_path):
        return FileResponse(remote_path)
    return {"error": "Remote control page not found"}


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}


@app.get("/api/stats")
async def get_stats():
    """获取调度统计"""
    if state.orbit_engine is None:
        return {"error": "Engine not initialized"}
    return state.orbit_engine.get_stats()
