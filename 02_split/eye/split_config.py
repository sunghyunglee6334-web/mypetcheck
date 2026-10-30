"""
split_config.py — 안구 데이터 Split 설정 (한 곳에서만 고친다)

여기 값은 분할 전에 확정한다. Test를 본 뒤에는 바꾸지 않는다.
바꿔야 하면 SPLIT_VERSION 을 올리고(split_v2), 이유를 team_hub.md 에 기록한다.
근거 문서: claude/pet_eye_split_plan.md
"""
from pathlib import Path

# ── 버전 ──────────────────────────────────────────────
SPLIT_VERSION = "split_v1"
SEED = 42

# ── 경로 (WSL 기준) ───────────────────────────────────
# 이 파일이 있는 폴더 = ~/mypetcheck/02_split/eye/  → 결과(manifests, reports)도 이 폴더 안에 생김
HERE = Path(__file__).resolve().parent
OUT_DIR = HERE

# 라벨 zip(TL1.zip, TL2.zip, VL.zip) 위치
#   비워 두면 윈도우 다운로드 폴더에서 "153.반려동물 안구질환 데이터"를 자동으로 찾는다.
#   다른 곳에 있으면 아래에 직접 적는다 (예: "/mnt/d/AIHub/153.반려동물 안구질환 데이터")
AIHUB_EYE_DIR = ""


def label_zip_dirs():
    import glob
    base = AIHUB_EYE_DIR
    if not base:
        hits = glob.glob("/mnt/c/Users/*/Downloads/153*안구*") + glob.glob("/mnt/c/Users/*/다운로드/153*안구*")
        if len(hits) != 1:
            raise SystemExit("[중단] AI Hub 안구 데이터 폴더를 찾지 못했거나 여러 개임: "
                             f"{hits}\n  split_config.py 의 AIHUB_EYE_DIR 에 직접 적어 주세요.")
        base = hits[0]
    dirs = sorted(glob.glob(f"{base}/**/라벨링데이터", recursive=True))
    if not dirs:
        raise SystemExit(f"[중단] {base} 아래에 '라벨링데이터' 폴더가 없음")
    return dirs


# crop 256px 캐시: 프로젝트 안 cache 폴더 (WSL 안이라 학습 때 빠름, Git 에는 안 올림)
PROJECT_ROOT = HERE.parents[1]                 # ~/mypetcheck
CACHE_DIR = PROJECT_ROOT / "cache" / "eye_crop256"

# ── 사용 범위 (10/30 결정) ─────────────────────────────
USE_DEVICES = {"스마트폰", "일반카메라"}
CACHE_LONG_SIDE = 256

# ── 이진 라벨 (10/30 결정: 중증도 제외) ─────────────────
NORMAL_LABELS = {"무"}            # → 0 (문제 없음). 나머지(유·상·하·초기·비성숙·성숙) → 1

# ── 분할 비율 (10/30 결정) ─────────────────────────────
# 개: 묶음을 20조각으로 나눠 14·3·2·1 조각씩 → 70/15/10/5 %
DOG_N_FOLDS = 20
DOG_FOLD_TO_SPLIT = {**{i: "train" for i in range(0, 14)},
                     **{i: "val" for i in range(14, 17)},
                     **{i: "test" for i in range(17, 19)},
                     19: "bridge"}
# 고양이: 5조각 중 1조각 Test(20%), 나머지 Train(80%) → Train 안에서 다시 5조각 교차검증
CAT_N_FOLDS = 5
CAT_TEST_FOLD = 4                 # 미리 고정 (결과를 보고 고르지 않음)
CAT_CV_FOLDS = 5

# ── 누수 방지 묶음 규칙 (pet_eye_split_plan.md 3-1) ──────
PHASH_MAX_DIST = 8                # ③ 유사 사진: pHash 해밍거리 ≤ 8 이면 같은 묶음
RULE4_ENABLED = True              # ④ 재촬영 의심 규칙 사용 여부 (끄려면 팀 결정 + 기록 필요)
RULE4_MAX_DAYS = 7                # ④ 촬영일 차 ≤ 7일
RULE4_MAX_AGE_DIFF = 1            # ④ 나이 차 ≤ 1살
# 묶음 하나가 이 비율보다 크면 분할이 한쪽으로 쏠리므로 멈추고 팀 결정을 받는다 (숨기지 않음)
MAX_GROUP_SHARE = 0.03            # 동물별 전체 사진의 3%

# ── 품종명 통일 (묶음 만들 때만 사용, 넓게 묶는 쪽) ─────────
# "푸들"(구분 없음)과 토이/미니어처/미디엄 푸들은 같은 아이일 수 있으므로 묶음 키에서는 한 이름으로 본다
BREED_GROUP_MAP = {
    "푸들": "푸들계열", "토이 푸들": "푸들계열", "미니어처 푸들": "푸들계열",
    "미디엄 푸들": "푸들계열", "스탠다드 푸들": "푸들계열",
    "웰시 코기 펨브록": "웰시코기계열", "웰시 코기 카디건": "웰시코기계열",
}

# ── 분할 전에 정한 제외 규칙 (Test 보고 추가하지 않음) ─────
EXCLUDE_RULES = ["crop 이미지 없음", "label_filename 확장자 없음", "박스 크기 0"]

# ── 나이 구간 (보고용, 모델 입력 아님) ──────────────────
AGE_BANDS = [(0, 2, "0~2"), (3, 6, "3~6"), (7, 99, "7+")]


def age_band(age):
    try:
        a = int(float(age))
    except (TypeError, ValueError):
        return "?"
    for lo, hi, name in AGE_BANDS:
        if lo <= a <= hi:
            return name
    return "?"
