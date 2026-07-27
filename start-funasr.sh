#!/usr/bin/env bash
# 一键启动 FunASR 实时语音听写服务
# 用法: ./start-funasr.sh
set -e

IMAGE="registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-online-cpu-0.1.13"
CONTAINER="funasr-server"
MODEL_DIR="./funasr-models"

echo "🎙️  FunASR 一键部署脚本"
echo "========================"

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ 未检测到 Docker，正在安装..."
    curl -O https://isv-data.oss-cn-hangzhou.aliyuncs.com/ics/MaaS/ASR/shell/install_docker.sh
    sudo bash install_docker.sh
fi

# 创建模型目录
mkdir -p "$MODEL_DIR"

# 拉取镜像
echo "📦 拉取 FunASR 镜像（约 2GB，首次需要几分钟）..."
docker pull "$IMAGE"

# 启动服务
echo "🚀 启动 FunASR 服务..."
docker run -d --name "$CONTAINER" \
    -p 10096:10095 \
    --privileged=true \
    -v "$PWD/$MODEL_DIR:/workspace/models" \
    "$IMAGE" \
    /bin/bash -c "
    cd FunASR/runtime &&
    nohup bash run_server_2pass.sh \
        --download-model-dir /workspace/models \
        --vad-dir damo/speech_fsmn_vad_zh-cn-16k-common-onnx \
        --model-dir damo/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-onnx \
        --online-model-dir damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online-onnx \
        --punc-dir damo/punc_ct-transformer_zh-cn-common-vad_realtime-vocab272727-onnx \
        --lm-dir damo/speech_ngram_lm_zh-cn-ai-wesp-fst \
        --itn-dir thuduj12/fst_itn_zh \
        --certfile 0 > log.txt 2>&1 &
    tail -f log.txt
    "

echo ""
echo "✅ FunASR 服务已启动！"
echo "   地址: ws://localhost:10096"
echo "   日志: docker logs -f $CONTAINER"
echo "   停止: docker stop $CONTAINER"
echo "   重启: docker restart $CONTAINER"
echo ""
echo "首次启动会自动下载模型（约 1.5GB），请耐心等待。"
echo "下载完成后日志中出现 'FunASR server started' 即可使用。"
