"""
02_build_groups.py — 누수 방지 묶음 만들기 (같은 아이일 수 있는 사진을 한 묶음으로)

규칙 (pet_eye_split_plan.md 3-1), 모두 "합치기만" 한다:
  ① 가상 개체 : 동물 + 품종(통일) + 나이 + 성별 + 촬영일 이 같음
  ② 같은 파일 : SHA-256 같음
  ③ 유사 사진 : pHash 해밍거리 ≤ PHASH_MAX_DIST (같은 동물 안 전체 비교)
  ④ 재촬영 의심: 동물·품종(통일)·성별 같고, 나이 차 ≤ 1, 촬영일 차 ≤ 7일

출력 : OUT_DIR/manifests/eye_groups.csv  (item_id, group_id, rule1_key)
       OUT_DIR/reports/group_report.md   (규칙별 연결 수, 묶음 크기, 가장 큰 묶음)
       OUT_DIR/reports/phash_pairs_sample.csv (유사 사진 쌍 표본 → 사람이 확인)

가장 큰 묶음이 동물별 전체의 MAX_GROUP_SHARE 를 넘으면 멈춘다 (분할이 한쪽으로 쏠림).
  → 숨기지 말고 보고서를 팀에 공유해 결정 (규칙 조정은 split_config.py 에 기록하고 다시 실행)
  → 팀이 그대로 가기로 하면 --accept-large-groups 로 실행 (보고서에 그 사실이 남음)

실행: python3 02_build_groups.py
"""
import argparse
import csv
import random
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import C, UnionFind, near_duplicate_pairs, hamming, out_dir  # noqa: E402


def breed_group(b):
    b = str(b).strip()
    return C.BREED_GROUP_MAP.get(b, b)


