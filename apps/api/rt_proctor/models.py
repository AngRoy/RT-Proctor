from sqlalchemy import Column, Integer, String, Float, JSON, Text
from .db import Base
class Session(Base):
    __tablename__='sessions'
    id=Column(Integer, primary_key=True); session_id=Column(String, unique=True, index=True)
    calibrated=Column(Integer, default=0); started_at=Column(Float, default=0.0); ended_at=Column(Float, default=0.0)
    calib_json=Column(JSON, default={})
class Event(Base):
    __tablename__='events'
    id=Column(Integer, primary_key=True); session_id=Column(String, index=True); ts=Column(Float); etype=Column(String); data=Column(JSON)
class Flag(Base):
    __tablename__='flags'
    id=Column(Integer, primary_key=True); session_id=Column(String, index=True); ts=Column(Float)
    severity=Column(String); kind=Column(String); details=Column(JSON)
class Submission(Base):
    __tablename__='submissions'
    id=Column(Integer, primary_key=True); session_id=Column(String, index=True); question_id=Column(String)
    language=Column(String); source=Column(Text); stdout=Column(Text); stderr=Column(Text); status=Column(String); time_ms=Column(Integer)
