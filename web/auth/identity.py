"""Identity resolution and tenant provisioning.

Pure functions over a DB session and a Claims value -- no FastAPI, no OAuth I/O.
The OAuth layer (web/auth/routes.py) extracts Claims from a provider and calls
resolve_or_provision_account; everything tenant-shaping lives here so it can be
unit-tested without a live provider.
"""
from __future__ import annotations

import dataclasses
import os
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.credits import default_rate, grant_credits, signup_grant_for_tier
from core.user import User
from db.database import Account, Identity


@dataclasses.dataclass
class Claims:
    provider: str
    subject: str
    email: str
    email_verified: bool


class BetaAccessDenied(Exception):
    """Raised when a login is rejected (unverified email or not on the allowlist)."""


class NoExtensionAccount(Exception):
    """Raised when an extension login has no existing AutoApply account to bind to."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _email_set(var: str) -> set[str]:
    return {e.strip().lower() for e in os.getenv(var, "").split(",") if e.strip()}


def is_admin_email(email: str) -> bool:
    return email.lower() in _email_set("ADMIN_EMAILS")


def signups_open() -> bool:
    """True when anyone with a verified Google/GitHub email may create an account.

    Controlled by ``OPEN_SIGNUPS`` (default off) so the invite gate can be
    restored with an env change, no deploy. Bans still apply: banned accounts
    are rejected by email before provisioning.
    """
    return os.getenv("OPEN_SIGNUPS", "").strip().lower() in {"1", "true", "yes"}


def is_allowed_email(db: Session, email: str) -> bool:
    if signups_open():
        return True
    e = email.lower()
    if e in _email_set("ALLOWED_EMAILS"):
        return True
    from db.database import AllowedEmail
    return db.query(AllowedEmail).filter_by(email=e).first() is not None


def _invite_grants_admin(db: Session, email: str) -> bool:
    from db.database import AllowedEmail
    invite = db.query(AllowedEmail).filter_by(email=email.lower()).first()
    return bool(invite is not None and invite.is_admin)


def sync_admin_flag(db: Session, acct: Account) -> None:
    """Re-derive ``acct.is_admin`` from its sources of truth on every login.

    Admin is granted by ADMIN_EMAILS (env) or by an admin-created invite with
    ``is_admin`` (the ``allowed_email`` row persists after signup). The account
    is admin iff at least one source still says so: removing an email from
    ADMIN_EMAILS demotes it unless an admin invite also grants it, and an
    invite-made admin is never demoted just because it isn't in ADMIN_EMAILS.

    A demoted account whose rate is the admin rate (0) is moved onto the
    default billing rate, else it would keep free LLM usage after demotion.
    """
    want = is_admin_email(acct.email) or _invite_grants_admin(db, acct.email)
    if bool(acct.is_admin) == want:
        return
    acct.is_admin = want
    if not want and not (acct.credit_rate or 0.0):
        acct.credit_rate = default_rate()
    db.commit()


def resolve_existing_account(db: Session, claims: Claims) -> Account:
    """Map OAuth claims to an EXISTING account; never provision (Option B).

    Links a new provider identity onto a known verified email. Raises
    NoExtensionAccount for unverified email, no matching account, or a banned
    account — the extension is a companion to a website-created account, not a
    sign-up surface.
    """
    if not claims.email or not claims.email_verified:
        raise NoExtensionAccount("email not verified")
    email = claims.email.lower()

    ident = (
        db.query(Identity)
        .filter_by(provider=claims.provider, provider_subject=claims.subject)
        .first()
    )
    if ident is not None:
        acct = db.query(Account).filter_by(id=ident.account_id).first()
        if acct is None or acct.banned:
            raise NoExtensionAccount(email)
        sync_admin_flag(db, acct)
        return acct

    acct = db.query(Account).filter_by(email=email).first()
    if acct is None or acct.banned:
        raise NoExtensionAccount(email)
    db.add(Identity(
        account_id=acct.id, provider=claims.provider,
        provider_subject=claims.subject, created_at=_now(),
    ))
    db.commit()
    sync_admin_flag(db, acct)
    return acct


def resolve_or_provision_account(db: Session, claims: Claims) -> Account:
    """Map an OAuth claim set to an Account, provisioning on first sight.

    Raises BetaAccessDenied for unverified emails or non-allowlisted non-admins.

    If two concurrent logins for the same new identity race, the loser hits a
    unique-constraint violation; we roll back and re-resolve, returning the
    account the winner just created.
    """
    try:
        return _resolve_or_provision(db, claims)
    except IntegrityError:
        db.rollback()
        return _resolve_existing_or_raise(db, claims)


def _resolve_existing_or_raise(db: Session, claims: Claims) -> Account:
    """Re-read after a concurrent-write rollback; the winner's rows now exist."""
    ident = (
        db.query(Identity)
        .filter_by(provider=claims.provider, provider_subject=claims.subject)
        .first()
    )
    if ident is not None:
        acct = db.query(Account).filter_by(id=ident.account_id).first()
        if acct is not None and acct.banned:
            raise BetaAccessDenied(claims.email)
        return acct
    acct = db.query(Account).filter_by(email=claims.email.lower()).first()
    if acct is not None:
        if acct.banned:
            raise BetaAccessDenied(claims.email)
        return acct
    raise BetaAccessDenied(claims.email)  # defensive: should not happen


