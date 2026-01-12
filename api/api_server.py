"""
API 服务器
提供REST API接口，通过SSE推送进度和事件
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, Optional, AsyncGenerator
import threading

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sse_starlette import EventSourceResponse

import sys
import os
from pathlib import Path

# 添加父目录到路径
_project_root = Path(__file__).parent.parent
sys.path.insert(0, str(_project_root))

# 添加VideoTranslate_Windows目录到路径
_windows_path = _project_root.parent / 'VideoTranslate_Windows'
if _windows_path.exists() and str(_windows_path) not in sys.path:
    sys.path.insert(0, str(_windows_path))

from .api_config import (
    API_HOST, API_PORT, API_BASE_URL, CORS_ORIGINS, 
    LOG_LEVEL, MAX_CONCURRENT_TASKS
)
from .api_models import (
    StartTranslationRequest, ConfirmAsrRequest, ConfirmTranslationRequest,
    StopTranslationRequest, StartTranslationResponse, TranslationStatusResponse,
    TranslationMode, TranslationStatusEnum, EventTypeEnum,
    TranslationProgressEvent, LogEvent, AsrConfirmRequiredEvent,
    TranslationConfirmRequiredEvent, CompletedEvent, ErrorEvent, 
    StoppedEvent, StatusEvent, TaskState
)

# 导入 VideoTranslate_Workflow 组件（适配器模式）
from ..video_downloader import VideoDownloader
from ..audio_processor import AudioProcessor
from ..speech_to_text import SpeechToText
from ..translate_text import DistributedTranslation
from ..ai_services import AIServices
from ..config import OUTPUT_DIR
from ..common.stop_flag import StopFlag
from ..cleanup_temp import cleanup_temp_files

# 导入UI配置（用于语言映射）
import sys
from pathlib import Path
_windows_path = Path(__file__).parent.parent.parent / 'VideoTranslate_Windows'
if str(_windows_path) not in sys.path:
    sys.path.insert(0, str(_windows_path))
try:
    from ui_config import DISPLAY_TO_CODE_MAP, LANGUAGE_CODE_MAP, ASR_DEFAULT_THRESHOLD, ASR_DEFAULT_COEFFICIENT  # type: ignore[import] # noqa: E402
except ImportError:
    # Fallback defaults if ui_config is not available
    DISPLAY_TO_CODE_MAP = {"中文": "zh", "英文": "en", "日文": "ja", "韩文": "ko", "法文": "fr", "德文": "de", "西班牙文": "es", "俄文": "ru"}
    LANGUAGE_CODE_MAP = {"zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean", "fr": "French", "de": "German", "es": "Spanish", "ru": "Russian"}
    ASR_DEFAULT_THRESHOLD = 0.95
    ASR_DEFAULT_COEFFICIENT = 1.0

# 配置日志
import logging
logging.basicConfig(level=getattr(logging, LOG_LEVEL))
logger = logging.getLogger(__name__)


# ==================== 全局状态 ====================

# 任务存储 {task_id: TaskState}
tasks: Dict[str, TaskState] = {}

# 事件队列 {task_id: asyncio.Queue}
event_queues: Dict[str, asyncio.Queue] = {}

# 任务锁
task_lock = threading.Lock()

# 运行状态
server_running = True


# ==================== FastAPI应用 ====================

app = FastAPI(
    title="VideoTranslate API",
    description="视频翻译服务API",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 工具函数 ====================

def get_event_queue(task_id: str) -> asyncio.Queue:
    """获取或创建任务事件队列"""
    if task_id not in event_queues:
        event_queues[task_id] = asyncio.Queue()
    return event_queues[task_id]


def parse_target_language(selected_display: str) -> tuple[str, str]:
    """解析目标语言"""
    lang_code = DISPLAY_TO_CODE_MAP.get(selected_display, "zh")
    target_language = LANGUAGE_CODE_MAP.get(lang_code, "Chinese")
    return lang_code, target_language


async def send_event(task_id: str, event_data: dict, event_type: str = "message"):
    """发送事件到队列"""
    queue = get_event_queue(task_id)
    await queue.put({
        "event": event_type,
        "data": json.dumps(event_data, ensure_ascii=False)
    })


def create_task_state(task_id: str, input_value: str, target_language_code: str, mode: TranslationMode) -> TaskState:
    """创建任务状态"""
    return TaskState(
        task_id=task_id,
        status=TranslationStatusEnum.READY,
        input_value=input_value,
        target_language_code=target_language_code,
        mode=mode,
        current_step=0,
        total_steps=6,
        progress=0.0,
        message="就绪",
        created_at=datetime.now(),
        logs=[]
    )


# ==================== 任务执行逻辑 ====================

def run_translation_task(
    task_id: str,
    input_value: str,
    target_language_display: str,
    mode: TranslationMode
):
    """在后台线程中运行翻译任务（适配器模式 - 调用 VideoTranslate_Workflow 组件）"""
    def log_callback(message: str):
        """日志回调"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        # 添加到任务日志
        with task_lock:
            if task_id in tasks:
                tasks[task_id].logs.append(f"[{timestamp}] {message}")

        # 发送日志事件
        asyncio.run_coroutine_threadsafe(
            send_event(task_id, {
                "event_type": EventTypeEnum.LOG,
                "timestamp": timestamp,
                "message": message
            }, "log"),
            asyncio.get_event_loop()
        )

    async def update_step(step: int, message: str, progress: float):
        """更新步骤进度"""
        with task_lock:
            if task_id in tasks:
                tasks[task_id].current_step = step
                tasks[task_id].progress = progress
                tasks[task_id].message = message

        await send_event(task_id, {
            "event_type": EventTypeEnum.PROGRESS,
            "current_step": step,
            "total_steps": 6,
            "message": message,
            "progress": progress
        }, "progress")

    try:
        # 创建事件循环用于异步操作
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # 更新状态
        with task_lock:
            if task_id in tasks:
                tasks[task_id].status = TranslationStatusEnum.PROCESSING
                tasks[task_id].message = "翻译中..."

        # 发送状态事件
        asyncio.run_coroutine_threadsafe(
            send_event(task_id, {
                "event_type": EventTypeEnum.STATUS,
                "status": TranslationStatusEnum.PROCESSING,
                "message": "翻译中..."
            }, "status"),
            asyncio.get_event_loop()
        )

        # 解析语言
        lang_code, target_language = parse_target_language(target_language_display)
        log_callback(f"目标语言: {target_language} ({lang_code})")

        # 创建停止标志
        stop_flag = StopFlag()

        # ========== 适配器：调用 VideoTranslate_Workflow 组件 ==========

        # 步骤 1: 准备视频文件
        log_callback("\n[步骤 1/6] 准备视频文件...")
        video_path, bv_id = VideoDownloader.prepare_video(input_value)
        if bv_id:
            log_callback(f"✓ 视频就绪: {video_path} (BV号: {bv_id})")
        else:
            log_callback(f"✓ 视频就绪: {video_path}")

        asyncio.run_coroutine_threadsafe(
            update_step(1, "准备视频文件", 0.15),
            asyncio.get_event_loop()
        )

        # 步骤 2: 提取音频
        log_callback("\n[步骤 2/6] 提取原始音频...")
        original_audio = AudioProcessor.extract_audio(video_path)
        log_callback(f"✓ 音频提取完成: {original_audio}")

        asyncio.run_coroutine_threadsafe(
            update_step(2, "提取音频", 0.3),
            asyncio.get_event_loop()
        )

        # 步骤 3: 语音识别(ASR)
        log_callback("\n[步骤 3/6] 语音识别(ASR)...")
        log_callback("提示: 这可能需要几分钟,请耐心等待...")

        stt = SpeechToText(stop_flag=stop_flag)
        original_text = stt.recognize(original_audio)
        log_callback(f"✓ 识别完成,共 {len(original_text)} 字符")

        asyncio.run_coroutine_threadsafe(
            update_step(3, "语音识别", 0.5),
            asyncio.get_event_loop()
        )

        # 保存原文
        if bv_id:
            original_text_file = OUTPUT_DIR / f"{bv_id}_original.txt"
        else:
            video_name = Path(video_path).stem
            original_text_file = OUTPUT_DIR / f"{video_name}_original.txt"
        original_text_file.write_text(original_text, encoding="utf-8")
        log_callback(f"  原文已保存: {original_text_file}")

        # 步骤 4: ASR 确认（通过回调）
        log_callback("\n[确认] 等待用户确认ASR识别结果...")

        # 发送 ASR 确认请求事件
        show_single = ASR_DEFAULT_COEFFICIENT >= ASR_DEFAULT_THRESHOLD
        asr_data = {
            "text": original_text,
            "coefficient": ASR_DEFAULT_COEFFICIENT,
            "threshold": ASR_DEFAULT_THRESHOLD,
            "show_single": show_single,
            "alternative_text": ""  # 简化处理，暂不提供备选文本
        }

        with task_lock:
            if task_id in tasks:
                tasks[task_id].asr_data = asr_data

        asyncio.run_coroutine_threadsafe(
            send_event(task_id, {
                "event_type": EventTypeEnum.ASR_CONFIRM_REQUIRED,
                "task_id": task_id,
                "text": original_text,
                "alternative_text": None,
                "coefficient": ASR_DEFAULT_COEFFICIENT,
                "threshold": ASR_DEFAULT_THRESHOLD
            }, "asr_confirm_required"),
            asyncio.get_event_loop()
        )

        # 等待用户确认（简化处理：等待一段时间后检查）
        import time
        time.sleep(1)

        confirmed_asr_text = original_text
        with task_lock:
            if task_id in tasks and tasks[task_id].asr_confirmed:
                task_data = tasks[task_id]
                if task_data.asr_data is not None:
                    confirmed_asr_text = task_data.asr_data.get("confirmed_text", original_text)

        display_text = confirmed_asr_text[:50] + "..." if len(confirmed_asr_text) > 50 else confirmed_asr_text
        log_callback(f"✓ ASR结果已确认: {display_text}")

        # 步骤 5: 翻译文本
        log_callback(f"\n[步骤 4/6] 翻译文本 (目标语言: {target_language})...")

        translator = DistributedTranslation(mode.value, stop_flag=stop_flag)
        translated_text, translation_score = translator.translate(confirmed_asr_text, target_language)

        log_callback(f"✓ 翻译完成,共 {len(translated_text)} 字符")

        if translation_score:
            log_callback(f"✓ 翻译质量评分: {translation_score.overall_score:.1f}/100")
            if translation_score.suggestions:
                log_callback("✓ 改进建议:")
                for i, suggestion in enumerate(translation_score.suggestions[:3], 1):
                    log_callback(f"  {i}. {suggestion}")

        asyncio.run_coroutine_threadsafe(
            update_step(4, "翻译文本", 0.65),
            asyncio.get_event_loop()
        )

        # 保存译文
        if bv_id:
            translated_text_file = OUTPUT_DIR / f"{bv_id}_{target_language}.txt"
        else:
            video_name = Path(video_path).stem
            translated_text_file = OUTPUT_DIR / f"{video_name}_translated_{target_language}.txt"
        translated_text_file.write_text(translated_text, encoding="utf-8")
        log_callback(f"  译文已保存: {translated_text_file}")

        # 步骤 6: 翻译确认（通过回调）
        log_callback("\n[确认] 等待用户确认翻译结果...")

        with task_lock:
            if task_id in tasks:
                tasks[task_id].translation_text = translated_text

        asyncio.run_coroutine_threadsafe(
            send_event(task_id, {
                "event_type": EventTypeEnum.TRANSLATION_CONFIRM_REQUIRED,
                "task_id": task_id,
                "text": translated_text,
                "score": translation_score.overall_score if translation_score else None,
                "suggestions": translation_score.suggestions if translation_score else None
            }, "translation_confirm_required"),
            asyncio.get_event_loop()
        )

        # 等待用户确认
        import time
        time.sleep(1)

        confirmed_translation = translated_text
        with task_lock:
            if task_id in tasks and tasks[task_id].translation_confirmed:
                confirmed_translation = tasks[task_id].translation_text or translated_text

        display_text = confirmed_translation[:50] + "..." if len(confirmed_translation) > 50 else confirmed_translation
        log_callback(f"✓ 翻译结果已确认: {display_text}")

        # 步骤 7: 语音合成(TTS)
        log_callback("\n[步骤 5/6] 语音合成(TTS)...")
        log_callback("提示: 正在生成新的配音...")

        ai_services = AIServices(mode.value)
        new_audio = ai_services.text_to_speech(confirmed_translation, language=target_language)  # type: ignore[attr-defined]
        log_callback(f"✓ 语音合成完成: {new_audio}")

        asyncio.run_coroutine_threadsafe(
            update_step(5, "语音合成", 0.85),
            asyncio.get_event_loop()
        )

        # 步骤 8: 替换音频
        log_callback("\n[步骤 6/6] 合成最终视频...")
        log_callback("提示: 正在合成视频,这可能需要几分钟...")
        output_video = AudioProcessor.replace_audio(
            video_path, new_audio, bv_id=bv_id, target_language=target_language
        )
        log_callback("✓ 视频合成完成!")

        asyncio.run_coroutine_threadsafe(
            update_step(6, "合成最终视频", 1.0),
            asyncio.get_event_loop()
        )

        # 完成
        log_callback(f"\n翻译完成! 输出视频: {output_video}")

        # 自动清理临时文件
        log_callback("\n正在清理临时文件...")
        cleanup_temp_files(keep_video_path=str(output_video))
        log_callback("✓ 临时文件清理完成")

        # 更新状态为完成
        with task_lock:
            if task_id in tasks:
                tasks[task_id].status = TranslationStatusEnum.COMPLETED
                tasks[task_id].message = "翻译完成"
                tasks[task_id].output_file = str(output_video)

        # 发送完成事件
        asyncio.run_coroutine_threadsafe(
            send_event(task_id, {
                "event_type": EventTypeEnum.COMPLETED,
                "task_id": task_id,
                "output_file": str(output_video)
            }, "completed"),
            asyncio.get_event_loop()
        )

        loop.close()

    except Exception as e:
        error_msg = str(e)
        logger.exception(f"翻译任务错误: {error_msg}")

        with task_lock:
            if task_id in tasks:
                tasks[task_id].status = TranslationStatusEnum.ERROR
                tasks[task_id].message = f"错误: {error_msg}"
                tasks[task_id].error_message = error_msg

        asyncio.run_coroutine_threadsafe(
            send_event(task_id, {
                "event_type": EventTypeEnum.ERROR,
                "task_id": task_id,
                "message": error_msg
            }, "error"),
            asyncio.get_event_loop()
        )


