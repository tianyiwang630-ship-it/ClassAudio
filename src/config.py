"""
ClassAudio Configuration File
集中管理所有配置参数
"""
import os

# ====== 路径配置 ======
# BASE_DIR 现在指向项目根目录（src/ 的父目录）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# 从本机 .env 读取密钥；.env 已被 .gitignore 排除，禁止把真实密钥写进源码。
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(BASE_DIR, ".env"))
except ImportError:
    pass

# ====== NeMo-Speech.cpp / Nemotron ASR ======
NEMO_RUNTIME_EXE = os.path.join(
    BASE_DIR, "tools", "nemo-speech", "runtime", "bin", "nemo-speech.exe"
)
NEMO_MODEL_EN = os.path.join(
    DATA_DIR,
    "models",
    "nemotron-speech-streaming-en-0.6b",
    "nemotron-speech-streaming-en-0.6b.with-tokenizer.q8_0.gguf",
)
NEMO_MODEL_MULTILINGUAL = os.path.join(
    DATA_DIR,
    "models",
    "nemotron-3.5-asr-streaming-0.6b",
    "nemotron-3.5-asr-streaming-0.6b.with-tokenizer.q8_0.gguf",
)

# 英文课堂默认使用英文专用模型。设为 multilingual 可切换中英文多语言模型。
NEMO_MODEL_VARIANT = os.getenv("CLASSAUDIO_ASR_MODEL", "en").strip().lower()
NEMO_MODEL_PATH = (
    NEMO_MODEL_MULTILINGUAL if NEMO_MODEL_VARIANT == "multilingual" else NEMO_MODEL_EN
)
NEMO_LANGUAGE = os.getenv(
    "CLASSAUDIO_ASR_LANGUAGE",
    "auto" if NEMO_MODEL_VARIANT == "multilingual" else "en-US",
)
NEMO_DEVICE = os.getenv("CLASSAUDIO_ASR_DEVICE", "cuda")
NEMO_SERVER_HOST = "127.0.0.1"
NEMO_SERVER_PORT = int(os.getenv("CLASSAUDIO_ASR_PORT", "8765"))
NEMO_SERVER_URL = f"http://{NEMO_SERVER_HOST}:{NEMO_SERVER_PORT}"
NEMO_REALTIME_URL = f"ws://{NEMO_SERVER_HOST}:{NEMO_SERVER_PORT}/v1/realtime"
NEMO_STARTUP_TIMEOUT_S = 60
# 端点检测静音阈值。课堂讲解中的换气/思考停顿可能超过 800ms，
# 提高到 1600ms 可减少一句话尚未结束就被切成两段的情况。
NEMO_ENDPOINTING_MS = int(os.getenv("CLASSAUDIO_ENDPOINTING_MS", "1600"))
NEMO_HOTWORD_BOOST = float(os.getenv("CLASSAUDIO_HOTWORD_BOOST", "1.8"))
NEMO_MAX_HOTWORDS = 100

# 输出路径
LOGS_DIR = os.path.join(DATA_DIR, "logs")
OUT_TXT = os.path.join(LOGS_DIR, "captions.txt")
TRANSCRIPT_LIST_JSON = os.path.join(DATA_DIR, "transcript_list.json")

# ====== 音频配置 ======
SR = 16000  # 采样率
CHANNELS = 1  # 单声道
BLOCK_MS = 32  # 每个音频块的毫秒数
BLOCK_SAMPLES = int(SR * BLOCK_MS / 1000)

# 队列大小
AUDIO_Q_MAX = 300
UTT_Q_MAX = 4000

# 最短最终字幕长度。模型自身负责流式分段和端点检测。
MIN_CHARS_TO_PRINT = 2

# ====== LLM 配置 ======
# DeepSeek V4 Flash 配置
# Demo 项目暂时提供本地默认值；同名环境变量仍可覆盖这些配置。
DEEPSEEK_API_KEY = os.getenv(
    "DEEPSEEK_API_KEY",
    "",
)
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

# LLM 处理配置
LLM_CHUNK_SIZE = 4  # 每次处理的转写文本数量
LLM_OUTPUT_JSON = os.path.join(LOGS_DIR, "llmcontent-latest.json")

# 可选的本机覆盖文件（文件名已被 .gitignore 排除）。
try:
    from .config_local import *
except ImportError:
    pass

# 确保 logs 目录存在
os.makedirs(LOGS_DIR, exist_ok=True)

