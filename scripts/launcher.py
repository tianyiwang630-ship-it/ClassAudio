"""
ClassAudio Launcher
一键启动后端服务和前端页面
"""
import os
import sys
import time
import subprocess
import webbrowser
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
import socket

from src.config import (
    NEMO_DEVICE,
    NEMO_ENDPOINTING_MS,
    NEMO_MODEL_PATH,
    NEMO_RUNTIME_EXE,
    NEMO_SERVER_HOST,
    NEMO_SERVER_PORT,
    NEMO_SERVER_URL,
    NEMO_STARTUP_TIMEOUT_S,
)
from src.services.nemo_streaming import NemoSpeechServer

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')


# ==================== 配置 ====================
BACKEND_PORT = 8000
FRONTEND_PORT = 8080
FRONTEND_DIR = "frontend"


# ==================== 工具函数 ====================
def print_banner():
    """打印启动横幅"""
    banner = """
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║              📚  ClassAudio 实时课堂转写系统                  ║
║                                                            ║
║                      一键启动器 v1.0                         ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    """
    print(banner)


def check_port(port):
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) != 0


def wait_for_backend(timeout=30):
    """等待后端服务启动"""
    print(f"\n⏳ 等待后端服务启动 (端口 {BACKEND_PORT})...")

    start_time = time.time()
    while time.time() - start_time < timeout:
        if not check_port(BACKEND_PORT):
            print("✅ 后端服务已就绪！")
            return True
        time.sleep(0.5)

    return False


# ==================== 后端服务 ====================
def start_asr_server():
    """启动由一键启动器统一管理的本地 Nemotron 服务。"""
    print("\n🧠 正在加载 Nemotron 流式语音模型...")
    server = NemoSpeechServer(
        executable=NEMO_RUNTIME_EXE,
        model_path=NEMO_MODEL_PATH,
        server_url=NEMO_SERVER_URL,
        host=NEMO_SERVER_HOST,
        port=NEMO_SERVER_PORT,
        device=NEMO_DEVICE,
        endpointing_ms=NEMO_ENDPOINTING_MS,
        startup_timeout_s=NEMO_STARTUP_TIMEOUT_S,
        log=lambda message: print(f"[ASR] {message}"),
    )
    try:
        server.start()
        print("✅ Nemotron 流式语音模型已就绪")
        return server
    except Exception as exc:
        print(f"❌ Nemotron 启动失败: {exc}")
        server.stop()
        return None


def start_backend():
    """启动后端 API 服务"""
    print("\n🚀 正在启动后端服务...")

    # 检查端口
    if not check_port(BACKEND_PORT):
        print(f"⚠️  警告: 端口 {BACKEND_PORT} 已被占用，后端可能已在运行")
        return None

    # 添加项目根目录到 Python 路径
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, project_root)

    try:
        # 启动 FastAPI 服务
        cmd = [
            sys.executable,
            "-m", "uvicorn",
            "src.api.server:app",
            "--host", "0.0.0.0",
            "--port", str(BACKEND_PORT),
            "--log-level", "info"
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding='utf-8',
            errors='replace',  # 替换无法解码的字符
            bufsize=1
        )

        print(f"✅ 后端服务进程已启动 (PID: {process.pid})")
        return process

    except Exception as e:
        print(f"❌ 后端服务启动失败: {e}")
        return None


