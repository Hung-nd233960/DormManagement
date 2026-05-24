from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base


class Member(Base):
    __tablename__ = "members"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_removed = Column(Boolean, default=False, nullable=False)
    force_password_change = Column(Boolean, default=True, nullable=False)
    is_sentinel = Column(Boolean, default=False, nullable=False)
    language = Column(String, default="en", nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    chore_states = relationship("ChoreState", back_populates="member", cascade="all, delete-orphan")
    chore_logs = relationship("ChoreLog", back_populates="member")


class Chore(Base):
    __tablename__ = "chores"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    name_vi = Column(String, nullable=True)
    icon = Column(String, default="🧹")
    limit_hours = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)

    chore_states = relationship("ChoreState", back_populates="chore", cascade="all, delete-orphan")
    chore_logs = relationship("ChoreLog", back_populates="chore")


class ChoreState(Base):
    __tablename__ = "chore_states"

    member_id = Column(Integer, ForeignKey("members.id", ondelete="CASCADE"), primary_key=True)
    chore_id = Column(Integer, ForeignKey("chores.id", ondelete="CASCADE"), primary_key=True)
    tally = Column(Integer, default=0, nullable=False)
    deficit = Column(Integer, default=0, nullable=False)

    member = relationship("Member", back_populates="chore_states")
    chore = relationship("Chore", back_populates="chore_states")


class ChoreLog(Base):
    __tablename__ = "chore_logs"

    id = Column(Integer, primary_key=True, index=True)
    member_id = Column(Integer, ForeignKey("members.id", ondelete="SET NULL"), nullable=True)
    chore_id = Column(Integer, ForeignKey("chores.id", ondelete="SET NULL"), nullable=True)
    logged_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    note = Column(Text, nullable=True)
    logged_member_name = Column(String, nullable=True)
    logged_chore_name = Column(String, nullable=True)

    member = relationship("Member", back_populates="chore_logs")
    chore = relationship("Chore", back_populates="chore_logs")
