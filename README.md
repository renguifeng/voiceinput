# 语音输入法

基于 [FunASR](https://github.com/alibaba-damo-academy/FunASR) 的本地离线语音输入工具，通过 WebSocket 连接本地部署的 FunASR 服务，实现语音实时识别并输入到任意应用。

## 功能

- **持续识别模式** — 按热键开始实时流式识别，再按停止。说话过程中实时显示中间结果，ASR 自动修正为准确文字
- **按住说话模式** — 按住热键实时识别，松开停止。与持续识别使用相同的流式引擎，支持长时录音
- **可配置热键** — 支持 Scroll Lock、F8-F10、Pause/Break、Insert、Ctrl(左)、Ctrl(右)
- **科技感浮窗** — 半透明置顶浮窗，圆形图标显示当前模式（LIVE/HOLD），呼吸灯/心跳动画反馈状态，可拖动，双击打开设置
- **系统托盘** — 最小化到托盘后台运行，托盘菜单可恢复窗口或退出
- **设置持久化** — 配置保存到 `settings.json`，重启自动加载
- **独立 EXE** — 支持 PyInstaller 打包为单个可执行文件，无需 Python 环境

## 依赖

- Python 3.10+
- 本地部署的 FunASR WebSocket 服务（默认 `ws://localhost:10096`）

## 安装

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 运行

```bash
venv\Scripts\python.exe voice_input.py
```

## 打包为 EXE

```bash
venv\Scripts\activate
pip install pyinstaller
pyinstaller --onefile --windowed --name "语音输入法" voice_input.py
```

生成文件在 `dist/语音输入法.exe`，连同同目录下的 `settings.json` 一起拷贝即可使用。

## 使用说明

1. 启动程序，出现设置窗口和桌面浮窗
2. 在设置窗口配置服务器地址、热键、录入模式，点击"保存设置"
3. 打开任意文本编辑器或输入框，按热键开始语音输入
4. 浮窗图标实时反馈状态（绿色=就绪，红色=录音中，橙色=识别中）
5. 关闭设置窗口后程序最小化到系统托盘继续运行
6. 双击浮窗或通过托盘菜单可恢复设置窗口

## 录入模式说明

| 模式 | 操作 | 说明 |
|------|------|------|
| 持续识别 | 按一下开始，再按一下停止 | 适合连续说话场景 |
| 按住说话 | 按住开始，松开停止 | 适合短句场景，松手即停 |

两种模式均使用 FunASR 2pass 实时流式识别，说话时实时显示文字，ASR 自动修正为准确结果。

## 文件说明

| 文件 | 说明 |
|------|------|
| `voice_input.py` | 主程序 |
| `debug_asr.py` | FunASR 调试工具，查看原始返回数据 |
| `requirements.txt` | Python 依赖列表 |
| `settings.json` | 用户配置（运行后自动生成） |
