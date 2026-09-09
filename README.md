# ClassAudio - AI驱动的智能课堂转写系统

<p align="center">
  <strong>实时语音转写 | AI智能整理 | 专业术语优化</strong>
</p>

<p align="center">
  <a href="README_EN.md">English</a> | 中文
</p>

---

## 📖 项目背景

在现代教育和学习场景中，高质量的课堂笔记对知识吸收至关重要。然而，传统的手写笔记存在以下痛点：

- **分心问题**：手写笔记会分散学生对课堂内容的注意力
- **专业术语障碍**：技术课程中的专业词汇难以快速准确记录
- **整理成本高**：课后需要花费大量时间整理和分类笔记
- **信息缺失**：无法同时专注听讲和记录完整内容

ClassAudio 通过 AI 技术解决这些痛点，提供**实时、准确、结构化**的课堂转写服务。

---

## ✨ 核心功能

### 1. 实时语音转写
- **低延迟显示**：边说边显示，延迟 < 1 秒
- **原生流式架构**：单个 Nemotron Streaming 模型同时输出实时片段和最终字幕
- **模型端点检测**：根据语音停顿自动完成一句字幕

### 2. AI 智能词汇优化
- **课堂主题感知**：输入课堂主题（如 "量子计算"、"Transformer 架构"）
- **LLM 生成专业词汇**：自动生成 30+ 相关专业术语
- **提升转写准确度**：将生成的词汇作为解码器 `speech_contexts` 热词进行加权

### 3. 结构化笔记整理
- **自动分类**：LLM 将转写内容分类为：
  - 📚 课程内容（Course Content）
  - 💡 知识点（Knowledge Points）
  - ❓ 问题讨论（Questions & Discussions）
- **实时生成**：每 4 条转写文本自动触发整理
- **JSON 导出**：支持导出结构化笔记数据

### 4. 优质用户体验
- **美观界面**：现代化渐变设计 + 流畅动画
- **稳定连接**：WebSocket 心跳保活 + 自动重连机制
- **一键启动**：Windows 双击启动，自动打开浏览器

### 📹 演示视频

https://github.com/user-attachments/assets/4bd1ee1a-5e41-4872-a30d-9abf60c47dfd 


## 🎯 核心价值

### 对学生
- ✅ **专注听讲**：无需分心手写，自动生成完整笔记
- ✅ **高精度记录**：专业术语准确识别，无遗漏
- ✅ **快速复习**：结构化笔记便于课后查找和复习

### 对教育机构
- ✅ **提升教学质量**：学生更专注课堂互动
- ✅ **知识留存**：完整保留课堂知识内容
- ✅ **数据分析**：可分析课程关键词和学生提问

### 对开发者
- ✅ **开源免费**：MIT 协议，可自由修改和商用
- ✅ **易于扩展**：模块化架构，支持自定义 LLM 和模型
- ✅ **完整文档**：详细技术文档 + 故障排查指南

---

## 🛠️ 技术实现

### 系统架构

```
┌─────────────────────────────────────────────────────┐
│                    前端 (Frontend)                   │
│  - WebSocket 实时连接  - Toast 通知  - 响应式 UI     │
└────────────────────┬────────────────────────────────┘
                     │ WebSocket + HTTP API
┌────────────────────▼────────────────────────────────┐
│              FastAPI 服务器 (Backend)                │
│  - WebSocket 推送  - RESTful API  - 自动重连机制     │
└──────┬──────────────────────────────────┬───────────┘
       │                                  │
┌──────▼──────────────┐        ┌──────────▼───────────┐
│  Audio Service      │        │   LLM Service        │
│  ┌──────────────┐   │        │  ┌────────────────┐  │
│  │ PCM16 采集   │   │        │  │ 内容分类整理    │  │
│  └──────┬───────┘   │        │  └────────────────┘  │
│  ┌──────▼───────┐   │        │  ┌────────────────┐  │
│  │ 流式 delta   │   │        │  │ 关键词生成      │  │
│  └──────────────┘   │        │  └────────────────┘  │
│  ┌──────────────┐   │        │                      │
│  │ Final 事件   │   │        │ LLM: DeepSeek V4     │
│  └──────────────┘   │        │       Flash          │
└─────────────────────┘        └──────────────────────┘
 Nemotron + NeMo-Speech.cpp          OpenAI API
```

### 核心技术栈

**后端**
- **FastAPI** - 高性能异步 Web 框架
- **WebSocket** - 实时双向通信
- **NeMo-Speech.cpp** - 本地 CUDA 流式 ASR 运行时
- **sounddevice** - 实时 PCM16 音频流捕获

**前端**
- **原生 JavaScript** - 无框架依赖，性能优先
- **WebSocket API** - 实时数据推送
- **CSS Grid/Flexbox** - 现代化响应式布局

**AI 模型**
- **Nemotron Speech Streaming 0.6B** - NVIDIA 英文流式语音识别模型
- **DeepSeek V4 Flash** - 用于专业词汇生成、内容结构化整理和课堂问答

### 关键技术亮点

1. **单模型原生流式架构**
   - `delta` 事件提供即时字幕
   - `completed` 事件提供可送入 LLM 的最终字幕

