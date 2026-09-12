# 별무리 고등학교 · AI 스케줄 관리 비서

별무리 고등학교 학생들을 위한 AI 기반 시간표·할일·메모 관리 웹서비스입니다.

- **Backend**: Python (Flask)
- **Frontend**: HTML5, Tailwind CSS(CDN), Vanilla JS
- **DB**: SQLite (파일 기반, 별도 서버 설치 불필요)
- **AI**: Google Gemini API (무료 티어)

---

## 1. 프로젝트 구조

```
byeolmuri-assistant/
├── app.py                     # Flask 백엔드 전체 (라우트, DB, Gemini 연동)
├── requirements.txt           # 파이썬 패키지 목록
├── .env.example                # 환경변수 예시 (복사해서 .env로 사용)
├── .gitignore
├── README.md
├── templates/
│   ├── login.html              # 로그인 / 회원가입 페이지
│   └── index.html               # 메인 대시보드 (시간표/투두/메모/챗봇)
└── static/
    ├── css/style.css            # 오로라 그라데이션 + 글래스모피즘 디자인
    └── js/dashboard.js          # 대시보드 클라이언트 로직

(최초 실행 시 schedule_assistant.db 파일이 자동 생성됩니다)
```

---

## 2. Gemini API 키 발급 가이드 (무료, 카드 등록 불필요)

이 프로젝트는 **Google Gemini API**를 사용합니다. 구글 계정만 있으면 **무료로, 신용카드 등록 없이** 바로 키를 받을 수 있어요.

1. 브라우저에서 **https://aistudio.google.com/apikey** 접속
2. 평소 쓰는 구글 계정으로 로그인 (처음이면 약관 동의 화면이 한 번 나올 수 있어요)
3. **"Create API key" (API 키 만들기)** 버튼 클릭
4. 프로젝트를 물어보면 새로 만들거나 기존 것 아무거나 선택 → 몇 초 뒤 `AIza...`로 시작하는 키가 생성됩니다
5. 그 키를 복사해서 아래 3번 항목의 `.env` 파일에 붙여넣으면 끝입니다

> 무료 티어는 하루 요청 수 제한(모델에 따라 500~1,500회 수준)이 있지만, 학생 1인용 스케줄 비서로 쓰기엔 충분합니다.
> 참고로 API 키는 비밀번호와 같아요. 절대 깃허브에 올리지 마세요 (`.gitignore`에 `.env`가 이미 포함되어 있어 자동으로 제외됩니다).

---

## 3. 로컬에서 실행하기

```bash
# 1) 프로젝트 폴더로 이동
cd byeolmuri-assistant

# 2) (권장) 가상환경 생성
python -m venv venv
source venv/bin/activate      # Windows는 venv\Scripts\activate

# 3) 패키지 설치
pip install -r requirements.txt

# 4) 환경변수 파일 만들기
cp .env.example .env
# .env 파일을 열어서 GEMINI_API_KEY=발급받은_키 로 수정하세요

# 5) 실행
python app.py
```

브라우저에서 **http://localhost:5000** 접속 → 회원가입 후 바로 사용할 수 있습니다.

---

## 4. 주요 기능

| 기능 | 설명 |
|---|---|
| 로그인/회원가입 | SQLite 기반 세션 로그인, 비밀번호는 해시로 저장 |
| 주간 시간표 | 요일×교시 그리드, 과목 추가/삭제 |
| To-Do & 숙제 | 마감일 지정, 체크 처리, 지남/오늘/내일 표시 |
| 메모장 + AI 분석 | 메모를 저장 후 "✨ AI 분석" 클릭 시 Gemini가 할 일을 찾아 To-Do에 자동 추가 |
| AI 챗봇 (별비서) | 우측 하단 플로팅 버튼. 학생의 시간표·할일·급식·공지 데이터를 Function Calling으로 직접 조회하며 답변 |
| Google Drive/Docs 연동 | 선택 기능. 기본 OAuth 구조만 포함 (아래 8번 참고) |

### AI 챗봇은 이렇게 동작합니다
`app.py`의 `build_chat_tools()` 함수가 아래 도구들을 Gemini에게 넘겨주고, 모델이 필요할 때 스스로 호출합니다 (Function Calling).
- `get_my_timetable` — 내 시간표 조회
- `get_my_todos` — 내 할 일 조회
- `add_new_todo` — 새 할 일 추가
- `get_meal_info` — 특정 날짜 급식 조회
- `get_school_notices` — 학교 공지사항 조회

예: "오늘 급식 뭐야?", "이번 주 화요일 시간표 알려줘", "내일까지 국어 발표자료 준비하는 거 할 일에 추가해줘"

---

## 5. ⚠️ 패키지 관련 참고사항

요청 주셨던 `google-generativeai` 패키지는 Google이 **공식적으로 지원을 종료(deprecated)**했습니다.
그래서 이 프로젝트는 후속 공식 SDK인 **`google-genai`**로 작성했습니다. API 키 발급 방법, 무료 여부는 동일하고, import 방식만 다릅니다.

```python
# 예전 (지원 종료)
import google.generativeai as genai
genai.configure(api_key="...")
model = genai.GenerativeModel("gemini-1.5-flash")

# 현재 (이 프로젝트에서 사용)
from google import genai
client = genai.Client(api_key="...")
client.models.generate_content(model="gemini-2.5-flash", contents="...")
```

---

## 6. GitHub에 올리기

```bash
cd byeolmuri-assistant
git init
git add .
git commit -m "Initial commit: 별무리고 AI 스케줄 비서"
git branch -M main
git remote add origin https://github.com/사용자명/저장소이름.git
git push -u origin main
```

`.env`와 `*.db` 파일은 `.gitignore`에 의해 자동으로 제외되니, API 키가 실수로 올라갈 걱정은 없습니다.
다른 사람이 클론해서 쓸 때는 `.env.example`을 보고 자기 `.env`를 새로 만들면 됩니다.

---

## 7. 배포할 때 참고

- `app.run(debug=True, ...)` 부분은 실제 서비스에서는 `debug=False`로 바꾸세요.
- `FLASK_SECRET_KEY`는 반드시 추측하기 어려운 랜덤 값으로 바꾸세요.
- SQLite는 소규모 학교 프로젝트에는 충분하지만, 사용자가 많아지면 PostgreSQL 등으로 옮기는 걸 고려하세요.

---

## 8. Google Drive/Docs 연동 (선택 사항)

`app.py` 하단에 Google OAuth 기본 구조(`/google/authorize`, `/google/oauth2callback`, `/api/google/drive/recent`)가 포함되어 있습니다. 이 기능은 **Gemini API 키와는 완전히 별개**이며, 없어도 AI 비서는 정상 작동합니다.

활성화하려면:
1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트 생성
2. "APIs & Services → 사용자 인증 정보"에서 **OAuth 클라이언트 ID (웹 애플리케이션)** 발급
3. 승인된 리디렉션 URI에 `http://localhost:5000/google/oauth2callback` 추가
4. "APIs & Services → 라이브러리"에서 Google Drive API, Google Docs API 활성화
5. 발급받은 클라이언트 ID/시크릿을 `.env`에 추가:
   ```
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   ```
6. 로그인 후 `/google/authorize`로 접속하면 연동이 시작됩니다.

이 부분은 학교 프로젝트 범위를 넘어서는 고급 기능이라, 당장 필요 없다면 건너뛰어도 전체 서비스는 문제없이 동작합니다.
