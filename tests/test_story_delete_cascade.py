"""Admin/member story delete must not 500 when feedback rows exist.

story_feedback.story_id is NOT NULL with ON DELETE CASCADE. SQLAlchemy still
loads the backref collection on parent delete unless passive_deletes is set,
then tries to NULL the FK and raises IntegrityError — which the API surfaces
as the generic 500 envelope.
"""
from sqlalchemy import Column, ForeignKey, Integer, create_engine, event
from sqlalchemy.orm import Session, backref, configure_mappers, declarative_base, relationship

# Import models so mappers configure (same set as other contract tests).
from app.model.billing import (  # noqa: F401
    PaymentTransaction,
    SubscriptionPlan,
    UserSubscription,
)
from app.model.cover_image import CoverImage  # noqa: F401
from app.model.credit import UserCredit  # noqa: F401
from app.model.feedback import StoryFeedback
from app.model.guest_session import GuestSession  # noqa: F401
from app.model.liberation import UserJourney, UserJourneyStep  # noqa: F401
from app.model.profile import UserProfile  # noqa: F401
from app.model.story import Story
from app.model.user import User, UserOAuthAccount  # noqa: F401


def test_feedback_backref_relies_on_db_cascade():
    configure_mappers()
    rel = Story.feedback_entries.property
    assert rel.passive_deletes in (True, "all")
    assert "delete" in rel.cascade


def test_parent_delete_with_not_null_child_fk_needs_passive_deletes():
    """Mirror the production failure shape on a tiny SQLite schema."""
    Base = declarative_base()

    class Parent(Base):
        __tablename__ = "parents"
        id = Column(Integer, primary_key=True)

    class Child(Base):
        __tablename__ = "children"
        id = Column(Integer, primary_key=True)
        parent_id = Column(
            Integer,
            ForeignKey("parents.id", ondelete="CASCADE"),
            nullable=False,
        )
        parent = relationship("Parent", backref=backref("children"))

    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add(Parent(id=1))
        db.add(Child(id=1, parent_id=1))
        db.commit()

    with Session(engine) as db:
        parent = db.get(Parent, 1)
        try:
            db.delete(parent)
            db.commit()
            raised = None
        except Exception as exc:  # noqa: BLE001 — assert exact failure mode
            raised = exc
            db.rollback()

    assert raised is not None
    assert "NOT NULL" in str(raised) or "IntegrityError" in type(raised).__name__


def test_passive_deletes_allows_parent_delete_with_children():
    Base = declarative_base()

    class Parent(Base):
        __tablename__ = "parents"
        id = Column(Integer, primary_key=True)

    class Child(Base):
        __tablename__ = "children"
        id = Column(Integer, primary_key=True)
        parent_id = Column(
            Integer,
            ForeignKey("parents.id", ondelete="CASCADE"),
            nullable=False,
        )
        parent = relationship(
            "Parent",
            backref=backref(
                "children",
                cascade="all, delete-orphan",
                passive_deletes=True,
            ),
        )

    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add(Parent(id=1))
        db.add(Child(id=1, parent_id=1))
        db.commit()

    with Session(engine) as db:
        parent = db.get(Parent, 1)
        db.delete(parent)
        db.commit()
        assert db.query(Child).count() == 0


def test_story_feedback_fk_declares_database_cascade():
    fk = next(
        fk
        for fk in StoryFeedback.__table__.c.story_id.foreign_keys
        if fk.column.table.name == "stories"
    )
    assert fk.ondelete == "CASCADE"