2. **动态热词加权**
   - LLM 根据课堂主题生成专业词汇
   - 动态注入 Nemotron 解码器的 `speech_contexts`
   - 显著提升专业术语识别准确率

3. **流式端点检测**
   - 模型根据语音停顿自动输出最终句子
   - 默认端点静音阈值为 800ms
   - 避免句子截断和过度分割

4. **鲁棒性设计**
   - WebSocket 心跳保活（30s 间隔）
   - 自动重连机制（指数退避）
   - 详细日志系统（分级日志 + 实时查看工具）

---

## 🚀 快速开始

### 环境要求

- **Python 3.10+**
- **CUDA** (可选，GPU 加速)
- **麦克风设备**

### 安装步骤

1. **克隆仓库**
```bash
git clone https://github.com/yourusername/classaudio.git
cd classaudio
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **确认本地模型**

当前项目使用带内嵌 tokenizer 的 Q8 GGUF；热词加权依赖该 tokenizer。
模型文件和 `tools/nemo-speech/runtime/` 预编译运行包体积较大，均被 `.gitignore` 排除，
不会随代码提交；在新电脑上需要按部署说明另行下载并解压到对应目录。

**目录结构示例：**
```
data/
├── models/
│   ├── nemotron-speech-streaming-en-0.6b/
│   │   └── nemotron-speech-streaming-en-0.6b.with-tokenizer.q8_0.gguf
│   └── nemotron-3.5-asr-streaming-0.6b/
│       └── nemotron-3.5-asr-streaming-0.6b.with-tokenizer.q8_0.gguf
```

4. **配置 API Keys**

**方法 1：使用环境变量（推荐）**
```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 API keys
```

**需要的 API Keys：**
- `DEEPSEEK_API_KEY` - 用于关键词生成、内容整理和课堂问答（DeepSeek V4 Flash）

5. **启动应用**

**Windows 用户（推荐）：**
```bash
启动ClassAudio.bat
```

**通用方式：**
```bash
python run.py
```

浏览器会自动打开 `http://localhost:8080/index.html`。

### 使用流程

1. **设置课堂主题**（可选但推荐）
   - 在页面顶部输入框输入主题，如 "量子计算"、"深度学习"
   - 点击"设置主题"，等待 LLM 生成专业词汇（约 5-15 秒）

2. **开始录音**
   - 点击"开始录音"按钮
   - 对着麦克风说话
   - 实时字幕会即时显示

3. **查看结果**
   - **Partial 字幕**：实时预览（灰色）
   - **Accurate 字幕**：最终结果（绿色，带质量指标）
   - **结构化笔记**：页面右侧自动分类显示

---

## 📁 项目结构

```
classaudio/
├── src/                        # 源代码
│   ├── services/               # 核心服务
│   │   ├── audio_service.py    # 音频转写服务
│   │   └── llm_service.py      # LLM 处理服务
│   ├── api/                    # API 接口
│   │   └── server.py           # FastAPI 服务器
│   ├── agent/                  # LLM 代理
│   │   ├── keywords.py         # 关键词生成
│   │   ├── llm.py              # LLM 接口
│   │   └── prompt.py           # 提示词模板
│   ├── config.py               # 配置文件
│   └── config.example.py       # 配置示例
│
├── frontend/                   # 前端界面
│   ├── index.html              # 主页面
│   ├── app.js                  # 前端逻辑
│   └── styles.css              # 样式文件
│
├── scripts/                    # 工具脚本
│   └── launcher.py             # 启动器
│
├── docs/                       # 文档
│   ├── 快速启动指南.md
│   ├── 课堂主题功能说明.md
│   ├── 故障排查指南.md
│   └── 日志系统说明.md
│
├── data/                       # 数据目录（Git 忽略）
│   ├── models/                 # Nemotron GGUF 模型（需手动下载）
│   └── logs/                   # 运行时日志
│
├── tools/nemo-speech/          # NeMo 运行包（Git 忽略，需单独安装）
├── .env.example                # 环境变量示例
├── .gitignore                  # Git 忽略配置
├── requirements.txt            # Python 依赖
├── run.py                      # 启动入口
└── README.md                   # 本文件
```

---

## 📚 文档

- [快速启动指南](docs/快速启动指南.md) - 详细安装和配置
- [课堂主题功能说明](docs/课堂主题功能说明.md) - 智能专业词汇生成
- [故障排查指南](docs/故障排查指南.md) - 常见问题解决方案
- [日志系统说明](docs/日志系统说明.md) - 日志查看和分析
- [项目架构](PROJECT_STRUCTURE.md) - 完整技术文档

---

## 🛠️ 工具脚本

### 日志查看器
实时查看系统日志：
```bash
python view_logs.py
```

### 缓存清理
清理 Python 字节码缓存：
```bash
clear_cache.bat  # Windows
# 或手动删除 __pycache__ 目录
```

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源协议。

---

## 🙏 致谢

- [NVIDIA NeMo-Speech.cpp](https://github.com/NVIDIA/NeMo-Speech.cpp) - 本地流式语音识别运行时
- [FastAPI](https://fastapi.tiangolo.com/) - 现代化 Web 框架

---

## 📧 联系方式

如有问题或建议，请提交 [Issue](https://github.com/yourusername/classaudio/issues)。

---

<p align="center">
  Made with ❤️ for better learning experience
</p>
