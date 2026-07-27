# 🎙️ VoiceInput — 本地离线语音输入法

> 基于 [FunASR](https://github.com/alibaba-damo-academy/FunASR) 的 Windows 语音输入工具。声音不上云，识别不花钱，打字不用手。

## ✨ 特性

- 🔒 **完全离线** — 语音数据不出本机，隐私零泄露
- ⚡ **实时流式识别** — 说话即出字，FunASR 2pass 自动修正
- 🎯 **全局输入** — 任意应用、任意输入框，识别后自动粘贴
- 🎨 **科技感浮窗** — 半透明置顶，呼吸灯反馈，可拖动
- ⌨️ **双模式** — 持续识别 / 按住说话
- 📦 **单文件 EXE** — PyInstaller 打包，无需 Python 环境

## 📸 截图

> _浮窗、设置窗口、字幕条截图（待补充）_

## 🚀 快速开始

### 前置条件

- Windows 10/11
- Python 3.10+（开发者）
- 本地部署的 [FunASR](https://github.com/alibaba-damo-academy/FunASR) WebSocket 服务

### 部署 FunASR 服务（Docker 一键启动）

```bash
docker run -d --name funasr \
  -p 10096:10096 \
  --gpus all \
  registry.cn-hangzhou.aliyuncs.com/funasr/funasr:runtime-sdk-online-latest \
  /bin/bash -c "cd FunASR/runtime && nohup bash run_server.sh > log.txt 2>&1"
```

没有 GPU？去掉 `--gpus all`，CPU 也能跑（稍慢）。

### 安装 & 运行

```bash
git clone https://github.com/renguifeng/voiceinput.git
cd voiceinput
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python voice_input.py
```

### 打包为 EXE

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "VoiceInput" voice_input.py
# 生成文件在 dist/VoiceInput.exe
```

## ⚙️ 配置

首次运行后自动生成 `settings.json`：

```json
{
  "server_url": "ws://localhost:10096",
  "hotkey": "ctrl_r",
  "mode": "continuous",
  "paste_delay": 20
}
```

| 字段 | 说明 | 可选值 |
|------|------|--------|
| `server_url` | FunASR WebSocket 地址 | 任意 ws:// 地址 |
| `hotkey` | 触发热键 | Scroll Lock / F8-F10 / Pause / Insert / Ctrl(左/右) |
| `mode` | 录入模式 | `continuous` / `ptt` |
| `paste_delay` | 粘贴延时(ms) | 0-200 |

## 🎬 使用方式

1. 启动程序 → 出现设置窗口和桌面浮窗
2. 配置好服务器地址和热键，保存
3. 打开任意输入框，**按热键开始说话**
4. 浮窗实时反馈状态（🟢就绪 / 🔴录音中 / 🟡识别中）
5. 关闭窗口自动最小化到托盘，后台继续运行

## 📁 项目结构

```
voiceinput/
├── voice_input.py   # 主程序入口、GUI、托盘
├── engine.py        # 语音引擎：录音、WebSocket、输入
├── widget.py        # 浮窗 UI、字幕条
├── constants.py     # 常量与配置路径
├── debug_asr.py     # FunASR 调试工具
└── requirements.txt
```

## 🛠️ 技术栈

- [FunASR](https://github.com/alibaba-damo-academy/FunASR) — 阿里达摩院开源语音识别
- [sounddevice](https://python-sounddevice.readthedocs.io/) — 音频采集
- [pynput](https://github.com/moses-palmer/pynput) — 全局热键 & 键盘模拟
- [pystray](https://github.com/moses-palmer/pystray) — 系统托盘
- [Pillow](https://python-pillow.org/) — 图标绘制

## 📋 使用场景

- 📝 长文档写作、会议记录
- 💬 快速回复消息
- 🔒 对隐私敏感的场景（医疗、法律、政务）
- ♿ 打字不便时的辅助输入

## 🤝 贡献

欢迎 Issue 和 PR。功能建议、Bug 反馈、UI 改进都可以。

## 📜 License

[MIT](LICENSE) — 随便用，不限制。

## ☕ 支持作者

如果这个工具对你有帮助：

- GitHub ⭐ Star 一下
- 分享给需要的朋友

---

**声音不上云，打字不用手。** 🎙️