def _resolve_or_provision(db: Session, claims: Claims) -> Account:
    if not claims.email or not claims.email_verified:
        raise BetaAccessDenied("email not verified")

    email = claims.email.lower()

    ident = (
        db.query(Identity)
        .filter_by(provider=claims.provider, provider_subject=claims.subject)
        .first()
    )
    if ident is not None:
        acct = db.query(Account).filter_by(id=ident.account_id).first()
        if acct is not None and acct.banned:
            raise BetaAccessDenied(email)
        if acct is not None:
            sync_admin_flag(db, acct)
        return acct

    admin = is_admin_email(email)
    if not admin and not is_allowed_email(db, email):
        raise BetaAccessDenied(email)

    acct = db.query(Account).filter_by(email=email).first()
    if acct is not None:
        if acct.banned:
            raise BetaAccessDenied(email)
        db.add(Identity(
            account_id=acct.id, provider=claims.provider,
            provider_subject=claims.subject, created_at=_now(),
        ))
        db.commit()
        sync_admin_flag(db, acct)
        return acct

    return _provision_account(db, email=email, is_admin=admin, claims=claims)


def _provision_account(db: Session, *, email: str, is_admin: bool, claims: Claims) -> Account:
    # An admin invite may set the intended tier and grant admin; env-based admin
    # (ADMIN_EMAILS) still wins via OR. No invite row => standard, non-admin.
    from db.database import AllowedEmail
    invite = db.query(AllowedEmail).filter_by(email=email.lower()).first()
    tier = invite.tier if invite is not None else "standard"
    is_admin = is_admin or (invite.is_admin if invite is not None else False)
    profile_id = _profile_for_new_account(db, is_admin)
    acct = Account(
        email=email, is_admin=is_admin, profile_id=profile_id, created_at=_now(),
        credit_rate=0.0 if is_admin else default_rate(),
        tier=tier,
    )
    db.add(acct)
    db.flush()
    db.add(Identity(
        account_id=acct.id, provider=claims.provider,
        provider_subject=claims.subject, created_at=_now(),
    ))
    db.commit()
    grant = signup_grant_for_tier(tier)
    if grant > 0:
        grant_credits(db, profile_id, grant, reason="signup_grant")
    return acct


def _profile_for_new_account(db: Session, is_admin: bool) -> int:
    """The first admin claims the existing profile_id=1 (carry over current data);
    everyone else (and later admins) gets a freshly provisioned profile."""
    if is_admin:
        claimed = db.query(Account).filter_by(profile_id=1).first()
        tenant_one = db.query(User).filter_by(id=1).first()
        if claimed is None and tenant_one is not None:
            return 1
    return _provision_profile(db)


def _provision_profile(db: Session) -> int:
    """Create an empty tenant and seed its prompt rows + skill aliases.

    seed_prompt_defaults(db) only populates the global prompt_defaults table
    (one row per type_key, idempotent). Per-profile Prompt rows are seeded by
    migrate_file_prompts_to_db, which fills in any profile that has zero Prompt
    rows yet using the prompt_defaults content (since the new profile's JSON has
    no prompt_* file paths).
    """
    from db.seed import migrate_file_prompts_to_db, seed_prompt_defaults, seed_skill_aliases

    user = User(name="New User", data="{}")
    db.add(user)
    db.flush()
    seed_prompt_defaults(db)
    migrate_file_prompts_to_db(db)
    seed_skill_aliases(db, profile_id=user.id)
    db.commit()
    from core.demo_data import seed_demo_job
    seed_demo_job(db, user.id)
    return user.id
