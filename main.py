from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")

DUMMY_MEAL = ["비빔밥", "팽이버섯된장국", "떡갈비구이", "포도", "배추김치"]
DUMMY_TIMETABLE = ["1교시: 국어", "2교시: 수학", "3교시: 영어", "4교시: 사회", "5교시: 과학", "6교시: 체육"]

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "school_name": "OO고등학교",
            "meals": DUMMY_MEAL,
            "timetable": DUMMY_TIMETABLE
        }
    )
