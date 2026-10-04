from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    email = Column(String)


# マイグレーションツール未使用: 直接 CREATE TABLE
def init_db():
    engine = create_engine("sqlite:///./app.db")
    Base.metadata.create_all(engine)
