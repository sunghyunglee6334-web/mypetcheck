"""common.py — Split 프로그램 공통 함수 (zip 읽기, pHash, 묶음 합치기, 유사 사진 찾기)"""
import hashlib
import io
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import split_config as C  # noqa: E402


# ─────────────────────────────────────────────
# zip
# ─────────────────────────────────────────────
def decode_name(info: zipfile.ZipInfo) -> str:
    """zip 안 파일명(CP949)을 한글로."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def find_zips(dirs):
    zips = []
    for d in dirs:
        p = Path(d)
        if p.is_file() and p.suffix.lower() == ".zip":
            zips.append(p)
        elif p.is_dir():
            zips += sorted(p.rglob("*.zip"))
    if not zips:
        sys.exit(f"[중단] 라벨 zip 을 찾지 못함: {dirs}\n  split_config.py 의 AIHUB_EYE_DIR 을 확인하세요.")
    return zips


def load_json_bytes(raw: bytes):
    for enc in ("utf-8-sig", "cp949"):
        try:
            return json.loads(raw.decode(enc))
        except Exception:
            continue
    return None


# ─────────────────────────────────────────────
# 해시
# ─────────────────────────────────────────────
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


_DCT = None


def _dct_matrix(n=32):
    global _DCT
    if _DCT is None:
        k = np.arange(n)[:, None]
        i = np.arange(n)[None, :]
        m = np.cos(np.pi * (2 * i + 1) * k / (2 * n))
        m[0] *= 1 / np.sqrt(2)
        _DCT = m * np.sqrt(2 / n)
    return _DCT


def phash(img: Image.Image) -> str:
    """표준 pHash (32x32 회색 → DCT → 왼쪽 위 8x8 → 중앙값 기준 64비트). 16자리 hex."""
    g = np.asarray(img.convert("L").resize((32, 32), Image.LANCZOS), dtype=np.float64)
    d = _dct_matrix() @ g @ _dct_matrix().T
    low = d[:8, :8].flatten()
    bits = low > np.median(low)
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return f"{v:016x}"


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


# ─────────────────────────────────────────────
# 묶음 합치기 (union-find)
# ─────────────────────────────────────────────
class UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.p[max(ra, rb)] = min(ra, rb)
        return True


# ─────────────────────────────────────────────
# 유사 사진 찾기 (pHash 해밍거리 ≤ T 인 쌍 전부)
#   64비트를 T+1 조각으로 나누면, 거리 ≤ T 인 두 해시는 적어도 한 조각이 완전히 같다 (비둘기집 원리).
#   → 같은 조각끼리만 비교하므로 11만 장 전체 쌍(60억 개)을 다 비교하지 않아도 빠짐없이 찾는다.
# ─────────────────────────────────────────────
def near_duplicate_pairs(hashes_hex, max_dist):
    vals = [int(h, 16) for h in hashes_hex]
    n_blocks = max_dist + 1
    widths = [64 // n_blocks + (1 if i < 64 % n_blocks else 0) for i in range(n_blocks)]
    pairs = set()
    shift = 64
    for w in widths:
        shift -= w
        mask = (1 << w) - 1
        buckets = defaultdict(list)
        for idx, v in enumerate(vals):
            buckets[(v >> shift) & mask].append(idx)
        for members in buckets.values():
            if len(members) < 2:
                continue
            for i in range(len(members)):
                vi = vals[members[i]]
                for j in range(i + 1, len(members)):
                    a, b = members[i], members[j]
                    key = (a, b) if a < b else (b, a)
                    if key in pairs:
                        continue
                    if hamming(vi, vals[b]) <= max_dist:
                        pairs.add(key)
    return pairs


def out_dir(args_out=None) -> Path:
    p = Path(args_out) if args_out else Path(C.OUT_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p
