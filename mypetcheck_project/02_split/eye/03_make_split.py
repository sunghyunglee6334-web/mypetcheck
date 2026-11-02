"""
03_make_split.py — 묶음 단위로 Train / Val / Test / Bridge 나누기

방식 (교과 8 Split 원칙: 묶음 단위 배정, 미리 정한 비율, seed 고정)
  - 묶음(group_id) 하나는 통째로 한쪽에만 들어감 → 모든 질환 모델에서 같은 쪽
  - StratifiedGroupKFold(seed 42)로 "질환 × 이진 라벨 × 기기" 비율을 각 조각에 고르게
  - 개   : 20조각 → Train 14 · Val 3 · Test 2 · Bridge 1  (70/15/10/5 %)
  - 고양이: 5조각 → 1조각 Test(20%), 나머지 Train(80%) → Train 을 다시 5조각(cv_fold 0~4)
  - 조각 → split 대응은 split_config.py 에 미리 고정 (결과 보고 고르지 않음)

출력 : OUT_DIR/manifests/split_v1.csv
이미 있으면 덮어쓰지 않는다 (봉인 보호). 다시 나누려면 SPLIT_VERSION 을 올리고 이유를 기록.

실행: python3 03_make_split.py
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import C, out_dir  # noqa: E402


def fold_ids(sub, n_folds, seed):
    y = (sub["disease"] + "|" + sub["label"].astype(str) + "|" + sub["device"]).values
    sgkf = StratifiedGroupKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    fold = pd.Series(-1, index=sub.index)
    for k, (_, te) in enumerate(sgkf.split(sub, y, groups=sub["group_id"].values)):
        fold.iloc[te] = k
    assert (fold >= 0).all()
    return fold


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = out_dir(args.out)
    target = out / "manifests" / f"{C.SPLIT_VERSION}.csv"
    if target.exists():
        sys.exit(f"[중단] {target.name} 이 이미 있음. 봉인된 분할은 덮어쓰지 않는다.\n"
                 f"  다시 나눠야 하면 split_config.py 의 SPLIT_VERSION 을 올리고 이유를 team_hub.md 에 기록.")

    items = pd.read_csv(out / "manifests" / "eye_items.csv", dtype=str, encoding="utf-8-sig")
    groups = pd.read_csv(out / "manifests" / "eye_groups.csv", dtype=str, encoding="utf-8-sig")
    df = items.merge(groups, on="item_id", how="left", validate="one_to_one")
    if df["group_id"].isna().any():
        sys.exit("[중단] 묶음 ID 없는 사진이 있음 → 02_build_groups.py 를 먼저 실행")

    df["split"] = ""
    df["cv_fold"] = ""

    dog = df[df.species == "개"]
    if len(dog):
        f = fold_ids(dog, C.DOG_N_FOLDS, C.SEED)
        df.loc[dog.index, "split"] = f.map(C.DOG_FOLD_TO_SPLIT)

    cat = df[df.species == "고양이"]
    if len(cat):
        f = fold_ids(cat, C.CAT_N_FOLDS, C.SEED)
        df.loc[cat.index, "split"] = ["test" if k == C.CAT_TEST_FOLD else "train" for k in f]
        cat_train = df[(df.species == "고양이") & (df.split == "train")]
        cv = fold_ids(cat_train, C.CAT_CV_FOLDS, C.SEED)
        df.loc[cat_train.index, "cv_fold"] = cv.astype(str)

    if (df["split"] == "").any():
        sys.exit("[중단] split 이 비어 있는 사진이 있음")

    df["age_band"] = df["age"].map(C.age_band)
    cols = ["item_id", "group_id", "split", "cv_fold", "species", "disease", "label", "orig_label",
            "device", "age", "age_band", "gender", "breed", "breed_group", "date", "eye",
            "file_name", "sha256", "phash", "cache_path", "rule1_key"]
    df[cols].to_csv(target, index=False, encoding="utf-8-sig")

    print(f"저장: {target}\n")
    print(pd.crosstab([df.species, df.split], df.label.map({"0": "문제 없음", "1": "문제 있음"}),
                      margins=True, margins_name="합계"))
    print("\n다음: 04_leak_check.py (누수 검사 6가지 → 모두 0 이어야 유효)")


if __name__ == "__main__":
    main()
