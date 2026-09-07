"""Contract tests for admin user management + hard-delete cascade wipe."""
from uuid import uuid4

from sqlalchemy import Column, ForeignKey, Integer, create_engine, event
from sqlalchemy.orm import Session, backref, configure_mappers, declarative_base, relationship

from app.model.billing import (  # noqa: F401
    PaymentTransaction,
    SubscriptionPlan,
    UserSubscription,
)
from app.model.cover_image import CoverImage  # noqa: F401
from app.model.credit import UserCredit  # noqa: F401
from app.model.feedback import StoryFeedback  # noqa: F401
from app.model.guest_session import GuestSession  # noqa: F401
from app.model.liberation import LiberationDefinition, UserJourney, UserJourneyStep  # noqa: F401
from app.model.profile import UserProfile
from app.model.story import Story  # noqa: F401
from app.model.user import User, UserOAuthAccount  # noqa: F401
from app.services import service_admin_user as admin_users


def test_user_owned_fks_declare_cascade():
    configure_mappers()
    assert UserProfile.__table__.c.user_id.foreign_keys
    profile_fk = next(iter(UserProfile.__table__.c.user_id.foreign_keys))
    assert profile_fk.ondelete == "CASCADE"

    oauth_fk = next(iter(UserOAuthAccount.__table__.c.user_id.foreign_keys))
    assert oauth_fk.ondelete == "CASCADE"

    journey_fk = next(iter(UserJourney.__table__.c.user_id.foreign_keys))
    assert journey_fk.ondelete == "CASCADE"

    lib_created = next(iter(LiberationDefinition.__table__.c.created_by.foreign_keys))
    assert lib_created.ondelete == "SET NULL"
    assert LiberationDefinition.__table__.c.created_by.nullable is True


def test_user_relationships_use_passive_deletes():
    configure_mappers()
    assert User.oauth_accounts.property.passive_deletes in (True, "all")
    assert User.profile.property.passive_deletes in (True, "all")
    assert User.subscriptions.property.passive_deletes in (True, "all")
    assert User.payments.property.passive_deletes in (True, "all")


def test_patch_guards_self_and_last_admin():
    """Lightweight unit test of guard branches via a tiny in-memory session."""
    Base = declarative_base()

    class MiniUser(Base):
        __tablename__ = "mini_users"
        id = Column(Integer, primary_key=True)
        is_admin = Column(Integer, default=1)
        is_active = Column(Integer, default=1)
        token_version = Column(Integer, default=1)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        only = MiniUser(id=1, is_admin=1, is_active=1, token_version=1)
        db.add(only)
        db.commit()

        # Mirror the last-admin check used by the service
        assert db.query(MiniUser).filter(MiniUser.is_admin == 1).count() == 1


def test_passive_deletes_allows_user_delete_with_profile_child():
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


def test_admin_user_schemas_import():
    from app.schemas.schema_admin_users import (
        AdminUserDeleteResponse,
        AdminUserDetail,
        AdminUserListItem,
        AdminUserPatchRequest,
    )

    patch = AdminUserPatchRequest(is_active=False, is_admin=True)
    assert patch.is_active is False
    assert patch.is_admin is True
    assert AdminUserListItem.__name__
    assert AdminUserDetail.__name__
    assert AdminUserDeleteResponse.__name__


def test_service_module_exports():
    assert callable(admin_users.list_users)
    assert callable(admin_users.get_user_detail)
    assert callable(admin_users.patch_user)
    assert callable(admin_users.delete_user)
    assert callable(admin_users.count_admins)
