# mypetcheck — 마이펫첵 (MyPetCheck)

반려동물 피부·안구 질환 사전 체크 앱 프로젝트

보호자가 스마트폰으로 촬영하면 개/고양이를 구분하고, 안구·피부 질환별로 "문제 있음 / 없음"을 판정합니다. 하나라도 문제 있음이면 **병원 방문을 권고**하고 의심 질환명과 근처 동물병원을 안내합니다. 이 앱은 진단을 하지 않습니다.

<br>

## 팀과 브랜치

| 이름 | 역할 | 브랜치 |
|---|---|---|
| 이성형 | PM (PM · 데이터) | `feature/pm-data` |
| 최용훈 | 메인 엔지니어 (AI 총괄 · QA) | `feature/ai-qa` |
| 박하나 | 서브 엔지니어 (ML · 프론트엔드) | `feature/ml-frontend` |
| 김하민 | 서브 엔지니어 (백엔드 · MLOps) | `feature/backend-mlops` |
| 김준형 | 비전 엔지니어 (컴퓨터 비전 · 영상) | `feature/vision-media` |

<br>

## 작업 규칙

1. 각자 **자기 브랜치**에서 작업하고 push 한다. `main` 에 직접 push 할 수 없다.
2. 작업이 끝나면 자기 브랜치 → `main` 으로 **Pull Request** 를 연다.
3. **PM(이성형)이 리뷰·승인해야만** `main` 에 병합된다.
4. `main` 은 삭제·강제 push(force push)가 막혀 있다.
5. 작업 전에 `main` 최신 내용을 자기 브랜치로 받아 온다.

```bash
git checkout feature/본인브랜치
git pull origin main
```

<br>

## 데이터 출처 · 업로드 금지

- 데이터 출처: **AI Hub** (반려동물 안구 질환 데이터 등)
- AI Hub 약관에 따라 **원본 사진·라벨 JSON 은 이 저장소에 올리지 않습니다.** 
- `.gitignore` 기준 (공모전 · 정부 지원사업 · 포트폴리오 공통)
  - ① 절대 안 올림 (AI Hub 약관): 원본 사진, 라벨 JSON, crop 캐시, zip, 사진별 장부(manifests), 실행 결과(reports)
  - ② 안 올림 (사업 · 보안): 모델 가중치, API 키(`.env`), 가상환경, 개인 설정
  - ③ 올림: 코드, 문서, 집계 결과(`docs/results/` 에 직접 복사한 것만), 화면 캡처
- 데이터를 재현하려면 AI Hub 에서 직접 신청해 받는다.
