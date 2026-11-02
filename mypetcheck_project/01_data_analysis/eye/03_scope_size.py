"""
03_scope_size.py — AI Hub 안구 데이터 중 "우리가 쓰는 것"과 "안 쓰는 것"의 용량 재기 (읽기만, 지우지 않음)

우리가 쓰는 범위: 기기 = 스마트폰 + 일반카메라 (10/30 결정)

재는 것
  1) 라벨 zip (TL1·TL2·VL): JSON + crop 사진 → 범위 안 / 범위 밖 용량
  2) 원천 zip (TS1·TS2·VS): 원본 사진 → 범위 안 / 범위 밖 용량
     (원본 사진의 기기 정보는 라벨 JSON 의 file_name 으로 연결)

실행 (WSL):
  python3 03_scope_size.py --data "/mnt/c/Users/<사용자>/Downloads/153.반려동물 안구질환 데이터"
결과: 화면 표 + scope_size.csv (이 폴더)
압축을 풀지 않고 zip 목록 정보만 읽으므로 디스크를 쓰지 않는다.
"""
import argparse
import csv
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

USE_DEVICES = {"스마트폰", "일반카메라"}


def decode_name(info):
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def load_json(raw):
    for enc in ("utf-8-sig", "cp949"):
        try:
            return json.loads(raw.decode(enc))
        except Exception:
            pass
    return None


def gb(n):
    return f"{n / 1024**3:,.1f} GB"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="153.반려동물 안구질환 데이터 폴더")
    args = ap.parse_args()
    root = Path(args.data)
    zips = sorted(root.rglob("*.zip"))
    label_zips = [z for z in zips if "라벨링데이터" in str(z)]
    source_zips = [z for z in zips if "원천데이터" in str(z)]
    if not label_zips:
        sys.exit(f"[중단] 라벨링데이터 zip 을 찾지 못함: {root}")

    # 1) 라벨 zip: 범위 안 원본 파일명 모으기 + 라벨 zip 안 용량 나누기
    in_scope_names = set()
    device_of = {}
    rows = []
    for zp in label_zips:
        print(f"[라벨 zip 읽는 중] {zp.name}", flush=True)
        with zipfile.ZipFile(zp) as zf:
            infos = [(decode_name(i), i) for i in zf.infolist() if not i.is_dir()]
            folder_device = {}
            for name, info in infos:
                if name.lower().endswith(".json"):
                    d = load_json(zf.read(info))
                    meta = (d or {}).get("images", {}).get("meta", {})
                    dev = meta.get("device", "?")
                    fn = str(meta.get("file_name", ""))
                    lfn = str((d or {}).get("label", {}).get("label_filename", ""))
                    folder = name.rsplit("/", 1)[0]
                    folder_device[f"{folder}/{lfn}"] = dev
                    folder_device[name] = dev
                    device_of[fn] = dev
                    if dev in USE_DEVICES:
                        in_scope_names.add(fn)
            size = defaultdict(int)
            count = defaultdict(int)
            for name, info in infos:
                dev = folder_device.get(name, "?")
                key = "범위 안" if dev in USE_DEVICES else "범위 밖"
                size[key] += info.compress_size
                count[key] += 1
            for k in ("범위 안", "범위 밖"):
                rows.append(["라벨", zp.name, k, count[k], size[k]])
            rows.append(["라벨", zp.name, "zip 전체", len(infos), zp.stat().st_size])

    # 2) 원천 zip: 원본 파일명으로 범위 판단
    for zp in source_zips:
        print(f"[원천 zip 목록 읽는 중] {zp.name}", flush=True)
        size = defaultdict(int)
        count = defaultdict(int)
        with zipfile.ZipFile(zp) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                base = decode_name(info).rsplit("/", 1)[-1]
                if base in in_scope_names:
                    k = "범위 안"
                elif base in device_of:
                    k = "범위 밖"
                else:
                    k = "라벨 없음"
                size[k] += info.compress_size
                count[k] += 1
        for k in ("범위 안", "범위 밖", "라벨 없음"):
            if count[k]:
                rows.append(["원천", zp.name, k, count[k], size[k]])
        rows.append(["원천", zp.name, "zip 전체", sum(count.values()), zp.stat().st_size])

    out = Path(__file__).resolve().parent / "scope_size.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["종류", "zip", "구분", "파일 수", "용량(byte)"])
        w.writerows(rows)

    print("\n| 종류 | zip | 구분 | 파일 수 | 용량 |\n|---|---|---|---:|---:|")
    tot = defaultdict(int)
    for kind, z, k, c, s in rows:
        print(f"| {kind} | {z} | {k} | {c:,} | {gb(s)} |")
        if k != "zip 전체":
            tot[(kind, k)] += s
    print("\n합계")
    for (kind, k), s in sorted(tot.items()):
        print(f"- {kind} {k}: {gb(s)}")
    print(f"\n범위 안 원본 파일명 {len(in_scope_names):,}개 (예상 112,473)")
    print(f"저장: {out}\n※ 이 스크립트는 아무것도 지우지 않음")


if __name__ == "__main__":
    main()
