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


def is_allowed_email(db: Session, email: str) -> bool:
    e = email.lower()
    if e in _email_set("ALLOWED_EMAILS"):
        return True
    from db.database import AllowedEmail
    return db.query(AllowedEmail).filter_by(email=e).first() is not None


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
        return acct

    acct = db.query(Account).filter_by(email=email).first()
    if acct is None or acct.banned:
        raise NoExtensionAccount(email)
    db.add(Identity(
        account_id=acct.id, provider=claims.provider,
        provider_subject=claims.subject, created_at=_now(),
    ))
    db.commit()
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
    grant_credits(db, profile_id, signup_grant_for_tier(tier), reason="signup_grant")
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
