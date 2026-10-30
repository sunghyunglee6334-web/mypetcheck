"""
02_json_inspect.py — AI Hub 반려동물 안구 라벨 JSON 확인·정밀분석 (zip을 풀지 않고 읽음)

두 가지 모드
  show  : JSON 파일을 키·값 그대로 보기 (몇 개만, 또는 파일 이름으로 찾아서)
  audit : 사용 범위(스마트폰 + 일반카메라) 전체를 돌며 「JSON 정밀분석」 숫자를 다시 계산해 CSV·요약 파일로 저장

사용 예 (WSL)
  # 라벨 zip 폴더 (TL1.zip, TL2.zip, VL.zip 이 들어 있는 폴더들을 모두 지정)
  L1="/mnt/c/Users/<사용자>/Downloads/153.반려동물 안구질환 데이터/01.데이터/1.Training/라벨링데이터"
  L2="/mnt/c/Users/<사용자>/Downloads/153.반려동물 안구질환 데이터/01.데이터/2.Validation/라벨링데이터"

  # 1) 범위 안 JSON 3개를 키·값 그대로 보기
  python3 02_json_inspect.py show --zip-dir "$L1" "$L2" -n 3

  # 2) 특정 파일 보기 (파일명 일부만 써도 됨)
  python3 02_json_inspect.py show --zip-dir "$L1" "$L2" --name D0_1234

  # 3) 전체 정밀분석 → 결과 저장
  python3 02_json_inspect.py audit --zip-dir "$L1" "$L2" \
      --out ~/mypetcheck/01_data_analysis/eye/json_inspect

원칙
  - 원본 zip은 읽기만 한다 (풀거나 고치지 않음)
  - 결과물에는 숫자·파일명만 저장 (사진 없음). Git·외부에 올리지 않는다
"""

import argparse
import collections
import csv
import json
import os
import sys
import zipfile
from pathlib import Path

USE_DEVICES = {"스마트폰", "일반카메라"}          # 최종 사용 범위 (10/30 결정)
EXPECTED_META = ["file_name", "date_time", "device", "gender", "age", "breed",
                 "medical_type", "width_height", "eye_position", "image_resolution"]
EXPECTED_LABEL = ["label_filename", "label_category_id", "label_path", "label_deleted",
                  "label_bbox", "label_disease_nm",
                  "label_disease_lv_1", "label_disease_lv_2", "label_disease_lv_3"]


# ─────────────────────────────────────────────
# zip 읽기
# ─────────────────────────────────────────────
def decode_name(info: zipfile.ZipInfo) -> str:
    """zip 안 파일명은 CP949 로 저장돼 있음 → 한글로 바꿔 줌."""
    if info.flag_bits & 0x800:          # 이미 UTF-8 로 표시된 파일
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
        sys.exit(f"[오류] zip 파일을 찾지 못함: {dirs}")
    return zips


def iter_json(zips):
    """(zip 이름, zip 안 경로, JSON 내용 또는 None, 오류문, 같은 폴더 이미지 이름 집합) 를 차례로 돌려줌."""
    for zp in zips:
        with zipfile.ZipFile(zp) as zf:
            infos = [(decode_name(i), i) for i in zf.infolist() if not i.is_dir()]
            images = {n.rsplit("/", 1)[-1] for n, _ in infos
                      if n.lower().endswith((".jpg", ".jpeg", ".png"))}
            for name, info in infos:
                if not name.lower().endswith(".json"):
                    continue
                raw = zf.read(info)
                data, err = None, ""
                for enc in ("utf-8-sig", "cp949"):
                    try:
                        data = json.loads(raw.decode(enc))
                        break
                    except Exception as e:          # 읽기 실패는 기록만 하고 계속
                        err = f"{type(e).__name__}: {e}"
                yield zp.name, name, data, ("" if data is not None else err), images


def in_scope(data) -> bool:
    try:
        return data["images"]["meta"]["device"] in USE_DEVICES
    except (KeyError, TypeError):
        return False


# ─────────────────────────────────────────────
# show 모드
# ─────────────────────────────────────────────
def print_kv(obj, indent=0):
    pad = "  " * indent
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict):
                print(f"{pad}{k}:")
                print_kv(v, indent + 1)
            else:
                print(f"{pad}{k} = {v!r}   ({type(v).__name__})")
    else:
        print(f"{pad}{obj!r}")


def cmd_show(args):
    shown = 0
    for zname, path, data, err, _ in iter_json(find_zips(args.zip_dir)):
        if args.name and args.name not in path:
            continue
        if not args.name and not args.all_devices and not in_scope(data):
            continue
        print("=" * 70)
        print(f"[{zname}] {path}")
        if data is None:
            print(f"  읽기 오류: {err}")
        else:
            print_kv(data, 1)
        shown += 1
        if shown >= args.n:
            break
    if shown == 0:
        print("조건에 맞는 JSON 이 없음")


# ─────────────────────────────────────────────
# audit 모드
# ─────────────────────────────────────────────
def to_num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.strip())
        except ValueError:
            return None
    return None


