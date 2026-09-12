# -*- coding: utf-8 -*-
"""
별무리 고등학교 AI 스케줄 관리 비서 - Flask 백엔드

- DB: SQLite (schedule_assistant.db, 최초 실행 시 자동 생성)
- AI: Google Gemini API (google-genai 공식 SDK)
- 인증: 세션 기반 간단 로그인/회원가입

실행 방법:
    pip install -r requirements.txt
    cp .env.example .env   # 그 다음 .env 안에 GEMINI_API_KEY 입력
    python app.py
"""
import os
import json
import sqlite3
from datetime import datetime, date
from functools import wraps

from flask import Flask, request, jsonify, session, render_template, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

from google import genai
from google.genai import types

# ----------------------------------------------------------------------------
# 초기 설정
# ----------------------------------------------------------------------------
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-please-change")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "schedule_assistant.db")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
# gemini-2.5-flash : 무료 티어 제공, 속도/성능 균형이 좋은 모델 (2026.09 기준)
# 요청량이 많다면 gemini-2.5-flash-lite 로 바꾸면 무료 한도가 더 넉넉합니다.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

DAY_NAMES = ["월", "화", "수", "목", "금"]

SCHOOL_NAME = "별무리 고등학교"
AI_ASSISTANT_NAME = "별비서"


# ----------------------------------------------------------------------------
# DB 헬퍼
# ----------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            grade INTEGER NOT NULL,
            class_no INTEGER NOT NULL,
            student_no INTEGER,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,      -- 0=월 ... 4=금
            period INTEGER NOT NULL,           -- 1~9교시
            subject TEXT NOT NULL,
            teacher TEXT,
            room TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            is_done INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'user',   -- user | ai | memo
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS memos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            analyzed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_date TEXT NOT NULL,
            meal_type TEXT NOT NULL,   -- 중식 | 석식
            menu TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,   -- user | model
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )

    # 데모용 급식/공지 시드 데이터 (없을 때만)
    count = conn.execute("SELECT COUNT(*) AS c FROM meals").fetchone()["c"]
    if count == 0:
        today = date.today().isoformat()
        conn.execute(
            "INSERT INTO meals (meal_date, meal_type, menu) VALUES (?,?,?)",
            (today, "중식", "잡곡밥, 미역국, 제육볶음, 계란말이, 배추김치"),
        )
        conn.execute(
            "INSERT INTO meals (meal_date, meal_type, menu) VALUES (?,?,?)",
            (today, "석식", "카레라이스, 유부장국, 오이무침, 요구르트"),
        )

    count = conn.execute("SELECT COUNT(*) AS c FROM notices").fetchone()["c"]
    if count == 0:
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO notices (title, content, created_at) VALUES (?,?,?)",
            ("2학기 중간고사 안내", "2학기 중간고사는 10월 넷째 주에 실시됩니다. 시험 범위는 각 교과 게시판을 확인하세요.", now),
        )
        conn.execute(
            "INSERT INTO notices (title, content, created_at) VALUES (?,?,?)",
            ("동아리 발표회 신청", "동아리 발표회 참가 신청을 이번 주 금요일까지 담당 선생님께 제출해주세요.", now),
        )

    conn.commit()
    conn.close()


# ----------------------------------------------------------------------------
# 인증 헬퍼
# ----------------------------------------------------------------------------
def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "로그인이 필요합니다."}), 401
            return redirect(url_for("login_page"))
        return view_func(*args, **kwargs)

    return wrapped


def current_user_row(conn):
    return conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()


# ----------------------------------------------------------------------------
# 페이지 라우트
# ----------------------------------------------------------------------------
@app.route("/")
@login_required
def index():
    return render_template("index.html", school_name=SCHOOL_NAME, ai_name=AI_ASSISTANT_NAME)


@app.route("/login")
def login_page():
    if "user_id" in session:
        return redirect(url_for("index"))
    return render_template("login.html", school_name=SCHOOL_NAME)


