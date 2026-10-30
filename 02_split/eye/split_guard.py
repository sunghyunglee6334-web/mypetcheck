"""
split_guard.py — 학습·평가 코드가 분할을 읽는 유일한 입구

  from split_guard import load_split
  tr = load_split("개", ["train"])                 # 학습
  va = load_split("개", ["val"])                   # 모델·임계값 고르기
  te = load_split("개", ["test"], allow_sealed=True, reason="최종 모델 확정 후 1회 평가")

지키는 것
  - 봉인 해시와 split 파일이 다르면 읽지 않음 (몰래 바뀐 분할 차단)
  - test / bridge 는 allow_sealed=True 와 이유를 적어야만 열림, 열 때마다 기록이 남음
  - 이미 한 번 열린 test / bridge 를 다시 열면 경고 (몇 번 열었는지 기록에 그대로 남음)
  - 모델 입력으로 쓰면 안 되는 열은 빼고 돌려줌
"""
import csv
import getpass
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import split_config as C  # noqa: E402

SEALED = {"test", "bridge"}
# 모델 입력 금지 (지름길 학습 방지). 평가 때 그룹별 성적을 낼 때만 별도로 읽는다.
FORBIDDEN_INPUT_COLUMNS = ["device", "age", "age_band", "gender", "breed", "breed_group", "date",
                           "rule1_key", "orig_label", "sha256", "phash", "group_id"]


def _paths(out=None):
    out = Path(out) if out else Path(C.OUT_DIR)
    return (out / "manifests" / f"{C.SPLIT_VERSION}.csv",
            out / "reports" / f"seal_{C.SPLIT_VERSION}.json",
            out / "reports" / f"sealed_access_log_{C.SPLIT_VERSION}.csv")


def load_split(species, splits, allow_sealed=False, reason="", with_meta=False, out=None):
    split_path, seal_path, log_path = _paths(out)
    if not seal_path.exists():
        raise RuntimeError("봉인되지 않은 분할은 쓰지 않는다 → 04_leak_check.py, 05_seal_and_report.py 먼저")
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    if hashlib.sha256(split_path.read_bytes()).hexdigest() != seal["split_file_sha256"]:
        raise RuntimeError("split 파일이 봉인 후 바뀜 → 사용 금지, PM 에게 보고")

    asked_sealed = SEALED & set(splits)
    if asked_sealed:
        if not allow_sealed or not reason.strip():
            raise PermissionError(f"{sorted(asked_sealed)} 는 봉인됨. 최종 확정 후에만 allow_sealed=True, reason='…' 로 연다")
        prev = 0
        if log_path.exists():
            with open(log_path, encoding="utf-8-sig") as f:
                prev = sum(1 for r in csv.DictReader(f) if r["species"] == species and r["split"] in asked_sealed)
        if prev:
            print(f"[경고] {species} {sorted(asked_sealed)} 는 이미 {prev}번 열렸음. 결과를 보고 모델을 고치면 안 됨", file=sys.stderr)
        new = not log_path.exists()
        with open(log_path, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "user", "species", "split", "reason"])
            for s in sorted(asked_sealed):
                w.writerow([datetime.now().isoformat(timespec="seconds"), getpass.getuser(), species, s, reason])

    df = pd.read_csv(split_path, dtype=str, encoding="utf-8-sig")
    df = df[(df.species == species) & (df.split.isin(splits))].copy()
    df["label"] = df["label"].astype(int)
    if not with_meta:
        df = df.drop(columns=[c for c in FORBIDDEN_INPUT_COLUMNS if c in df.columns])
    return df.reset_index(drop=True)
