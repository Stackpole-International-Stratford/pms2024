import ldap
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class CustomLDAPBackend(BaseBackend):
    """
    Custom authentication backend that:
      1) Allows any <firstname.lastname>@preload user to sign in with password "12345",
         regardless of the preload account's stored password.  On first preload login:
           • Create a real user "<firstname.lastname>"
           • Copy groups from "<firstname.lastname>@preload"
           • Delete the "<firstname.lastname>@preload" user
           • Set the new user's password to "12345"
      2) Otherwise, tries each LDAP server in settings.LDAP_SERVERS.  On successful bind:
           • If a local user exists with password="12345", replace it with an AD‐backed user
             (copy groups from the old one, delete the old one, create new one with the AD password).
           • If a local user exists with any other password, just return it unchanged.
           • If no local user exists, create one, copy groups from leftover preload (if present),
             delete preload, set password=AD password, and return it.
    """
    PRELOAD_PASSWORD = "12345"

    def authenticate(self, request, username=None, password=None):
        if not username or password is None:
            return None

        username = username.lower().strip()
        # If you still want the “must contain a dot” rule, keep this:
        if '.' not in username:
            return None

        User = get_user_model()

        # --------------------------------------------------------------------
        # 1) PRELOAD‐FALLBACK: if the user typed password == "12345", ignore whatever the preload's own hash is.
        # --------------------------------------------------------------------
        if password == self.PRELOAD_PASSWORD:
            preload_username = f"{username}@preload"
            try:
                preload_user = User.objects.get(username=preload_username)
            except User.DoesNotExist:
                # No such preload user → cannot log in with "12345"
                return None
            else:
                # We no longer check preload_user.check_password("12345").
                # We simply see that "<username>@preload" exists and accept "12345".
                # Next, check if a real "<username>" already exists:
                try:
                    real_user = User.objects.get(username=username)
                except User.DoesNotExist:
                    # Create a brand‐new "<username>" with password="12345"
                    real_user = User.objects.create_user(username=username)
                    real_user.is_staff = True
                    real_user.set_password(self.PRELOAD_PASSWORD)
                    real_user.save()

                    # Copy groups from preload_user → real_user, then delete preload_user
                    real_user.groups.set(preload_user.groups.all())
                    real_user.save()

                    logger.info(f"Preload login: created real user '{username}', copied groups, deleted '{preload_username}'.")
                    preload_user.delete()
                    return real_user

                else:
                    # A "<username>" already exists locally.
                    if real_user.check_password(self.PRELOAD_PASSWORD):
                        # They previously signed in via preload and still have password "12345".
                        return real_user
                    else:
                        # Their local account is already AD‐backed (or someone altered it). Reject "12345".
                        return None

        # --------------------------------------------------------------------
        # 2) FALLBACK TO LDAP (password != "12345")
        # --------------------------------------------------------------------
        ldap_servers = getattr(settings, 'LDAP_SERVERS', [])
        for server_config in ldap_servers:
            server_uri = server_config.get('URI')
            user_dn_template = server_config.get('USER_DN_TEMPLATE').format(user=username)

            try:
                conn = ldap.initialize(server_uri)
                conn.set_option(ldap.OPT_REFERRALS, 0)
                conn.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
                conn.simple_bind_s(user_dn_template, password)
                # Successful bind → handle local user logic
                return self._handle_post_ldap_bind(username, password)
            except ldap.INVALID_CREDENTIALS:
                continue
            except ldap.SERVER_DOWN:
                continue
            except Exception:
                continue
            finally:
                try:
                    conn.unbind_s()
                except:
                    pass

        return None

    def _handle_post_ldap_bind(self, username, ldap_password):
        """
        After a successful LDAP bind:
          A) If no local '<username>' exists, create one with password=ldap_password,
             copy groups from '<username>@preload' if it exists, delete preload, return it.
          B) If local '<username>' exists and check_password("12345") is True,
             delete it, create new user with password=ldap_password, copy groups, return it.
          C) If local '<username>' exists and password != "12345", return it.
        """
        User = get_user_model()

        try:
            existing = User.objects.get(username=username)
        except User.DoesNotExist:
            # Case A
            new_user = User.objects.create_user(username=username)
            new_user.is_staff = True
            new_user.set_password(ldap_password)
            new_user.save()

            preload_username = f"{username}@preload"
            try:
                preload = User.objects.get(username=preload_username)
            except User.DoesNotExist:
                pass
            else:
                new_user.groups.set(preload.groups.all())
                new_user.save()
                preload.delete()

            return new_user

        else:
            # local "<username>" already exists
            if existing.check_password(self.PRELOAD_PASSWORD):
                # Case B: it was a preload-based user who never switched to AD
                old_groups = list(existing.groups.all())
                existing.delete()

                new_user = User.objects.create_user(username=username)
                new_user.is_staff = True
                new_user.set_password(ldap_password)
                new_user.save()
                new_user.groups.set(old_groups)
                new_user.save()
                return new_user
            else:
                # Case C: already AD-backed (or manually changed password)
                return existing

    def get_user(self, user_id):
        User = get_user_model()
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
