#!/usr/bin/env bash
# run_split.sh — 안구 Split 전체 실행 (한 단계라도 실패하면 거기서 멈춤)
#
#   cd ~/mypetcheck/02_split/eye
#   bash run_split.sh --test    가짜 데이터로 시험 (/tmp 에만 만들고 지움, 진짜 결과에 영향 없음)
#   bash run_split.sh           진짜 데이터 → 이 폴더 안 manifests/, reports/ 에 결과
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${1:-}" == "--test" ]]; then
  T=/tmp/pet_split_test
  rm -rf "$T"
  python3 00_make_fake_data.py "$T/zips"
  IDX=(--zip-dir "$T/zips" --out "$T/out" --cache "$T/cache")
  OUT=(--out "$T/out")
else
  IDX=()
  OUT=()
fi

echo "== 1/5 사진 목록 + crop 캐시 + 해시 =="; python3 01_build_index.py   "${IDX[@]}"
echo "== 2/5 누수 방지 묶음 ==";              python3 02_build_groups.py  "${OUT[@]}"
echo "== 3/5 분할 ==";                         python3 03_make_split.py    "${OUT[@]}"
echo "== 4/5 누수 검사 ==";                    python3 04_leak_check.py    "${OUT[@]}"
echo "== 5/5 봉인 + 보고서 ==";                python3 05_seal_and_report.py "${OUT[@]}"
echo "완료. reports/ 의 보고서와 봉인 해시를 PM 에게 전달하세요."
