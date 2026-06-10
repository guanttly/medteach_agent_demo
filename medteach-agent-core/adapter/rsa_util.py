"""纯 Python RSA（PKCS#1 v1.5）加密工具。

教学平台登录要求：用 `GET /auth-server/open/getKeys` 返回的 base64 DER 公钥
（X.509 SubjectPublicKeyInfo，RSA-1024）对密码做 PKCS#1 v1.5 加密后再 base64。
等价于前端 jsencrypt 的行为。

这里用纯标准库实现，避免引入 cryptography / pycryptodome 依赖，
保证 medteach-agent-core 可在任意 Python 3 环境（含系统 python3）直接运行。
"""
from __future__ import annotations

import base64
import secrets


def _read_len(data: bytes, i: int) -> tuple[int, int]:
    """读取 DER 长度字段，返回 (长度, 新游标)。"""
    b = data[i]
    i += 1
    if b < 0x80:
        return b, i
    num_bytes = b & 0x7F
    length = int.from_bytes(data[i : i + num_bytes], "big")
    return length, i + num_bytes


def parse_rsa_public_key(der: bytes) -> tuple[int, int]:
    """从 X.509 SubjectPublicKeyInfo DER 解析出 (modulus n, exponent e)。"""
    i = 0
    if der[i] != 0x30:  # 外层 SEQUENCE
        raise ValueError("无效公钥：缺少外层 SEQUENCE")
    i += 1
    _, i = _read_len(der, i)
    if der[i] != 0x30:  # AlgorithmIdentifier SEQUENCE（跳过）
        raise ValueError("无效公钥：缺少 AlgorithmIdentifier")
    i += 1
    alg_len, i = _read_len(der, i)
    i += alg_len
    if der[i] != 0x03:  # BIT STRING
        raise ValueError("无效公钥：缺少 BIT STRING")
    i += 1
    _, i = _read_len(der, i)
    if der[i] != 0x00:  # unused bits 计数
        raise ValueError("无效公钥：BIT STRING unused bits 异常")
    i += 1
    if der[i] != 0x30:  # 内层 RSAPublicKey SEQUENCE
        raise ValueError("无效公钥：缺少 RSAPublicKey SEQUENCE")
    i += 1
    _, i = _read_len(der, i)
    if der[i] != 0x02:  # modulus INTEGER
        raise ValueError("无效公钥：缺少 modulus")
    i += 1
    m_len, i = _read_len(der, i)
    modulus = int.from_bytes(der[i : i + m_len], "big")
    i += m_len
    if der[i] != 0x02:  # exponent INTEGER
        raise ValueError("无效公钥：缺少 exponent")
    i += 1
    e_len, i = _read_len(der, i)
    exponent = int.from_bytes(der[i : i + e_len], "big")
    return modulus, exponent


def _pkcs1v15_encrypt(message: bytes, n: int, e: int) -> bytes:
    """RSAES-PKCS1-v1_5 加密一段不超过 k-11 字节的明文。"""
    k = (n.bit_length() + 7) // 8
    if len(message) > k - 11:
        raise ValueError("明文过长，超出 RSA 密钥可加密长度")
    ps_len = k - len(message) - 3
    ps = bytearray()
    while len(ps) < ps_len:
        b = secrets.token_bytes(1)
        if b != b"\x00":  # PS 必须为非零随机字节
            ps += b
    em = b"\x00\x02" + bytes(ps) + b"\x00" + message
    c = pow(int.from_bytes(em, "big"), e, n)
    return c.to_bytes(k, "big")


def rsa_encrypt_base64(plaintext: str, public_key_b64: str) -> str:
    """用 base64 DER 公钥对明文做 PKCS#1 v1.5 加密，返回 base64 密文。"""
    der = base64.b64decode(public_key_b64)
    n, e = parse_rsa_public_key(der)
    cipher = _pkcs1v15_encrypt(plaintext.encode("utf-8"), n, e)
    return base64.b64encode(cipher).decode("ascii")
