# MyPetCheck · 02_split/eye — 안구 데이터 Split 프로그램

기준 문서: 프로젝트 문서 `claude/pet_eye_split_plan.md`
Split 코드는 전부 이 폴더 하나에 있고, 결과도 이 폴더 안에 생긴다.

## 이 폴더

```
~/mypetcheck/02_split/eye/
├── split_config.py         설정: 비율·규칙·경로 (여기만 고침, Test 본 뒤에는 안 고침)
├── common.py               공통 함수
├── split_guard.py          학습·평가 코드가 분할을 읽는 유일한 입구
├── 00_make_fake_data.py    가짜 데이터 (시험용)
├── 01_build_index.py       사진 목록 + crop 256px 캐시 + SHA-256·pHash
├── 02_build_groups.py      누수 방지 묶음 (① 가상 개체 ② 같은 파일 ③ 유사 사진 ④ 재촬영 의심)
├── 03_make_split.py        묶음 단위 분할 (개 70/15/10/5, 고양이 80/20 + 교차검증 5조각)
├── 04_leak_check.py        누수 검사 6가지 (하나라도 0이 아니면 멈춤)
├── 05_seal_and_report.py   봉인 해시 + 분할 보고서
├── run_split.sh            1~5 한 번에 실행
├── manifests/              (실행 후 생김) eye_items.csv, eye_groups.csv, split_v1.csv
└── reports/                (실행 후 생김) 묶음·누수·분할 보고서, 봉인 해시
```

- AI Hub 라벨 zip: 윈도우 다운로드 폴더의 `153.반려동물 안구질환 데이터`를 자동으로 찾음 (`/mnt/c/Users/…/Downloads/`). 못 찾으면 `split_config.py` 의 `AIHUB_EYE_DIR` 에 적기
- crop 캐시: `~/mypetcheck/cache/eye_crop256/` (약 2~3GB)

## 실행

```bash
cd ~/mypetcheck/02_split/eye
bash run_split.sh --test    # 1) 가짜 데이터로 시험 (/tmp 에만 생김)
bash run_split.sh           # 2) 진짜 데이터
```

2단계에서 "묶음이 너무 큼"으로 멈추면 `reports/group_report.md` 를 팀에 공유하고 결정 받는다.
4단계에서 누수 검사가 실패하면 봉인되지 않는다.

## 학습 코드에서 분할 읽기

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "mypetcheck/02_split/eye"))
from split_guard import load_split

train = load_split("개", ["train"])
val   = load_split("개", ["val"])
# 최종 모델 확정 후 1회만
test  = load_split("개", ["test"], allow_sealed=True, reason="최종 모델 확정 후 1회 평가")
```

- 사진 파일은 각 행의 `cache_path`
- 봉인 후 split 파일이 바뀌면 읽지 않음
- Test·Bridge 는 이유를 적어야 열리고, 열 때마다 `reports/sealed_access_log_split_v1.csv` 에 남음
- 기기·나이·품종 등 모델 입력 금지 열은 빼고 돌려줌 (그룹별 성적을 낼 때만 `with_meta=True`)
