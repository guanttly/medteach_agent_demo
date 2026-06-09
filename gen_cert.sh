#!/usr/bin/env bash
# 生成本地演示用「自签 TLS 证书」（含本机所有局域网 IP 的 SAN），用于 HTTPS 远程演示。
#
# 为什么需要 HTTPS：浏览器的「麦克风 / 语音识别（getUserMedia / SpeechRecognition）」
# 只在「安全上下文」下可用——localhost 例外，但其他机器通过 IP 访问必须走 HTTPS，
# 否则数字形象页根本拿不到麦克风权限，语音交互无法演示。
#
# 用法：
#   ./gen_cert.sh                      # 生成到 backend/certs（已存在则跳过）
#   FORCE=1 ./gen_cert.sh              # 强制重建
#   EXTRA_SAN="DNS:demo.local,IP:10.0.0.5" ./gen_cert.sh   # 追加自定义域名/IP
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
CERT_DIR="${CERT_DIR:-$ROOT/backend/certs}"
CRT="$CERT_DIR/cert.pem"
KEY="$CERT_DIR/key.pem"

mkdir -p "$CERT_DIR"

if [ -f "$CRT" ] && [ -f "$KEY" ] && [ "${FORCE:-0}" != "1" ]; then
  echo "[cert] 已存在证书：$CRT（设 FORCE=1 可强制重建）"
  exit 0
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "[cert] 未找到 openssl，请先安装：sudo apt-get install -y openssl" >&2
  exit 1
fi

# 汇集 SAN：localhost + 127.0.0.1 + 本机所有 IPv4（让局域网其他机器也能匹配证书）
SAN="DNS:localhost,IP:127.0.0.1"
if command -v hostname >/dev/null 2>&1; then
  for ip in $(hostname -I 2>/dev/null); do
    case "$ip" in
      *.*.*.*) SAN="$SAN,IP:$ip" ;;
    esac
  done
fi
[ -n "${EXTRA_SAN:-}" ] && SAN="$SAN,$EXTRA_SAN"

echo "[cert] 生成自签证书，SAN=$SAN"
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$KEY" -out "$CRT" -days 825 \
  -subj "/CN=medteach-demo" \
  -addext "subjectAltName=$SAN" >/dev/null 2>&1

chmod 600 "$KEY" 2>/dev/null || true
echo "[cert] 完成：$CRT"
echo "[cert] 首次访问浏览器会提示「不安全」，点击「高级 → 继续前往」即可（这是自签证书的正常提示）。"