# ==================== API端点 ====================

@app.get("/")
async def root():
    """根路径 - API信息"""
    return {
        "name": "VideoTranslate API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.post("/api/v1/translate/start", response_model=StartTranslationResponse)
async def start_translation(request: StartTranslationRequest):
    """开始翻译任务"""
    # 生成任务ID
    task_id = str(uuid.uuid4())[:8]
    
    # 创建任务状态
    task_state = create_task_state(
        task_id=task_id,
        input_value=request.input_value,
        target_language_code=request.target_language_code,
        mode=request.mode
    )
    
    with task_lock:
        tasks[task_id] = task_state
    
    # 在后台线程运行翻译任务
    thread = threading.Thread(
        target=run_translation_task,
        args=(
            task_id,
            request.input_value,
            request.target_language_code,
            request.mode
        ),
        daemon=True
    )
    thread.start()
    
    logger.info(f"翻译任务已启动: {task_id}")
    
    return StartTranslationResponse(
        success=True,
        task_id=task_id,
        message="翻译任务已启动"
    )


@app.post("/api/v1/translate/confirm/asr")
async def confirm_asr(request: ConfirmAsrRequest):
    """确认ASR结果"""
    with task_lock:
        if request.task_id not in tasks:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        task = tasks[request.task_id]
        if task.asr_confirmed:
            raise HTTPException(status_code=400, detail="ASR已确认")

        # 更新确认的文本
        if task.asr_data is None:
            task.asr_data = {}
        task.asr_data["confirmed_text"] = request.confirmed_text
        task.asr_confirmed = True
    
    return {"success": True, "message": "ASR结果已确认"}


@app.post("/api/v1/translate/confirm/translation")
async def confirm_translation(request: ConfirmTranslationRequest):
    """确认翻译结果"""
    with task_lock:
        if request.task_id not in tasks:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        task = tasks[request.task_id]
        if task.translation_confirmed:
            raise HTTPException(status_code=400, detail="翻译已确认")

        # 更新确认的文本
        task.translation_text = request.confirmed_text
        task.translation_confirmed = True
    
    return {"success": True, "message": "翻译结果已确认"}


@app.post("/api/v1/translate/stop")
async def stop_translation(request: StopTranslationRequest):
    """停止翻译任务"""
    with task_lock:
        if request.task_id not in tasks:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        task = tasks[request.task_id]
        if task.status not in [TranslationStatusEnum.PROCESSING, TranslationStatusEnum.READY]:
            raise HTTPException(status_code=400, detail="任务未在运行中")
        
        task.status = TranslationStatusEnum.STOPPED
        task.message = "正在停止..."
    
    return {"success": True, "message": "停止请求已发送"}


@app.get("/api/v1/translate/status/{task_id}", response_model=TranslationStatusResponse)
async def get_status(task_id: str):
    """获取任务状态"""
    with task_lock:
        if task_id not in tasks:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        task = tasks[task_id]
    
    return TranslationStatusResponse(
        task_id=task_id,
        status=task.status,
        message=task.message,
        current_step=task.current_step,
        total_steps=task.total_steps,
        progress=task.progress
    )


@app.get("/api/v1/translate/logs/{task_id}")
async def get_logs(task_id: str):
    """获取任务日志"""
    with task_lock:
        if task_id not in tasks:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        logs = list(tasks[task_id].logs)
    
    return {"logs": logs}


@app.get("/api/v1/translate/events/{task_id}")
async def events(task_id: str):
    """SSE事件流"""
    async def event_generator():
        queue = get_event_queue(task_id)
        
        try:
            while True:
                # 检查任务是否还存在
                with task_lock:
                    if task_id not in tasks:
                        break
                
                try:
                    # 等待事件，超时30秒
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield event
                except asyncio.TimeoutError:
                    # 发送心跳
                    yield {"event": "heartbeat", "data": json.dumps({"keepalive": True})}
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"SSE错误: {e}")
        finally:
            # 清理
            if task_id in event_queues:
                del event_queues[task_id]
    
    return EventSourceResponse(event_generator())


@app.delete("/api/v1/translate/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除任务（清理资源）"""
    with task_lock:
        if task_id not in tasks:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        del tasks[task_id]
        
        if task_id in event_queues:
            del event_queues[task_id]
    
    return {"success": True, "message": "任务已删除"}


@app.get("/api/v1/tasks")
async def list_tasks():
    """列出所有任务"""
    with task_lock:
        task_list = [
            {
                "task_id": task_id,
                "status": task.status.value,
                "input_value": task.input_value,
                "created_at": task.created_at.isoformat()
            }
            for task_id, task in tasks.items()
        ]
    
    return {"tasks": task_list}


# ==================== 启动服务器 ====================

def run_server():
    """运行API服务器"""
    import uvicorn
    uvicorn.run(
        app,
        host=API_HOST,
        port=API_PORT,
        log_level=LOG_LEVEL.lower()
    )


if __name__ == "__main__":
    run_server()
