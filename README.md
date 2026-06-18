# 미국 주요 경기지표 대시보드 (자동 갱신)

매일 자동으로 데이터를 받아 와 차트로 보여주는 정적 웹 대시보드입니다.
GitHub Actions가 매일 데이터를 갱신하고 Netlify가 자동 재배포하므로, **Claude나 내 컴퓨터를 켜둘 필요가 없습니다.**

- 경제지표 5종: 실업률, 산업생산(전월대비), 소매판매(전월대비), GDP 성장률(연율), ISM 제조업 PMI — 출처 FRED / ISM
- 주가지수 3종: S&P 500, 다우존스, 나스닥 100 (월간 종가) — 출처 Stooq

## 구성 파일
- `index.html` — 대시보드 (브라우저에서 `data.json`을 읽어 차트 표시)
- `data.json` — 데이터 (Actions가 매일 갱신)
- `update_data.py` — 데이터 수집 스크립트 (FRED + Stooq + ISM)
- `.github/workflows/daily.yml` — 매일 실행되는 GitHub Actions 워크플로
- `netlify.toml` — Netlify 정적 배포 설정

## 설치 (최초 1회, 약 5분)

### 1. GitHub 저장소 만들기
1. https://github.com/new 에서 새 저장소 생성 (예: `us-econ-dashboard`).
2. 이 폴더의 모든 파일을 업로드합니다.
   - 웹에서: "uploading an existing file"로 드래그&드롭 (단, `.github/workflows/daily.yml`은 폴더 구조를 유지해야 하니 git 사용 권장).
   - 터미널 사용 시:
     ```bash
     cd github_bundle
     git init && git add -A && git commit -m "init dashboard"
     git branch -M main
     git remote add origin https://github.com/<your-id>/us-econ-dashboard.git
     git push -u origin main
     ```

### 2. Netlify에 연결 (자동 배포)
1. https://app.netlify.com → **Add new site → Import an existing project → GitHub** 선택.
2. 방금 만든 저장소 선택.
3. Build command: 비워둠 / Publish directory: `.` (netlify.toml에 이미 설정됨) → **Deploy**.
4. 배포되면 `https://<사이트이름>.netlify.app` 공개 URL이 생깁니다. 어디서든 접속하세요.

> 푸시할 때마다 Netlify가 자동 재배포합니다. Actions가 매일 `data.json`을 갱신·푸시하므로 사이트도 매일 자동으로 최신화됩니다.

### 3. (자동) 매일 갱신 확인
- GitHub 저장소 → **Actions** 탭에서 "Daily data update" 워크플로가 매일 도는 것을 볼 수 있습니다.
- 지금 바로 테스트하려면 Actions 탭 → 워크플로 선택 → **Run workflow** 클릭.

## 자주 묻는 점
- **데이터 사용량/요금?** 없음. 하루 1회, 수백 KB 수준. GitHub Actions(공개 저장소 무제한) · Netlify 무료 플랜으로 충분합니다.
- **실행 시각 변경?** `.github/workflows/daily.yml`의 cron(UTC 기준)을 수정하세요. 예: `0 22 * * *` = 한국 오전 7시.
- **데이터 소스가 막히면?** 스크립트는 항목별로 예외 처리되어, 실패한 지표는 직전 값을 유지하고 나머지만 갱신합니다(대시보드가 비지 않음).
- **지표 의미** 산업생산·소매판매는 전월대비(MoM) 증감률, GDP는 분기 연율 성장률, PMI는 50 기준 확장/위축.
