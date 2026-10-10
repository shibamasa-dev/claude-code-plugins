from fastapi import FastAPI
from app.database import get_db
from app.models import User

app = FastAPI()


@app.get("/users")
def list_users():
    print(f"Fetching users at {__name__}")  # logging未使用、printで代用
    db = get_db()
    try:
        users = db.execute("SELECT * FROM users WHERE name = '" + "test" + "'")  # SQLインジェクション脆弱性
        return {"users": [dict(u) for u in users]}
    except:
        pass  # エラー握りつぶし


@app.get("/users/{user_id}")
def get_user(user_id):  # バリデーションなし（int型指定なし）
    db = get_db()
    user = db.execute(f"SELECT * FROM users WHERE id = {user_id}")  # f-string SQL
    print(f"Got user {user_id}")
    return {"user": dict(user.fetchone())}


@app.post("/users")
def create_user(name: str, email: str):
    db = get_db()
    db.execute(f"INSERT INTO users (name, email) VALUES ('{name}', '{email}')")
    db.commit()
    return {"status": "created"}
