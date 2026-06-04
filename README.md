# 语音输入法

基于 [FunASR](https://github.com/alibaba-damo-academy/FunASR) 的本地离线语音输入工具，通过 WebSocket 连接本地部署的 FunASR 服务，实现语音实时识别并输入到任意应用。

## 功能

- **持续识别模式** — 按热键开始实时流式识别，再按停止，说话过程中实时显示中间结果并自动修正
- **按住说话模式** — 按住热键录音，松开后一次性识别并输入
- **可配置热键** — 支持 Scroll Lock、F8-F10、Pause、Insert、Ctrl(左/右)
- **科技感浮窗** — 半透明置顶浮窗，显示当前模式和状态，带呼吸灯/心跳动画效果
- **系统托盘** — 最小化到托盘后台运行
- **设置持久化** — 配置保存到 `settings.json`，重启自动加载

## 依赖

- Python 3.10+
- 本地部署的 FunASR WebSocket 服务（默认 `ws://localhost:10096`）

## 安装

```bash
python -m venv venv
venv\Scripts\activate
pip install websockets sounddevice numpy pynput pystray Pillow
```

## 运行

```bash
venv\Scripts\python.exe voice_input.py
```

## 打包为 EXE

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "语音输入法" voice_input.py
```

生成文件在 `dist/语音输入法.exe`，可独立运行，无需 Python 环境。

## 使用

1. 启动程序后出现设置窗口和桌面浮窗
2. 在设置窗口配置服务器地址、热键、录入模式，点击"保存设置"
3. 打开任意文本编辑器，按热键开始语音输入
4. 关闭设置窗口后程序在系统托盘继续运行

## 文件说明

| 文件 | 说明 |
|------|------|
| `voice_input.py` | 主程序 |
| `debug_asr.py` | FunASR 调试工具，查看原始返回数据 |
| `settings.json` | 用户配置（自动生成） |
