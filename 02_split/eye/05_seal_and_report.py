"""
05_seal_and_report.py — 누수 검사 통과 후 봉인 + 분할 보고서

  - 04_leak_check.py 를 통과해야만 실행됨
  - split 파일 전체, 개 Test·Bridge 목록, 고양이 Test 목록의 SHA-256 을 seal.json 에 기록
    → team_hub.md 6장에 그대로 옮겨 적는다 (나중에 목록이 바뀌었는지 누구나 확인 가능)
  - 이미 봉인돼 있으면 다시 봉인하지 않는다

출력 : OUT_DIR/reports/seal_<버전>.json, split_report_<버전>.md
실행 : python3 05_seal_and_report.py
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import C, out_dir  # noqa: E402


def list_hash(names):
    return hashlib.sha256("\n".join(sorted(names)).encode("utf-8")).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = out_dir(args.out)
    split_path = out / "manifests" / f"{C.SPLIT_VERSION}.csv"
    seal_path = out / "reports" / f"seal_{C.SPLIT_VERSION}.json"
    if not (out / "reports" / f"{C.SPLIT_VERSION}.LEAK_PASS").exists():
        sys.exit("[중단] 누수 검사를 통과하지 않음 → 04_leak_check.py 먼저")
    if seal_path.exists():
        sys.exit(f"[중단] 이미 봉인됨: {seal_path.name}")

    df = pd.read_csv(split_path, dtype=str, encoding="utf-8-sig")
    seal = {
        "version": C.SPLIT_VERSION,
        "sealed_at": datetime.now().isoformat(timespec="seconds"),
        "split_file_sha256": hashlib.sha256(split_path.read_bytes()).hexdigest(),
        "dog_test_list_sha256": list_hash(df[(df.species == "개") & (df.split == "test")].file_name),
        "dog_bridge_list_sha256": list_hash(df[(df.species == "개") & (df.split == "bridge")].file_name),
        "cat_test_list_sha256": list_hash(df[(df.species == "고양이") & (df.split == "test")].file_name),
        "rule4_enabled": C.RULE4_ENABLED, "phash_max_dist": C.PHASH_MAX_DIST, "seed": C.SEED,
    }
    seal_path.write_text(json.dumps(seal, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 보고서 ──
    order = ["train", "val", "test", "bridge"]
    L = [f"# 분할 보고서 ({C.SPLIT_VERSION})", "", f"봉인 시각: {seal['sealed_at']}", ""]
    L += ["## 1. 몇 장씩 나뉘었나", "", "| 동물 | " + " | ".join(order) + " | 합계 |", "|---|" + "---:|" * 5]
    for sp, sub in df.groupby("species"):
        c = sub.split.value_counts()
        L.append(f"| {sp} | " + " | ".join(f"{c.get(s,0):,} ({c.get(s,0)/len(sub):.1%})" for s in order) + f" | {len(sub):,} |")
    tot = df.split.value_counts()
    L.append("| 합계 | " + " | ".join(f"{tot.get(s,0):,}" for s in order) + f" | {len(df):,} |")

    L += ["", "## 2. 질환별 문제 있음 / 문제 없음", ""]
    for sp, sub in df.groupby("species"):
        sides = [s for s in order if s in set(sub.split)]
        L += [f"### {sp}", "", "| 질환 | " + " | ".join(f"{s} 0/1" for s in sides) + " | 판단 |", "|---|" + "---|" * (len(sides) + 1)]
        for dis, d in sub.groupby("disease"):
            cells, test1 = [], 0
            for s in sides:
                x = d[d.split == s]
                n0, n1 = (x.label == "0").sum(), (x.label == "1").sum()
                cells.append(f"{n0:,} / {n1:,}")
                if s == "test":
                    test1 = n1
            L.append(f"| {dis} | " + " | ".join(cells) + f" | {'참고용 (Test 문제 있음 30장 미만)' if test1 < 30 else '평가 가능'} |")
        L.append("")

    L += ["## 3. 원래 중증도가 세 쪽에 고르게 갔는지 (학습에는 안 씀)", "",
          "| 동물 | 질환 | 원래 라벨 | " + " | ".join(order) + " |", "|---|---|---|" + "---:|" * 4]
    sev = df[df.label == "1"]
    for (sp, dis, ol), d in sev.groupby(["species", "disease", "orig_label"]):
        c = d.split.value_counts()
        L.append(f"| {sp} | {dis} | {ol} | " + " | ".join(f"{c.get(s,0):,}" for s in order) + " |")

    for col, title in [("device", "기기"), ("age_band", "나이 구간")]:
        L += ["", f"## {title}별 분포", "", "| 동물 | " + title + " | " + " | ".join(order) + " |", "|---|---|" + "---:|" * 4]
        for (sp, v), d in df.groupby(["species", col]):
            c = d.split.value_counts()
            L.append(f"| {sp} | {v} | " + " | ".join(f"{c.get(s,0):,}" for s in order) + " |")

    cat_tr = df[(df.species == "고양이") & (df.split == "train")]
    if len(cat_tr):
        L += ["", "## 고양이 교차검증 조각", "", "| cv_fold | 사진 | 문제 있음 |", "|---|---:|---:|"]
        for k, d in cat_tr.groupby("cv_fold"):
            L.append(f"| {k} | {len(d):,} | {(d.label=='1').sum():,} |")

    L += ["", "## 봉인 해시 (team_hub.md 6장에 기록)", "", "```", json.dumps(seal, ensure_ascii=False, indent=2), "```",
          "", "Test·Bridge 는 최종 모델 확정 후 1회만 사용. 학습 코드는 split_guard.py 로만 분할을 읽는다."]
    rp = out / "reports" / f"split_report_{C.SPLIT_VERSION}.md"
    rp.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L[:12]))
    print(f"\n봉인: {seal_path}\n보고서: {rp}")


if __name__ == "__main__":
    main()