# ----------------------------------------------------------------------------
# 인증 API
# ----------------------------------------------------------------------------
@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    name = (data.get("name") or "").strip()
    grade = data.get("grade")
    class_no = data.get("class_no")
    student_no = data.get("student_no")

    if not username or not password or not name or not grade or not class_no:
        return jsonify({"error": "아이디, 비밀번호, 이름, 학년, 반은 필수입니다."}), 400
    if len(password) < 4:
        return jsonify({"error": "비밀번호는 4자 이상이어야 합니다."}), 400

    conn = get_db()
    exists = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if exists:
        conn.close()
        return jsonify({"error": "이미 사용 중인 아이디입니다."}), 409

    conn.execute(
        """INSERT INTO users (username, password_hash, name, grade, class_no, student_no, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (
            username,
            generate_password_hash(password),
            name,
            int(grade),
            int(class_no),
            int(student_no) if student_no else None,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    user_id = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()["id"]
    conn.close()

    session["user_id"] = user_id
    return jsonify({"message": "회원가입이 완료되었습니다.", "user_id": user_id})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "아이디 또는 비밀번호가 올바르지 않습니다."}), 401

    session["user_id"] = user["id"]
    return jsonify({"message": "로그인 성공"})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"message": "로그아웃 되었습니다."})


@app.route("/api/me")
@login_required
def api_me():
    conn = get_db()
    user = current_user_row(conn)
    conn.close()
    return jsonify(
        {
            "id": user["id"],
            "username": user["username"],
            "name": user["name"],
            "grade": user["grade"],
            "class_no": user["class_no"],
            "student_no": user["student_no"],
        }
    )


# ----------------------------------------------------------------------------
# 시간표 API
# ----------------------------------------------------------------------------
@app.route("/api/schedule", methods=["GET"])
@login_required
def get_schedule():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM schedule WHERE user_id=? ORDER BY day_of_week, period",
        (session["user_id"],),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/schedule", methods=["POST"])
@login_required
def add_schedule():
    data = request.get_json(silent=True) or {}
    try:
        day_of_week = int(data.get("day_of_week"))
        period = int(data.get("period"))
    except (TypeError, ValueError):
        return jsonify({"error": "요일과 교시는 숫자로 입력해주세요."}), 400
    subject = (data.get("subject") or "").strip()
    if not subject or not (0 <= day_of_week <= 4) or period < 1:
        return jsonify({"error": "요일(0~4), 교시(1 이상), 과목명을 확인해주세요."}), 400

    conn = get_db()
    conn.execute(
        "INSERT INTO schedule (user_id, day_of_week, period, subject, teacher, room) VALUES (?,?,?,?,?,?)",
        (session["user_id"], day_of_week, period, subject, data.get("teacher") or "", data.get("room") or ""),
    )
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.close()
    return jsonify({"message": "시간표가 추가되었습니다.", "id": new_id})


@app.route("/api/schedule/<int:item_id>", methods=["DELETE"])
@login_required
def delete_schedule(item_id):
    conn = get_db()
    conn.execute("DELETE FROM schedule WHERE id=? AND user_id=?", (item_id, session["user_id"]))
    conn.commit()
    conn.close()
    return jsonify({"message": "삭제되었습니다."})


# ----------------------------------------------------------------------------
# To-Do API
# ----------------------------------------------------------------------------
@app.route("/api/todos", methods=["GET"])
@login_required
def get_todos():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM todos WHERE user_id=? ORDER BY (due_date IS NULL), due_date, is_done",
        (session["user_id"],),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/todos", methods=["POST"])
@login_required
def add_todo():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "할 일 제목을 입력해주세요."}), 400

    conn = get_db()
    conn.execute(
        "INSERT INTO todos (user_id, title, description, due_date, is_done, source, created_at) VALUES (?,?,?,?,0,'user',?)",
        (session["user_id"], title, data.get("description") or "", data.get("due_date") or None, datetime.now().isoformat()),
    )
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.close()
    return jsonify({"message": "할 일이 추가되었습니다.", "id": new_id})


@app.route("/api/todos/<int:todo_id>", methods=["PATCH"])
@login_required
def update_todo(todo_id):
    data = request.get_json(silent=True) or {}
    conn = get_db()
    todo = conn.execute("SELECT * FROM todos WHERE id=? AND user_id=?", (todo_id, session["user_id"])).fetchone()
    if not todo:
        conn.close()
        return jsonify({"error": "할 일을 찾을 수 없습니다."}), 404

    is_done = data.get("is_done")
    title = data.get("title")
    due_date = data.get("due_date")

    if is_done is not None:
        conn.execute("UPDATE todos SET is_done=? WHERE id=?", (1 if is_done else 0, todo_id))
    if title is not None:
        conn.execute("UPDATE todos SET title=? WHERE id=?", (title, todo_id))
    if due_date is not None:
        conn.execute("UPDATE todos SET due_date=? WHERE id=?", (due_date or None, todo_id))

    conn.commit()
    conn.close()
    return jsonify({"message": "수정되었습니다."})


@app.route("/api/todos/<int:todo_id>", methods=["DELETE"])
@login_required
def delete_todo(todo_id):
    conn = get_db()
    conn.execute("DELETE FROM todos WHERE id=? AND user_id=?", (todo_id, session["user_id"]))
    conn.commit()
    conn.close()
    return jsonify({"message": "삭제되었습니다."})


# ----------------------------------------------------------------------------
# 메모 API (+ AI 분석 -> To-Do 자동 추가)
# ----------------------------------------------------------------------------
@app.route("/api/memos", methods=["GET"])
@login_required
def get_memos():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM memos WHERE user_id=? ORDER BY id DESC", (session["user_id"],)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/memos", methods=["POST"])
@login_required
def add_memo():
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "메모 내용을 입력해주세요."}), 400

    conn = get_db()
    conn.execute(
        "INSERT INTO memos (user_id, content, analyzed, created_at) VALUES (?,?,0,?)",
        (session["user_id"], content, datetime.now().isoformat()),
    )
    conn.commit()
    new_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.close()
    return jsonify({"message": "메모가 저장되었습니다.", "id": new_id})


@app.route("/api/memos/<int:memo_id>", methods=["DELETE"])
@login_required
def delete_memo(memo_id):
    conn = get_db()
    conn.execute("DELETE FROM memos WHERE id=? AND user_id=?", (memo_id, session["user_id"]))
    conn.commit()
    conn.close()
    return jsonify({"message": "삭제되었습니다."})


@app.route("/api/memos/<int:memo_id>/analyze", methods=["POST"])
@login_required
def analyze_memo(memo_id):
    if not gemini_client:
        return jsonify({"error": "GEMINI_API_KEY가 설정되어 있지 않습니다. .env 파일을 확인해주세요."}), 500

    conn = get_db()
    memo = conn.execute(
        "SELECT * FROM memos WHERE id=? AND user_id=?", (memo_id, session["user_id"])
    ).fetchone()
    if not memo:
        conn.close()
        return jsonify({"error": "메모를 찾을 수 없습니다."}), 404

    today_str = date.today().isoformat()
    prompt = (
        "다음은 고등학생이 작성한 메모입니다. 이 메모에서 실제로 해야 할 일(과제, 준비물, 시험공부, 약속 등)을 "
        "찾아 리스트로 추출하세요.\n"
        f"오늘 날짜는 {today_str} 입니다. '내일', '다음주 월요일' 같은 상대적 날짜 표현이 있으면 실제 날짜(YYYY-MM-DD)로 "
        "변환하세요. 날짜 언급이 전혀 없다면 due_date는 빈 문자열로 두세요. 해야 할 일이 없다면 tasks를 빈 배열로 반환하세요.\n\n"
        f'메모 내용:\n"""\n{memo["content"]}\n"""'
    )

    task_schema = {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "할 일 제목 (간결하게)"},
                        "due_date": {"type": "string", "description": "YYYY-MM-DD 형식, 없으면 빈 문자열"},
                    },
                    "required": ["title", "due_date"],
                },
            }
        },
        "required": ["tasks"],
    }

    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=task_schema,
                temperature=0.2,
            ),
        )
        result = json.loads(response.text)
        tasks = result.get("tasks", [])
    except Exception as e:  # noqa: BLE001
        conn.close()
        return jsonify({"error": f"메모 분석 중 오류가 발생했습니다: {e}"}), 500

    now = datetime.now().isoformat()
    added = []
    for t in tasks:
        title = (t.get("title") or "").strip()
        if not title:
            continue
        due = (t.get("due_date") or "").strip() or None
        conn.execute(
            "INSERT INTO todos (user_id, title, description, due_date, is_done, source, created_at) "
            "VALUES (?,?,?,?,0,'memo',?)",
            (session["user_id"], title, "메모에서 AI가 자동으로 추출한 항목입니다.", due, now),
        )
        added.append({"title": title, "due_date": due or ""})

    conn.execute("UPDATE memos SET analyzed=1 WHERE id=?", (memo_id,))
    conn.commit()
    conn.close()

    return jsonify({"added_tasks": added})


# ----------------------------------------------------------------------------
# 급식 / 공지 API
# ----------------------------------------------------------------------------
@app.route("/api/meals", methods=["GET"])
@login_required
def get_meals():
    target = request.args.get("date") or date.today().isoformat()
    conn = get_db()
    rows = conn.execute("SELECT * FROM meals WHERE meal_date=?", (target,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/notices", methods=["GET"])
@login_required
def get_notices():
    conn = get_db()
    rows = conn.execute("SELECT * FROM notices ORDER BY id DESC LIMIT 10").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ----------------------------------------------------------------------------
# AI 챗봇 (Function Calling으로 시간표/할일/급식/공지 데이터 접근)
# ----------------------------------------------------------------------------
def build_chat_tools(conn, user_id):
    """현재 로그인한 학생 데이터에 접근하는 Gemini function-calling 도구 목록을 만든다."""

    def get_my_timetable() -> str:
        """이 학생의 주간 시간표(요일, 교시, 과목, 교실)를 조회합니다."""
        rows = conn.execute(
            "SELECT day_of_week, period, subject, room FROM schedule WHERE user_id=? ORDER BY day_of_week, period",
            (user_id,),
        ).fetchall()
        if not rows:
            return "등록된 시간표가 없습니다."
        items = [
            {"요일": DAY_NAMES[r["day_of_week"]], "교시": r["period"], "과목": r["subject"], "교실": r["room"] or "미지정"}
            for r in rows
        ]
        return json.dumps(items, ensure_ascii=False)

    def get_my_todos(include_completed: bool = False) -> str:
        """이 학생의 할 일(숙제) 목록을 조회합니다. include_completed를 True로 하면 완료된 항목도 포함합니다."""
        if include_completed:
            rows = conn.execute(
                "SELECT title, due_date, is_done FROM todos WHERE user_id=? ORDER BY due_date", (user_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT title, due_date, is_done FROM todos WHERE user_id=? AND is_done=0 ORDER BY due_date",
                (user_id,),
            ).fetchall()
        if not rows:
            return "등록된 할 일이 없습니다."
        items = [{"제목": r["title"], "마감일": r["due_date"] or "미지정", "완료여부": bool(r["is_done"])} for r in rows]
        return json.dumps(items, ensure_ascii=False)

    def add_new_todo(title: str, due_date: str = "") -> str:
        """새로운 할 일(숙제)을 학생의 To-Do 목록에 추가합니다. due_date는 YYYY-MM-DD 형식, 모르면 빈 문자열로 둡니다."""
        conn.execute(
            "INSERT INTO todos (user_id, title, description, due_date, is_done, source, created_at) "
            "VALUES (?,?,?,?,0,'ai',?)",
            (user_id, title, "AI 비서와의 대화에서 추가됨", due_date or None, datetime.now().isoformat()),
        )
        conn.commit()
        return f"'{title}' 할 일을 To-Do 목록에 추가했습니다."

    def get_meal_info(target_date: str = "") -> str:
        """특정 날짜(YYYY-MM-DD)의 학교 급식 메뉴를 조회합니다. 비워두면 오늘 날짜를 사용합니다."""
        d = target_date or date.today().isoformat()
        rows = conn.execute("SELECT meal_type, menu FROM meals WHERE meal_date=?", (d,)).fetchall()
        if not rows:
            return f"{d} 급식 정보가 등록되어 있지 않습니다."
        return json.dumps([{"구분": r["meal_type"], "메뉴": r["menu"]} for r in rows], ensure_ascii=False)

    def get_school_notices() -> str:
        """최근 학교 공지사항 목록을 조회합니다."""
        rows = conn.execute("SELECT title, content FROM notices ORDER BY id DESC LIMIT 5").fetchall()
        if not rows:
            return "등록된 공지사항이 없습니다."
        return json.dumps([{"제목": r["title"], "내용": r["content"]} for r in rows], ensure_ascii=False)

    return [get_my_timetable, get_my_todos, add_new_todo, get_meal_info, get_school_notices]


@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    if not gemini_client:
        return jsonify({"error": "GEMINI_API_KEY가 설정되어 있지 않습니다. .env 파일을 확인해주세요."}), 500

    data = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()
    if not user_message:
        return jsonify({"error": "메시지를 입력해주세요."}), 400

    user_id = session["user_id"]
    conn = get_db()
    user = current_user_row(conn)

    history_rows = conn.execute(
        "SELECT role, content FROM chat_history WHERE user_id=? ORDER BY id DESC LIMIT 12",
        (user_id,),
    ).fetchall()
    history_rows = list(reversed(history_rows))

    system_instruction = (
        f"너는 '{SCHOOL_NAME}'의 AI 스케줄 관리 비서 '{AI_ASSISTANT_NAME}'야. "
        f"학생 {user['name']}({user['grade']}학년 {user['class_no']}반)을 도와주고 있어. "
        "너는 이 학생의 시간표, 할 일(To-Do), 급식, 학교 공지사항에 접근할 수 있는 도구를 갖고 있으니 "
        "필요할 때 적극적으로 활용해서 정확한 정보로 답변해. "
        "말투는 친절하고 다정한 반말 섞인 존댓말로, 이모지는 가끔만 사용해. 답변은 너무 길지 않게 핵심 위주로 해."
    )

    contents = []
    for row in history_rows:
        role = "user" if row["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=row["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))

    tools = build_chat_tools(conn, user_id)

    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tools,
                temperature=0.7,
            ),
        )
        reply_text = response.text or "죄송해요, 답변을 생성하지 못했어요. 다시 한 번 물어봐 줄래요?"
    except Exception as e:  # noqa: BLE001
        conn.close()
        return jsonify({"error": f"AI 응답 생성 중 오류가 발생했습니다: {e}"}), 500

    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO chat_history (user_id, role, content, created_at) VALUES (?,?,?,?)",
        (user_id, "user", user_message, now),
    )
    conn.execute(
        "INSERT INTO chat_history (user_id, role, content, created_at) VALUES (?,?,?,?)",
        (user_id, "model", reply_text, now),
    )
    conn.commit()
    conn.close()

    return jsonify({"reply": reply_text})


# ----------------------------------------------------------------------------
# Google OAuth / Drive / Docs 연동 (선택 기능 - 기본 구조만 제공)
#
# 사용하려면 .env에 아래 값을 추가하고 Google Cloud Console에서
# OAuth 2.0 클라이언트 ID(웹 애플리케이션)를 발급받아야 합니다.
#   GOOGLE_CLIENT_ID=...
#   GOOGLE_CLIENT_SECRET=...
#   GOOGLE_REDIRECT_URI=http://localhost:5000/google/oauth2callback
# 이 기능은 Gemini API 키와는 완전히 별개이며, 없어도 AI 비서 기능은 정상 동작합니다.
# ----------------------------------------------------------------------------
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:5000/google/oauth2callback")
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
]


def google_oauth_enabled():
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)


def build_google_flow():
    from google_auth_oauthlib.flow import Flow  # 지연 import (선택 의존성)

    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_REDIRECT_URI],
        }
    }
    return Flow.from_client_config(client_config, scopes=GOOGLE_SCOPES, redirect_uri=GOOGLE_REDIRECT_URI)


@app.route("/google/authorize")
@login_required
def google_authorize():
    if not google_oauth_enabled():
        return jsonify({"error": "Google 연동이 설정되지 않았습니다. .env에 GOOGLE_CLIENT_ID/SECRET을 추가해주세요."}), 400
    flow = build_google_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    session["google_oauth_state"] = state
    return redirect(auth_url)


@app.route("/google/oauth2callback")
@login_required
def google_oauth2callback():
    if not google_oauth_enabled():
        return redirect(url_for("index"))
    flow = build_google_flow()
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    session["google_credentials"] = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }
    return redirect(url_for("index"))


@app.route("/api/google/drive/recent")
@login_required
def google_drive_recent():
    if not google_oauth_enabled():
        return jsonify({"error": "Google 연동이 설정되지 않았습니다."}), 400
    if "google_credentials" not in session:
        return jsonify({"error": "Google 계정이 연동되어 있지 않습니다. 먼저 /google/authorize 로 연동해주세요."}), 400

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build as gbuild

    creds = Credentials(**session["google_credentials"])
    service = gbuild("drive", "v3", credentials=creds)
    results = (
        service.files()
        .list(pageSize=10, fields="files(id, name, mimeType, webViewLink)", orderBy="modifiedTime desc")
        .execute()
    )
    return jsonify(results.get("files", []))


# ----------------------------------------------------------------------------
# 엔트리 포인트
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    if not GEMINI_API_KEY:
        print("[경고] GEMINI_API_KEY가 설정되어 있지 않습니다. .env 파일을 확인해주세요. (AI 기능이 동작하지 않습니다)")
    app.run(debug=True, host="0.0.0.0", port=5000)