def bbox_check(bbox, wh):
    """박스 문제를 문자열 목록으로 돌려줌. 고치지 않고 표시만 한다."""
    issues = []
    if not isinstance(bbox, list) or len(bbox) != 4:
        return ["형식오류"], None
    if any(isinstance(v, str) for v in bbox):
        issues.append("문자열")
    nums = [to_num(v) for v in bbox]
    if any(v is None for v in nums):
        return issues + ["숫자변환불가"], None
    x1, y1, x2, y2 = nums
    if x2 < x1:
        issues.append("x뒤집힘")
    if y2 < y1:
        issues.append("y뒤집힘")
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    if (x2 - x1) < 1 or (y2 - y1) < 1:
        issues.append("크기0")
    area_ratio = None
    if isinstance(wh, list) and len(wh) == 2 and all(to_num(v) for v in wh):
        w, h = to_num(wh[0]), to_num(wh[1])
        if x1 < 0 or y1 < 0 or x2 > w or y2 > h:
            issues.append("사진밖")
        if x1 <= 0 and y1 <= 0 and x2 >= w and y2 >= h:
            issues.append("사진전체")
        area_ratio = (max(0, min(x2, w) - max(x1, 0)) * max(0, min(y2, h) - max(y1, 0))) / (w * h)
    return issues, area_ratio


def species_of(meta, path):
    fn = str(meta.get("file_name", ""))
    if fn.startswith("D"):
        return "개"
    if fn.startswith("C"):
        return "고양이"
    return "개" if "/개/" in path else ("고양이" if "/고양이/" in path else "?")


