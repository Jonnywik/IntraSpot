from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.db.models import uid
from app.db.session import engine
from app.domains.organizations.models import OrgMembership
from app.domains.ownership import service
from app.domains.ownership.models import OwnershipTransfer, OwnershipTransferAudit
from app.domains.ownership.schemas import OwnershipTransferCreate, OwnershipTransferDecision
from app.notifications import Notification


def add_admin(db, org, user):
    db.add(OrgMembership(
        id=uid(), org_id=org.id, user_id=user.id, role="admin", active=True,
    ))
    db.commit()


def run_race(barrier, operation):
    barrier.wait(timeout=15)
    with Session(engine(), expire_on_commit=False) as concurrent_db:
        try:
            result = operation(concurrent_db)
            concurrent_db.commit()
            return ("ok", result.id)
        except DomainError as exc:
            concurrent_db.rollback()
            return ("error", exc.status, exc.code)
        except Exception:
            concurrent_db.rollback()
            raise


def test_concurrent_same_key_create_returns_one_offer_without_duplicate_effects(
    db, make_user, make_org,
):
    owner = make_user()
    nominee = make_user()
    org = make_org(owner=owner)
    add_admin(db, org, nominee)
    payload = OwnershipTransferCreate(nominee_id=UUID(nominee.id), client_key=uuid4())
    barrier = Barrier(2)

    def submit(concurrent_db):
        return service.create_transfer(concurrent_db, owner.id, org.id, payload)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run_race(barrier, submit), range(2)))

    assert results[0] == results[1]
    assert results[0][0] == "ok"
    assert db.scalar(select(func.count(OwnershipTransferAudit.id))) == 1
    assert db.scalar(select(func.count(OwnershipTransferAudit.id)).where(
        OwnershipTransferAudit.action == "requested",
    )) == 1
    assert db.scalar(select(func.count(Notification.id)).where(
        Notification.kind == "ownership_transfer_requested",
    )) == 1


def test_concurrent_distinct_offers_serialize_to_at_most_one_pending(
    db, make_user, make_org,
):
    owner = make_user()
    first_nominee = make_user()
    second_nominee = make_user()
    org = make_org(owner=owner)
    add_admin(db, org, first_nominee)
    add_admin(db, org, second_nominee)
    requests = (
        (first_nominee, OwnershipTransferCreate(
            nominee_id=UUID(first_nominee.id), client_key=uuid4(),
        )),
        (second_nominee, OwnershipTransferCreate(
            nominee_id=UUID(second_nominee.id), client_key=uuid4(),
        )),
    )
    barrier = Barrier(2)

    def submit(index, concurrent_db):
        _, payload = requests[index]
        return service.create_transfer(concurrent_db, owner.id, org.id, payload)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda index: run_race(barrier, lambda concurrent_db: submit(index, concurrent_db)),
            range(2),
        ))

    assert sum(result[0] == "ok" for result in results) == 1
    assert sum(result[0] == "error" and result[1] == 409 for result in results) == 1
    pending_count = db.scalar(select(func.count(OwnershipTransfer.id)).where(
        OwnershipTransfer.org_id == org.id,
        OwnershipTransfer.status == "pending",
    ))
    assert pending_count == 1


def test_concurrent_accept_and_revoke_have_one_terminal_winner(
    db, make_user, make_org,
):
    owner = make_user()
    nominee = make_user()
    org = make_org(owner=owner)
    add_admin(db, org, nominee)
    created = service.create_transfer(
        db,
        owner.id,
        org.id,
        OwnershipTransferCreate(nominee_id=UUID(nominee.id), client_key=uuid4()),
    )
    db.commit()
    transfer_id = created.id
    barrier = Barrier(2)
    actions = ((nominee.id, "accept"), (owner.id, "revoke"))

    def submit(index, concurrent_db):
        actor_id, action = actions[index]
        return service.decide_transfer(
            concurrent_db,
            actor_id,
            org.id,
            transfer_id,
            OwnershipTransferDecision(action=action, version=1),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda index: run_race(barrier, lambda concurrent_db: submit(index, concurrent_db)),
            range(2),
        ))

    assert sum(result[0] == "ok" for result in results) == 1
    assert sum(result[0] == "error" and result[1] == 409 for result in results) == 1
    terminal_audits = db.scalars(select(OwnershipTransferAudit).where(
        OwnershipTransferAudit.transfer_id == transfer_id,
        OwnershipTransferAudit.action.in_(("accepted", "revoked")),
    )).all()
    assert len(terminal_audits) == 1
    active_owners = db.scalar(select(func.count(OrgMembership.id)).where(
        OrgMembership.org_id == org.id,
        OrgMembership.role == "owner",
        OrgMembership.active.is_(True),
    ))
    assert active_owners == 1