def to_date(s):
    try:
        y, m, d = (int(x) for x in str(s)[:10].split("-"))
        return date(y, m, d)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--accept-large-groups", action="store_true",
                    help="팀 결정으로 큰 묶음을 그대로 쓰기로 한 경우에만")
    args = ap.parse_args()
    out = out_dir(args.out)
    (out / "reports").mkdir(exist_ok=True)

    df = pd.read_csv(out / "manifests" / "eye_items.csv", dtype=str, encoding="utf-8-sig")
    df["breed_group"] = df["breed"].map(breed_group)
    df["rule1_key"] = df[["species", "breed_group", "gender", "age", "date"]].astype(str).agg("|".join, axis=1)
    n = len(df)
    uf = UnionFind(n)
    links = Counter()
    report = [f"# 누수 방지 묶음 보고서 ({C.SPLIT_VERSION})", "",
              f"- 사진 {n:,}장 (개 {(df.species=='개').sum():,} · 고양이 {(df.species=='고양이').sum():,})",
              f"- 규칙: ① 가상 개체 ② 같은 파일 ③ pHash ≤ {C.PHASH_MAX_DIST} "
              f"④ 재촬영 의심(나이 차 ≤ {C.RULE4_MAX_AGE_DIFF}, 촬영일 차 ≤ {C.RULE4_MAX_DAYS}일) "
              f"{'사용' if C.RULE4_ENABLED else '**미사용 (팀 결정)**'}", ""]

    def snapshot(label):
        roots = Counter(uf.find(i) for i in range(n))
        sizes = sorted(roots.values(), reverse=True)
        report.append(f"| {label} | {len(roots):,} | {sizes[0]:,} | {sum(1 for s in sizes if s == 1):,} |")

    report += ["## 규칙을 하나씩 더할 때 묶음 변화", "",
               "| 단계 | 묶음 수 | 가장 큰 묶음(장) | 1장짜리 묶음 |", "|---|---:|---:|---:|"]
    snapshot("시작 (사진 1장 = 1묶음)")

    # ① 가상 개체
    first = {}
    for i, k in enumerate(df["rule1_key"]):
        if k in first:
            links["①"] += uf.union(first[k], i)
        else:
            first[k] = i
    snapshot("+ ① 가상 개체")

    # ② 같은 파일
    first = {}
    for i, h in enumerate(df["sha256"]):
        if h in first:
            links["②"] += uf.union(first[h], i)
        else:
            first[h] = i
    snapshot("+ ② 같은 파일")

    # ③ 유사 사진 (동물별 전체)
    sample_rows = []
    for sp, sub in df.groupby("species"):
        idx = sub.index.tolist()
        pairs = near_duplicate_pairs(sub["phash"].tolist(), C.PHASH_MAX_DIST)
        for a, b in pairs:
            ia, ib = idx[a], idx[b]
            merged = uf.union(ia, ib)
            links["③"] += merged
            sample_rows.append((sp, df.at[ia, "item_id"], df.at[ib, "item_id"],
                                hamming(int(df.at[ia, "phash"], 16), int(df.at[ib, "phash"], 16)),
                                df.at[ia, "rule1_key"] == df.at[ib, "rule1_key"]))
        links[f"③쌍_{sp}"] = len(pairs)
    snapshot("+ ③ 유사 사진")

    # ④ 재촬영 의심 (① 키 단위로 비교 → 빠름)
    if C.RULE4_ENABLED:
        keys = df.drop_duplicates("rule1_key")[["rule1_key", "species", "breed_group", "gender", "age", "date"]]
        key_first = {}
        for i, k in zip(df.index, df["rule1_key"]):
            key_first.setdefault(k, i)
        for _, sub in keys.groupby(["species", "breed_group", "gender"]):
            items = []
            for _, r in sub.iterrows():
                d = to_date(r["date"])
                try:
                    a = int(r["age"])
                except ValueError:
                    a = None
                if d is not None and a is not None:
                    items.append((d, a, r["rule1_key"]))
            items.sort()
            for i in range(len(items)):
                di, ai, ki = items[i]
                for j in range(i + 1, len(items)):
                    dj, aj, kj = items[j]
                    if (dj - di).days > C.RULE4_MAX_DAYS:
                        break
                    if abs(aj - ai) <= C.RULE4_MAX_AGE_DIFF:
                        links["④"] += uf.union(key_first[ki], key_first[kj])
        snapshot("+ ④ 재촬영 의심")

    # 최종 묶음 ID
    roots = [uf.find(i) for i in range(n)]
    root_to_gid = {}
    for r in roots:
        if r not in root_to_gid:
            root_to_gid[r] = f"G{len(root_to_gid):06d}"
    df["group_id"] = [root_to_gid[r] for r in roots]

    report += ["", "## 규칙별 실제로 합쳐진 횟수", ""]
    for k in ["①", "②", "③", "④"]:
        report.append(f"- {k}: {links.get(k, 0):,}")
    report.append(f"- ③ 유사 사진 쌍: 개 {links.get('③쌍_개', 0):,} · 고양이 {links.get('③쌍_고양이', 0):,}")

    report += ["", "## 동물별 묶음 크기", "",
               "| 동물 | 사진 | 묶음 수 | 가장 큰 묶음 | 비율 | 상위 5개 묶음 크기 |", "|---|---:|---:|---:|---:|---|"]
    too_big = []
    for sp, sub in df.groupby("species"):
        sizes = sub["group_id"].value_counts()
        share = sizes.iloc[0] / len(sub)
        report.append(f"| {sp} | {len(sub):,} | {len(sizes):,} | {sizes.iloc[0]:,} | {share:.1%} | "
                      + ", ".join(f"{s:,}" for s in sizes.iloc[:5]) + " |")
        if share > C.MAX_GROUP_SHARE:
            too_big.append((sp, sizes.index[0], int(sizes.iloc[0]), share))

    # 유사 사진 쌍 표본 (사람 확인용: 경계값 근처 우선)
    random.seed(C.SEED)
    sample_rows.sort(key=lambda r: -r[3])
    near_edge = sample_rows[:100]
    rest = random.sample(sample_rows[100:], min(100, max(0, len(sample_rows) - 100)))
    with open(out / "reports" / "phash_pairs_sample.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["동물", "item_a", "item_b", "해밍거리", "①키 같음", "사람 확인(같은 사진?/다른 사진?)"])
        for r in near_edge + rest:
            w.writerow(list(r) + [""])

    if too_big:
        report += ["", "## ⚠ 묶음이 너무 큼 (팀 결정 필요)", ""]
        for sp, gid, size, share in too_big:
            g = df[df.group_id == gid]
            report.append(f"- {sp} {gid}: {size:,}장 ({share:.1%}) · 품종 상위 "
                          + ", ".join(f"{k} {v}" for k, v in g['breed_group'].value_counts().head(3).items())
                          + f" · 촬영일 {g['date'].min()} ~ {g['date'].max()}")
        report.append("")
        report.append("원인 후보: ④ 재촬영 의심 규칙이 날짜를 따라 사슬처럼 이어 붙음, 또는 ③ 유사 사진이 서로 다른 아이를 이음.")
        report.append("선택지는 팀이 정한다 (예: ④ 기간 줄이기, ③ 기준 낮추기, 그대로 진행). 어느 쪽이든 split_config.py 에 기록.")
        if args.accept_large_groups:
            report.append("\n**팀 결정으로 큰 묶음을 그대로 사용함 (--accept-large-groups)**")

    (out / "reports" / "group_report.md").write_text("\n".join(report), encoding="utf-8")
    df[["item_id", "group_id", "rule1_key", "breed_group"]].to_csv(
        out / "manifests" / "eye_groups.csv", index=False, encoding="utf-8-sig")

    print("\n".join(report))
    if too_big and not args.accept_large_groups:
        sys.exit("\n[중단] 묶음이 너무 큼 → reports/group_report.md 를 팀에 공유하고 결정 받기 (분할은 아직 안 함)")
    print(f"\n저장: {out/'manifests'/'eye_groups.csv'}, {out/'reports'/'group_report.md'}")


if __name__ == "__main__":
    main()
