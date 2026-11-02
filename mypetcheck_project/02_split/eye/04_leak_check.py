"""
04_leak_check.py — 분할 후 누수 검사 6가지 (하나라도 0 이 아니면 분할 무효)

  1 같은 묶음 ID 가 두 쪽 이상에 있음
  2 같은 파일명이 두 쪽 이상에 있음
  3 같은 SHA-256 이 두 쪽 이상에 있음
  4 쪽이 다른 사진끼리 pHash 해밍거리 ≤ PHASH_MAX_DIST
  5 쪽이 다른 사진끼리 ① 가상 개체 키가 같음
  6 쪽이 다른 사진끼리 ④ 재촬영 의심 조건 해당
  + 고양이 교차검증 조각(cv_fold)끼리도 1·5 검사

"쪽" = 동물별 split (개: train/val/test/bridge, 고양이: train/test)
출력 : OUT_DIR/reports/leak_check.csv, leak_report.md
통과 못 하면 종료 코드 1 → 14_seal.py 가 실행되지 않음

실행: python3 04_leak_check.py
"""
import argparse
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import C, near_duplicate_pairs, out_dir  # noqa: E402


def to_date(s):
    try:
        y, m, d = (int(x) for x in str(s)[:10].split("-"))
        return date(y, m, d)
    except Exception:
        return None


def multi_side(df, col, side_col):
    """같은 값이 두 쪽 이상에 걸친 값의 개수와 사진 수."""
    g = df.groupby(col)[side_col].nunique()
    bad = g[g > 1].index
    return len(bad), int(df[col].isin(bad).sum()), list(bad[:5])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = out_dir(args.out)
    (out / "reports").mkdir(exist_ok=True)
    df = pd.read_csv(out / "manifests" / f"{C.SPLIT_VERSION}.csv", dtype=str, encoding="utf-8-sig")
    df["side"] = df["species"] + ":" + df["split"]

    results = []

    def add(no, name, n_values, n_photos, examples, enforced=True, note=""):
        results.append({"번호": no, "검사": name, "걸린 값": n_values, "걸린 사진": n_photos,
                        "판정": ("통과" if n_values == 0 else ("실패" if enforced else "참고")),
                        "예시": "; ".join(map(str, examples)), "비고": note})

    add(1, "같은 묶음 ID 가 두 쪽 이상", *multi_side(df, "group_id", "side"))
    add(2, "같은 파일명이 두 쪽 이상", *multi_side(df, "file_name", "side"))
    add(3, "같은 SHA-256 이 두 쪽 이상", *multi_side(df, "sha256", "side"))

    # 4 pHash
    n_pairs, photos, ex = 0, set(), []
    for sp, sub in df.groupby("species"):
        sub = sub.reset_index(drop=True)
        for a, b in near_duplicate_pairs(sub["phash"].tolist(), C.PHASH_MAX_DIST):
            if sub.at[a, "split"] != sub.at[b, "split"]:
                n_pairs += 1
                photos.update([sub.at[a, "item_id"], sub.at[b, "item_id"]])
                if len(ex) < 5:
                    ex.append(f"{sub.at[a,'item_id']}({sub.at[a,'split']})~{sub.at[b,'item_id']}({sub.at[b,'split']})")
    add(4, f"쪽이 다른 사진끼리 pHash ≤ {C.PHASH_MAX_DIST}", n_pairs, len(photos), ex)

    add(5, "쪽이 다른 사진끼리 ① 가상 개체 키 같음", *multi_side(df, "rule1_key", "side"))

    # 6 재촬영 의심 (① 키 단위)
    keys = df.groupby("rule1_key").agg(species=("species", "first"), breed_group=("breed_group", "first"),
                                       gender=("gender", "first"), age=("age", "first"),
                                       date=("date", "first"), sides=("side", lambda s: frozenset(s))).reset_index()
    n6, ex6, photos6 = 0, [], set()
    for _, sub in keys.groupby(["species", "breed_group", "gender"]):
        items = []
        for _, r in sub.iterrows():
            d = to_date(r["date"])
            try:
                a = int(r["age"])
            except ValueError:
                a = None
            if d is not None and a is not None:
                items.append((d, a, r["rule1_key"], r["sides"]))
        items.sort(key=lambda t: t[0])
        for i in range(len(items)):
            di, ai, ki, si = items[i]
            for j in range(i + 1, len(items)):
                dj, aj, kj, sj = items[j]
                if (dj - di).days > C.RULE4_MAX_DAYS:
                    break
                if abs(aj - ai) <= C.RULE4_MAX_AGE_DIFF and si != sj:
                    n6 += 1
                    photos6.update([ki, kj])
                    if len(ex6) < 5:
                        ex6.append(f"{ki} ~ {kj}")
    add(6, "쪽이 다른 사진끼리 ④ 재촬영 의심 조건", n6, len(photos6), ex6,
        enforced=C.RULE4_ENABLED,
        note="" if C.RULE4_ENABLED else "규칙 ④ 미사용 (팀 결정) → 참고로만 기록")

    # 고양이 교차검증 조각끼리
    cat_tr = df[(df.species == "고양이") & (df.split == "train")]
    if len(cat_tr):
        add("7a", "고양이 cv 조각끼리 같은 묶음 ID", *multi_side(cat_tr, "group_id", "cv_fold"))
        add("7b", "고양이 cv 조각끼리 ① 키 같음", *multi_side(cat_tr, "rule1_key", "cv_fold"))

    res = pd.DataFrame(results)
    res.to_csv(out / "reports" / "leak_check.csv", index=False, encoding="utf-8-sig")
    failed = res[res["판정"] == "실패"]
    lines = [f"# 누수 검사 ({C.SPLIT_VERSION})", "", "| # | 검사 | 걸린 값 | 걸린 사진 | 판정 |", "|---|---|---:|---:|---|"]
    for r in results:
        lines.append(f"| {r['번호']} | {r['검사']} | {r['걸린 값']:,} | {r['걸린 사진']:,} | {r['판정']} |")
    lines += ["", f"**결과: {'통과 — 분할 유효' if failed.empty else '실패 — 분할 무효 (봉인 금지)'}**", "",
              "한계: 개체 ID 가 없어, 몇 주~몇 달 뒤 다시 찍은 같은 아이는 이 검사로도 완벽히 잡지 못할 수 있음 → '확인할 수 있는 범위에서 0'으로 보고"]
    (out / "reports" / "leak_report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    if not failed.empty:
        sys.exit(1)
    (out / "reports" / f"{C.SPLIT_VERSION}.LEAK_PASS").write_text("ok", encoding="utf-8")


if __name__ == "__main__":
    main()
