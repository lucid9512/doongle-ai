"""DB 연결 + Job 모델 (동기 SQLAlchemy).

워커는 doongle-api가 소유한 PostgreSQL `jobs` 테이블을 최소 컬럼으로 다시 매핑한다.
하는 일은 단 하나: job_id로 찾아 status/result를 update.
설계상 동기(추론이 순차·연산 중심)라 sync 엔진/세션을 쓴다.
"""

import logging
from typing import Optional

from sqlalchemy import create_engine, String, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
)

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class Job(Base):
    """`jobs` 테이블의 최소 매핑.

    워커는 job_id로 행을 찾아 status/result만 갱신한다. 다른 컬럼(생성시각 등)은
    api가 관리하므로 매핑하지 않는다. job_id를 ORM 식별자(primary_key)로 선언하지만,
    update는 Core 문(아래 update_job)으로 처리해 실제 PK 구성과 무관하게 동작한다.
    """

    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String)
    result: Mapped[Optional[str]] = mapped_column(String, nullable=True)


def create_db_engine(database_url: str) -> Engine:
    # create_engine은 DBAPI 드라이버(psycopg2)는 즉시 import하지만, 실제 DB 연결은
    # 첫 사용 시점까지 열지 않는다(시작 시 DB가 떠 있지 않아도 됨, 드라이버만 설치돼 있으면 OK).
    # pool_pre_ping: 끊긴 커넥션을 체크아웃 시 감지해 재연결.
    return create_engine(database_url, pool_pre_ping=True, future=True)


def create_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, future=True)


def update_job(
    session_factory: sessionmaker,
    job_id: str,
    status: str,
    result: Optional[str] = None,
) -> int:
    """job_id로 행을 찾아 status/result를 갱신한다. 갱신된 행 수를 반환(0이면 없음)."""
    with session_factory() as session:
        stmt = (
            update(Job)
            .where(Job.job_id == job_id)
            .values(status=status, result=result)
        )
        res = session.execute(stmt)
        session.commit()
        rowcount = res.rowcount or 0
        if rowcount == 0:
            logger.warning("job not found for update: job_id=%s", job_id)
        return rowcount
