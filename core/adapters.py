"""Sign-in policy: Google only, allowlist only.

The allowlist is checked twice: at first sign-in (signup) and on every
later sign-in, so removal from the allowlist actually removes access.
"""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.shortcuts import render


def _allowed(email):
    return (email or "").lower() in settings.UNDIARY_ALLOWED_EMAILS


def promote_if_admin(user):
    """Grant Django admin to accounts on UNDIARY_ADMIN_EMAILS."""
    if (user.email or "").lower() in settings.UNDIARY_ADMIN_EMAILS:
        if not (user.is_staff and user.is_superuser):
            user.is_staff = True
            user.is_superuser = True
            user.save(update_fields=["is_staff", "is_superuser"])
    return user


class NoLocalSignupAdapter(DefaultAccountAdapter):
    """No username-and-password accounts, ever."""

    def is_open_for_signup(self, request):
        return False


class AllowlistSocialAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        return _allowed(sociallogin.user.email)

    def save_user(self, request, sociallogin, form=None):
        from .models import Tag

        user = promote_if_admin(super().save_user(request, sociallogin, form))
        Tag.ensure_defaults(user)
        return user

    def pre_social_login(self, request, sociallogin):
        if not _allowed(sociallogin.user.email):
            raise ImmediateHttpResponse(
                render(request, "account/denied.html", status=403)
            )
