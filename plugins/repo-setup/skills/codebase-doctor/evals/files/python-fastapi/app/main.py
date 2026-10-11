from fastapi import FastAPI
from app.database import get_db
from app.models import User

app = FastAPI()


@app.get("/users")
def list_users():
    print(f"Fetching users at {__name__}")  # no logging, print used instead
    db = get_db()
    try:
        users = db.execute("SELECT * FROM users WHERE name = '" + "test" + "'")  # SQL injection vulnerability
        return {"users": [dict(u) for u in users]}
    except:
        pass  # swallowed error


@app.get("/users/{user_id}")
def get_user(user_id):  # no validation (no int type annotation)
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
