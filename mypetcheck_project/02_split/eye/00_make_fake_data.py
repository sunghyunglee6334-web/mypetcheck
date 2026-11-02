"""
make_fake_data.py — 진짜 데이터 없이 Split 프로그램을 시험하는 가짜 라벨 zip 만들기
(AI Hub 구조를 흉내만 냄. 사진은 무작위 무늬)

실행: python3 00_make_fake_data.py /tmp/fake_eye
"""
import io
import json
import random
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from PIL import Image

random.seed(0)
np.random.seed(0)
out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/fake_eye")
out.mkdir(parents=True, exist_ok=True)

DOG = {"결막염": ["무", "유"], "유루증": ["무", "유"], "백내장": ["무", "초기", "비성숙", "성숙"], "궤양성각막질환": ["무", "상", "하"]}
CAT = {"결막염": ["무", "유"], "각막궤양": ["무", "유"]}
DOG_BREEDS = ["말티즈", "포메라니안", "토이 푸들", "푸들", "시츄", "믹스"]
CAT_BREEDS = ["코리아 숏헤어", "페르시안"]


def animal_pattern():
    return np.random.randint(0, 255, (16, 16, 3), dtype=np.uint8)


def photo(pattern, jitter):
    a = pattern.astype(np.int16) + np.random.randint(-jitter, jitter + 1, pattern.shape)
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).resize((300, 260), Image.NEAREST)
    b = io.BytesIO()
    img.save(b, "JPEG", quality=90)
    return b.getvalue()


def make(species, n_animals, diseases, breeds, devices, prefix, zf_train, zf_val):
    k = 0
    for a in range(n_animals):
        pat = animal_pattern()
        breed, age, gender = random.choice(breeds), random.randint(0, 12), random.randint(0, 1)
        d0 = date(2021, 1, 1) + timedelta(days=random.randint(0, 200))
        visits = [d0] + ([d0 + timedelta(days=random.randint(1, 5))] if random.random() < 0.15 else [])
        dev = random.choice(devices)
        zf = zf_train if random.random() < 0.88 else zf_val
        for d in visits:
            for eye in ["왼쪽", "오른쪽"]:
                img = photo(pat, 6 if d == d0 else 25)
                for dis, stages in diseases.items():
                    stage = random.choice(stages) if random.random() < 0.3 else "무"
                    k += 1
                    fn = f"{prefix}{k:06d}_{a:05d}.jpg"
                    meta = {"file_name": fn, "date_time": f"{d} 00:00:00", "device": dev,
                            "gender": gender if random.random() > 0.01 else float(gender),
                            "age": age, "breed": breed, "medical_type": 1,
                            "width_height": [4032, 3024], "eye_position": eye, "image_resolution": [72, 72]}
                    label = {"label_filename": "crop_" + fn, "label_category_id": 1, "label_path": "x",
                             "label_deleted": 0, "label_bbox": [100, 100, 400, 380], "label_disease_nm": dis,
                             "label_disease_lv_1": stage, "label_disease_lv_2": stage, "label_disease_lv_3": stage}
                    folder = f"{species}/안구/일반/{dis}/{stage}"
                    zf.writestr(f"{folder}/crop_{fn[:-4]}.json", json.dumps({"images": {"meta": meta}, "label": label}, ensure_ascii=False))
                    zf.writestr(f"{folder}/crop_{fn}", img)
    return k


with zipfile.ZipFile(out / "TL1.zip", "w") as tr, zipfile.ZipFile(out / "VL.zip", "w") as va:
    n = make("개", 400, DOG, DOG_BREEDS, ["스마트폰", "스마트폰", "일반카메라"], "D0_", tr, va)
    n += make("고양이", 120, CAT, CAT_BREEDS, ["일반카메라"], "C0_", tr, va)
    # 범위 밖(검안경) 1장 — 빠져야 정상
    tr.writestr("개/안구/일반/결막염/유/crop_D0_x.json", json.dumps({"images": {"meta": {"file_name": "D0_x.jpg", "device": "검안경"}}, "label": {}}))
print(f"가짜 JSON {n:,}개 → {out}")
