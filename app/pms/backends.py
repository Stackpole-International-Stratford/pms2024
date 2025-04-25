import ldap
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
import logging

# Set up logger
logger = logging.getLogger(__name__)

class CustomLDAPBackend(BaseBackend):
    """
    Custom authentication backend for authenticating users against multiple LDAP servers.
    Falls back to the default database authentication if LDAP authentication fails.
    """
    def authenticate(self, request, username=None, password=None):
        """
        Authenticate the user against the configured LDAP servers.

        Args:
            request: The HTTP request object (may be None for non-HTTP auth flows).
            username (str): The username provided by the user.
            password (str): The password provided by the user.

        Returns:
            User object if authentication is successful, or None if it fails.
        """
        # Check if username and password are provided
        if not username or not password:
            logger.warning("No username or password provided.")
            # print("No username or password provided.")
            return None

        # Retrieve the list of LDAP servers from settings
        from django.conf import settings
        ldap_servers = settings.LDAP_SERVERS

        # Iterate over each configured LDAP server to attempt authentication
        for server_config in ldap_servers:
            logger.info(f"Attempting to authenticate {username} on {server_config['URI']}")
            # print(f"Attempting to authenticate {username} on {server_config['URI']}")

            # Call the helper function to perform LDAP authentication
            user = self._authenticate_with_ldap(
                server_config['URI'],  # LDAP server URI
                server_config['USER_DN_TEMPLATE'].format(user=username),  # User's distinguished name (DN)
                password  # User's password
            )
            if user:
                # If authentication succeeds, return the authenticated user
                logger.info(f"Successfully authenticated {username} on {server_config['URI']}")
                # print(f"Successfully authenticated {username} on {server_config['URI']}")
                return user
            else:
                # Log failure for this LDAP server
                logger.warning(f"Authentication failed for {username} on {server_config['URI']}")
                print(f"Authentication failed for {username} on {server_config['URI']}")

        # If all LDAP attempts fail, log the failure and return None
        logger.error(f"All LDAP authentication attempts failed for {username}.")
        # print(f"All LDAP authentication attempts failed for {username}.")
        return None

    def _authenticate_with_ldap(self, server_uri, user_dn, password):
        """
        Helper function to authenticate a user against a single LDAP server.

        Args:
            server_uri (str): The URI of the LDAP server (e.g., "ldap://10.4.131.200").
            user_dn (str): The distinguished name (DN) of the user (e.g., "user@domain.com").
            password (str): The user's password.

        Returns:
            User object if authentication is successful, or None if it fails.
        """
        try:
            logger.info(f"Connecting to LDAP server {server_uri} with user {user_dn}")
            # print(f"Connecting to LDAP server {server_uri} with user {user_dn}")

            # Initialize the LDAP connection
            conn = ldap.initialize(server_uri)
            conn.set_option(ldap.OPT_REFERRALS, 0)  # Disable referrals
            conn.set_option(ldap.OPT_PROTOCOL_VERSION, 3)  # Use LDAPv3 protocol

            # Attempt to bind with the provided user DN and password
            conn.simple_bind_s(user_dn, password)
            logger.info(f"Connection established and user authenticated: {user_dn}")
            # print(f"Connection established and user authenticated: {user_dn}")

            # If successful, fetch or create the corresponding Django user
            return self._get_or_create_user(user_dn.split("@")[0])  # Extract username from email-style DN
        except ldap.INVALID_CREDENTIALS:
            # Handle case where the user's credentials are invalid
            logger.warning(f"Invalid credentials for user {user_dn} on {server_uri}")
            print(f"Invalid credentials for user {user_dn} on {server_uri}")
        except ldap.SERVER_DOWN:
            # Handle case where the LDAP server is unreachable
            logger.error(f"LDAP server {server_uri} is unavailable.")
            print(f"LDAP server {server_uri} is unavailable.")
        except Exception as e:
            # Handle any other unexpected errors
            logger.error(f"Unexpected error during LDAP authentication for {user_dn} on {server_uri}: {str(e)}")
            print(f"Unexpected error during LDAP authentication for {user_dn} on {server_uri}: {str(e)}")
        finally:
            # Always unbind the connection to clean up resources
            try:
                conn.unbind_s()
            except:
                pass

        return None

    def _get_or_create_user(self, username):
            """
            Fetch or create a Django user based on the given username.
            If this is the very first time they log in, look for a 
            preload account (username@preload), copy its groups, then
            delete the preload user.
            """
            User = get_user_model()
            created = False

            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                # first‐time login: create the real user
                user = User.objects.create_user(username=username)
                user.is_staff = True
                user.save()
                created = True

            if created:
                preload_username = f"{username}@preload"
                try:
                    preload = User.objects.get(username=preload_username)
                except User.DoesNotExist:
                    logger.warning(f"No preload user found: {preload_username}")
                else:
                    # 1) copy all group memberships
                    groups = preload.groups.all()
                    user.groups.set(groups)
                    user.save()
                    logger.info(f"Copied {groups.count()} groups from {preload_username} to {username}")

                    # 2) delete the preload account
                    preload.delete()
                    logger.info(f"Deleted preload user {preload_username}")

            return user


    def get_user(self, user_id):
        """
        Retrieve a Django user based on their user ID.

        Args:
            user_id (int): The primary key (ID) of the user.

        Returns:
            User object if the user exists, or None if they do not.
        """
        User = get_user_model()
        try:
            # Attempt to retrieve the user by ID
            logger.info(f"Fetching user with ID {user_id} from Django database.")
            # print(f"Fetching user with ID {user_id} from Django database.")
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            # If the user doesn't exist, log and return None
            logger.warning(f"User with ID {user_id} not found in database.")
            print(f"User with ID {user_id} not found in database.")
            return None
