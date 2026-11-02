"""
01_build_index.py — 라벨 zip 에서 사용 범위 사진 목록 만들기 + crop 256px 캐시 + SHA-256·pHash

입력 : 라벨 zip (풀지 않고 읽기만)
출력 : OUT_DIR/manifests/eye_items.csv   (사진 1장 = 1행)
       OUT_DIR/manifests/excluded.csv    (분할 전에 정한 규칙으로 뺀 사진과 이유)
       CACHE_DIR/<개|고양이>/<파일명>.jpg  (긴 변 256px)

실행 (WSL):  python3 01_build_index.py
옵션     :  --zip-dir 폴더…  --out 폴더  --cache 폴더  --workers 8
"""
import argparse
import csv
import io
import os
import sys
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import C, decode_name, find_zips, load_json_bytes, sha256_bytes, phash, out_dir  # noqa: E402

FIELDS = ["item_id", "species", "disease", "orig_label", "label", "device", "breed", "age", "gender",
          "date", "eye", "file_name", "zip", "crop_member", "sha256", "phash", "cache_path", "width", "height"]


def to_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def bbox_zero(bbox):
    if not isinstance(bbox, list) or len(bbox) != 4:
        return True
    n = [to_num(v) for v in bbox]
    if any(v is None for v in n):
        return True
    return abs(n[2] - n[0]) < 1 or abs(n[3] - n[1]) < 1


def process(task):
    """작업자 프로세스: crop 바이트 → SHA-256, pHash, 256px 캐시 저장."""
    raw, cache_path = task
    img = Image.open(io.BytesIO(raw))
    img.load()
    img = img.convert("RGB")
    w, h = img.size
    ph = phash(img)
    if not os.path.exists(cache_path):
        small = img.copy()
        small.thumbnail((C.CACHE_LONG_SIDE, C.CACHE_LONG_SIDE), Image.LANCZOS)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        tmp = cache_path + ".tmp"
        small.save(tmp, "JPEG", quality=95)
        os.replace(tmp, cache_path)
    return sha256_bytes(raw), ph, w, h


def flush(pool, pending, rows):
    """모아 둔 crop 을 병렬 처리하고 비운다."""
    if not pending:
        return
    tasks = [(raw, r["cache_path"]) for r, raw in pending]
    for (row, _), res in zip(pending, pool.map(process, tasks, chunksize=16)):
        row["sha256"], row["phash"], row["width"], row["height"] = res
        rows.append(row)
    pending.clear()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip-dir", nargs="+", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--cache", default=str(C.CACHE_DIR))
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    args = ap.parse_args()

    out = out_dir(args.out) / "manifests"
    out.mkdir(parents=True, exist_ok=True)
    cache = Path(args.cache)

    rows, excluded, n_json, n_scope = [], [], 0, 0
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for zp in find_zips(args.zip_dir or C.label_zip_dirs()):
            print(f"[읽는 중] {zp.name}", flush=True)
            with zipfile.ZipFile(zp) as zf:
                members = {decode_name(i): i for i in zf.infolist() if not i.is_dir()}
                pending = []
                for name, info in members.items():
                    if not name.lower().endswith(".json"):
                        continue
                    n_json += 1
                    data = load_json_bytes(zf.read(info))
                    if data is None:
                        excluded.append({"zip": zp.name, "json": name, "reason": "JSON 읽기 오류"})
                        continue
                    meta = data.get("images", {}).get("meta", {})
                    label = data.get("label", {})
                    if meta.get("device") not in C.USE_DEVICES:
                        continue
                    n_scope += 1
                    fn = str(meta.get("file_name", ""))
                    lfn = str(label.get("label_filename", ""))
                    folder = name.rsplit("/", 1)[0]
                    crop_member = f"{folder}/{lfn}"
                    reason = ""
                    if not lfn.lower().endswith((".jpg", ".jpeg", ".png")):
                        reason = "label_filename 확장자 없음"
                    elif crop_member not in members:
                        reason = "crop 이미지 없음"
                    elif bbox_zero(label.get("label_bbox")):
                        reason = "박스 크기 0"
                    if reason:
                        excluded.append({"zip": zp.name, "json": name, "reason": reason})
                        continue
                    species = "개" if fn.startswith("D") else ("고양이" if fn.startswith("C") else "?")
                    lv3 = label.get("label_disease_lv_3")
                    age = to_num(meta.get("age"))
                    gender = to_num(meta.get("gender"))
                    row = {
                        "item_id": Path(fn).stem,
                        "species": species,
                        "disease": label.get("label_disease_nm"),
                        "orig_label": lv3,
                        "label": 0 if lv3 in C.NORMAL_LABELS else 1,
                        "device": meta.get("device"),
                        "breed": str(meta.get("breed", "")).strip(),
                        "age": "" if age is None else int(age),
                        "gender": "" if gender is None else int(gender),
                        "date": str(meta.get("date_time", ""))[:10],
                        "eye": meta.get("eye_position"),
                        "file_name": fn,
                        "zip": zp.name,
                        "crop_member": crop_member,
                        "cache_path": str(cache / species / (Path(fn).stem + ".jpg")),
                    }
                    pending.append((row, zf.read(members[crop_member])))
                    if len(pending) >= 512:          # 메모리 보호: 512장씩 나눠 처리
                        flush(pool, pending, rows)
                flush(pool, pending, rows)
                print(f"  누적 사용 사진 {len(rows):,}장", flush=True)

    ids = [r["item_id"] for r in rows]
    if len(ids) != len(set(ids)):
        sys.exit("[중단] item_id(원본 파일명)가 겹침 → 분할 단위 정의를 다시 확인해야 함")

    with open(out / "eye_items.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    with open(out / "excluded.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["zip", "json", "reason"])
        w.writeheader()
        w.writerows(excluded)

    print(f"\nJSON {n_json:,} · 사용 범위 {n_scope:,} · 사용 {len(rows):,} · 제외 {len(excluded):,}")
    print(f"저장: {out/'eye_items.csv'}, {out/'excluded.csv'}  /  캐시: {cache}")


if __name__ == "__main__":
    main()