# ==================== 前端服务 ====================
class FrontendHandler(SimpleHTTPRequestHandler):
    """自定义 HTTP 处理器"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=FRONTEND_DIR, **kwargs)

    def log_message(self, format, *args):
        """静默日志输出"""
        pass


def start_frontend():
    """启动前端 HTTP 服务"""
    print(f"\n🌐 正在启动前端服务 (端口 {FRONTEND_PORT})...")

    # 检查端口
    if not check_port(FRONTEND_PORT):
        print(f"⚠️  警告: 端口 {FRONTEND_PORT} 已被占用")
        return None

    # 检查前端目录
    if not os.path.exists(FRONTEND_DIR):
        print(f"❌ 错误: 前端目录 '{FRONTEND_DIR}' 不存在")
        return None

    try:
        server = HTTPServer(('localhost', FRONTEND_PORT), FrontendHandler)
        print(f"✅ 前端服务已就绪")

        # 在后台线程运行服务器
        def run_server():
            server.serve_forever()

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()

        return server

    except Exception as e:
        print(f"❌ 前端服务启动失败: {e}")
        return None


# ==================== 浏览器 ====================
def open_browser():
    """打开浏览器"""
    url = f"http://localhost:{FRONTEND_PORT}/index.html"

    print(f"\n🌍 正在打开浏览器...")
    print(f"   地址: {url}")

    time.sleep(2)  # 等待服务完全启动

    try:
        webbrowser.open(url)
        print("✅ 浏览器已打开")
    except Exception as e:
        print(f"⚠️  无法自动打开浏览器: {e}")
        print(f"   请手动访问: {url}")


# ==================== 后台日志监控 ====================
def monitor_backend_logs(process):
    """监控后端日志输出"""
    if not process:
        return

    def read_logs():
        for line in iter(process.stdout.readline, ''):
            if line:
                # 过滤掉过多的 INFO 日志
                if 'INFO' in line and 'GET' in line:
                    continue
                print(f"[后端] {line.rstrip()}")

    thread = threading.Thread(target=read_logs, daemon=True)
    thread.start()


# ==================== 主函数 ====================
def main():
    """主函数"""
    print_banner()

    print("\n📋 启动检查清单:")
    print("   ✓ Python 环境")
    print("   ✓ 依赖包 (uvicorn, fastapi)")
    print("   ✓ Nemotron 流式语音模型")
    print("   ✓ 后端服务 (FastAPI)")
    print("   ✓ 前端服务 (HTTP Server)")
    print("   ✓ 浏览器")

    # 1. 启动 ASR（由启动器持有，确保 Windows 退出时不会遗留 GPU 进程）
    asr_server = start_asr_server()
    if not asr_server:
        sys.exit(1)

    # 2. 启动后端
    backend_process = start_backend()

    if backend_process:
        # 等待后端就绪
        if not wait_for_backend():
            print("❌ 后端服务启动超时")
            if backend_process:
                backend_process.terminate()
            asr_server.stop()
            sys.exit(1)

        # 监控后端日志
        monitor_backend_logs(backend_process)

    # 3. 启动前端
    frontend_server = start_frontend()

    if not frontend_server and not backend_process:
        print("\n❌ 启动失败，请检查以上错误信息")
        asr_server.stop()
        sys.exit(1)

    # 4. 打开浏览器
    open_browser()

    # 5. 显示信息
    print("\n" + "=" * 60)
    print("🎉 ClassAudio 已成功启动！")
    print("=" * 60)
    print(f"\n📊 服务信息:")
    print(f"   • 后端 API:  http://localhost:{BACKEND_PORT}")
    print(f"   • API 文档:  http://localhost:{BACKEND_PORT}/docs")
    print(f"   • 前端页面:  http://localhost:{FRONTEND_PORT}/index.html")
    print(f"   • WebSocket: ws://localhost:{BACKEND_PORT}/ws/captions")

    print(f"\n💡 使用提示:")
    print(f"   1. 在浏览器中点击 '开始录音' 按钮")
    print(f"   2. 对着麦克风说话")
    print(f"   3. 查看实时字幕和结构化笔记")
    print(f"   4. 点击 '停止录音' 结束")

    print(f"\n⚠️  按 Ctrl+C 停止所有服务")
    print("=" * 60)

    # 6. 保持运行
    try:
        while True:
            time.sleep(1)

            # 检查后端进程是否还在运行
            if backend_process and backend_process.poll() is not None:
                print("\n⚠️  后端进程已退出")
                break

    except KeyboardInterrupt:
        print("\n\n🛑 正在停止服务...")
    finally:
        if frontend_server:
            frontend_server.shutdown()
            print("✅ 前端服务已停止")

        if backend_process:
            backend_process.terminate()
            try:
                backend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend_process.kill()
            print("✅ 后端服务已停止")

        asr_server.stop()
        print("✅ Nemotron 语音服务已停止")
        print("\n👋 ClassAudio 已关闭，感谢使用！\n")


if __name__ == "__main__":
    # 检查依赖
    try:
        import uvicorn
        import fastapi
    except ImportError as e:
        print(f"\n❌ 缺少依赖: {e}")
        print("\n请先安装依赖:")
        print("   pip install -r requirements.txt")
        sys.exit(1)

    main()