def cmd_audit(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    n_total = n_scope = 0
    read_errors = []
    keysets = collections.Counter()
    # 필드별 (동물, 필드) → 타입 카운트 / 값 카운트
    types = collections.defaultdict(collections.Counter)
    values = collections.defaultdict(collections.Counter)
    bbox_issue = collections.defaultdict(collections.Counter)
    areas = collections.defaultdict(list)
    lv = collections.defaultdict(collections.Counter)       # (동물) → 일치/불일치 종류
    lv_change = collections.defaultdict(collections.Counter)
    medtype = collections.Counter()
    filename_seen = collections.Counter()
    rows = []                                                # 사진 1장 = 1행

    for zname, path, data, err, images in iter_json(find_zips(args.zip_dir)):
        n_total += 1
        if data is None:
            read_errors.append((zname, path, err))
            continue
        if not in_scope(data):
            continue
        n_scope += 1
        meta = data.get("images", {}).get("meta", {})
        label = data.get("label", {})
        sp = species_of(meta, path)

        keysets[(tuple(sorted(meta.keys())), tuple(sorted(label.keys())))] += 1
        for k in EXPECTED_META:
            v = meta.get(k, "<없음>")
            types[(sp, "meta." + k)][type(v).__name__] += 1
            if k in ("width_height", "image_resolution"):
                values[(sp, "meta." + k)][str(v)] += 1
            elif k not in ("file_name", "date_time"):
                values[(sp, "meta." + k)][str(v)] += 1
        for k in EXPECTED_LABEL:
            v = label.get(k, "<없음>")
            types[(sp, "label." + k)][type(v).__name__] += 1
            if k in ("label_category_id", "label_deleted", "label_disease_nm",
                     "label_disease_lv_1", "label_disease_lv_2", "label_disease_lv_3"):
                values[(sp, "label." + k)][str(v)] += 1

        issues, ar = bbox_check(label.get("label_bbox"), meta.get("width_height"))
        for i in issues:
            bbox_issue[sp][i] += 1
        if ar is not None:
            areas[sp].append(ar)

        l1, l2, l3 = (label.get("label_disease_lv_1"), label.get("label_disease_lv_2"),
                      label.get("label_disease_lv_3"))
        lv[sp]["lv2==lv3"] += int(l2 == l3)
        lv[sp]["lv1==lv3"] += int(l1 == l3)
        lv[sp]["전체"] += 1
        if l1 != l3:
            lv_change[sp][f"{label.get('label_disease_nm')} {l1}→{l3}"] += 1

        medtype[(sp, meta.get("device"), "무" if l3 == "무" else "질환", str(meta.get("medical_type")))] += 1

        lfn = str(label.get("label_filename", ""))
        has_ext = lfn.lower().endswith((".jpg", ".jpeg", ".png"))
        crop_exists = lfn in images
        filename_seen[str(meta.get("file_name"))] += 1

        folder_parts = path.split("/")
        rows.append({
            "zip": zname, "json_path": path, "동물": sp,
            "file_name": meta.get("file_name"), "date": str(meta.get("date_time", ""))[:10],
            "device": meta.get("device"), "gender": meta.get("gender"), "age": meta.get("age"),
            "breed": meta.get("breed"), "medical_type": meta.get("medical_type"),
            "eye_position": meta.get("eye_position"),
            "width_height": meta.get("width_height"),
            "질환": label.get("label_disease_nm"), "lv1": l1, "lv2": l2, "lv3": l3,
            "folder_disease": folder_parts[-3] if len(folder_parts) >= 3 else "",
            "folder_stage": folder_parts[-2] if len(folder_parts) >= 2 else "",
            "label_filename": lfn, "확장자있음": has_ext, "crop있음": crop_exists,
            "bbox": label.get("label_bbox"), "bbox_문제": "|".join(issues),
            "bbox_면적비": "" if ar is None else round(ar, 5),
        })

    # ── 저장 ──
    with open(out / "json_rows.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["empty"])
        w.writeheader()
        w.writerows(rows)

    with open(out / "field_types_values.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["동물", "필드", "구분", "값", "건수"])
        for (sp, fld), c in sorted(types.items()):
            for t, n in c.most_common():
                w.writerow([sp, fld, "타입", t, n])
        for (sp, fld), c in sorted(values.items()):
            for v, n in c.most_common(50):        # 값 종류가 많으면 상위 50개만
                w.writerow([sp, fld, "값", v, n])

    with open(out / "read_errors.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["zip", "json_path", "오류"])
        w.writerows(read_errors)

    def med(xs):
        xs = sorted(xs)
        return xs[len(xs) // 2] if xs else float("nan")

    def pct(xs, q):
        xs = sorted(xs)
        return xs[int(q * (len(xs) - 1))] if xs else float("nan")

    dup_files = sum(1 for n in filename_seen.values() if n > 1)
    folder_mismatch = sum(1 for r in rows if r["folder_stage"] != r["lv3"])
    disease_mismatch = sum(1 for r in rows if r["folder_disease"] != r["질환"])

    lines = [
        "# JSON 정밀분석 재계산 결과 (02_json_inspect.py audit)", "",
        f"- 읽은 JSON: {n_total:,} · 읽기 오류: {len(read_errors):,} · 사용 범위(스마트폰+일반카메라): {n_scope:,}",
        f"- 키 구성 종류: {len(keysets)} (1이면 모든 JSON 구조 동일)",
        f"- 같은 file_name 이 2번 이상: {dup_files:,}",
        f"- 폴더 단계명 ≠ lv_3: {folder_mismatch:,} · 폴더 질환명 ≠ label_disease_nm: {disease_mismatch:,}",
        f"- 확장자 없는 label_filename: {sum(1 for r in rows if not r['확장자있음']):,} · crop 이미지 없음: {sum(1 for r in rows if not r['crop있음']):,}",
        "",
    ]
    for sp in sorted(lv):
        t = lv[sp]["전체"]
        lines += [f"## {sp}",
                  f"- 장수: {t:,}",
                  f"- lv_2 = lv_3: {lv[sp]['lv2==lv3']:,} / {t:,}",
                  f"- 수의사1 ≠ 확정: {t - lv[sp]['lv1==lv3']:,} ({(t - lv[sp]['lv1==lv3']) / t:.1%})",
                  "- 박스 문제: " + (", ".join(f"{k} {v:,}" for k, v in bbox_issue[sp].most_common()) or "없음"),
                  f"- 박스 면적비 p10 / 중앙값 / p90: {pct(areas[sp], .1):.1%} / {med(areas[sp]):.1%} / {pct(areas[sp], .9):.1%}",
                  "- 수의사1 → 확정 변경 상위: " + ", ".join(f"{k} {v}" for k, v in lv_change[sp].most_common(6)),
                  ""]
    lines += ["## medical_type × 기기 × 정상/질환", "", "| 동물 | 기기 | 정상/질환 | medical_type | 건수 |", "|---|---|---|---|---:|"]
    for (sp, dev, st, mt), n in sorted(medtype.items()):
        lines.append(f"| {sp} | {dev} | {st} | {mt} | {n:,} |")
    (out / "audit_summary.md").write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines))
    print(f"\n저장 위치: {out}")
    print("  json_rows.csv (사진 1장 = 1행, 모든 키·값) / field_types_values.csv / read_errors.csv / audit_summary.md")


def main():
    ap = argparse.ArgumentParser(description="AI Hub 안구 라벨 JSON 확인·정밀분석")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("show", help="JSON 키·값 그대로 보기")
    s.add_argument("--zip-dir", nargs="+", required=True, help="라벨 zip 이 있는 폴더(여러 개 가능) 또는 zip 파일")
    s.add_argument("-n", type=int, default=3, help="보여 줄 개수 (기본 3)")
    s.add_argument("--name", help="파일 경로에 이 글자가 들어간 JSON 만")
    s.add_argument("--all-devices", action="store_true", help="검안경 등 범위 밖 기기도 보기")
    s.set_defaults(func=cmd_show)

    a = sub.add_parser("audit", help="사용 범위 전체 정밀분석")
    a.add_argument("--zip-dir", nargs="+", required=True)
    a.add_argument("--out", required=True, help="결과 저장 폴더 (예: ~/mypetcheck/01_data_analysis/eye/json_inspect)")
    a.set_defaults(func=cmd_audit)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
