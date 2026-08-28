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


class NoLocalSignupAdapter(DefaultAccountAdapter):
    """No username-and-password accounts, ever."""

    def is_open_for_signup(self, request):
        return False


class AllowlistSocialAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        return _allowed(sociallogin.user.email)

    def pre_social_login(self, request, sociallogin):
        if not _allowed(sociallogin.user.email):
            raise ImmediateHttpResponse(
                render(request, "account/denied.html", status=403)
            )
