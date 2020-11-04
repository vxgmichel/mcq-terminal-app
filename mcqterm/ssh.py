"""
Provide an SSH server that lets clients claim a username by uploading a public key.
"""

import asyncssh
import structlog

from pathvalidate import sanitize_filename

LOGGER = structlog.get_logger()

ADD_AUTHORIZED_KEYS_HELP = """\
You are not using public key authentification.
In order to claim the {username!r} username, please use one of the following command:

    ssh-copy-id -p {port} {username}@{hostname}
    ssh -p {port} {username}@{hostname} add-authorized-keys < ~/.ssh/id_rsa.pub
"""


def show_add_authorized_keys_help(process):
    # Help with add-authorized-keys command
    username = process.get_extra_info("username")
    external_address = process.get_extra_info("external_address")
    if external_address is None:
        hostname, port = process.get_extra_info("sockname")
    elif ":" in external_address:
        hostname, port = external_address.split(":")
    else:
        hostname, port = external_address, 22
    message = ADD_AUTHORIZED_KEYS_HELP.format(
        username=username, hostname=hostname, port=port
    )
    print(message, file=process.stdout)


class UserClaimableSSHServer(asyncssh.SSHServer):

    def __init__(
        self,
        authenticated_process_factory,
        user_claim_password,
        external_address,
        authorized_keys_dir,
            extra_config,
    ):
        self._log_info = {}
        self._extra_config = extra_config
        self._external_address = external_address
        self._user_claim_password = user_claim_password
        self._authorized_keys_dir = authorized_keys_dir
        self._authenticated_process_factory = authenticated_process_factory

    def connection_made(self, conn):
        self._conn = conn
        self._conn.set_extra_info(log_info=self._log_info)
        self._conn.set_extra_info(extra_config=self._extra_config)
        self._conn.set_extra_info(external_address=self._external_address)
        peername = conn.get_extra_info("peername")
        self._log_info["peer_hostname"], self._log_info["peer_port"] = peername
        LOGGER.info(f"Connection made", **self._log_info)

    def begin_auth(self, username):
        username = sanitize_filename(username)
        self._log_info["username"] = username
        LOGGER.info(f"Begin authentification", **self._log_info)
        try:
            self._conn.set_authorized_keys(f"./authorized_keys/{username}")
        except (OSError, ValueError):
            pass
        return True

    def password_auth_supported(self):
        return bool(self._user_claim_password and not self._conn._client_keys)

    def validate_password(self, username, password):
        result = password == self._user_claim_password
        if result:
            self._conn.set_extra_info(password_auth_used=True)
        self._log_info["password_auth_used"] = result
        return result

    def session_requested(self):
        return asyncssh.SSHServerProcess(self.process_handler, None, None)

    def connection_lost(self, conn):
        LOGGER.info(f"Connection lost", **self._log_info)

    # Process methods

    async def process_handler(self, process):
        # Sanitize username
        username = sanitize_filename(self._conn.get_extra_info("username"))
        username = self._conn.set_extra_info(username=username)
        self._log_info["command"] = process.command
        try:
            if process.command is None:
                LOGGER.info("Running shell", **self._log_info)
                return await self.process_shell_handler(process)
            else:
                LOGGER.info(f"Running command", **self._log_info)
                return await self.process_command_handler(process, process.command)
        except Exception:
            LOGGER.exception("Unexpected exception in process handler", **self._log_info)
            return process.exit(1)

    async def process_command_handler(self, process, command):
        # Add authorized keys
        if (
            "echo >> .ssh/authorized_keys" in process.command
            or "add-authorized-keys" in process.command
        ):
            username = process.get_extra_info("username")
            stdin = await process.stdin.read()
            if not stdin.endswith("\n"):
                stdin += "\n"
            filename = sanitize_filename(username)
            self._authorized_keys_dir.mkdir(parents=True, exist_ok=True)
            with open(self._authorized_keys_dir / filename, "a") as f:
                f.write(stdin)
            return process.exit(0)

        # Unsupported command
        print(f"Command {command!r} is not supported.", file=process.stdout)

        # Already using public key authentification
        if not process.get_extra_info("password_auth_used"):
            return process.exit(1)

        # Show add-authorized-keys help
        print(file=process.stdout)
        show_add_authorized_keys_help(process)
        return process.exit(1)

    async def process_shell_handler(self, process):
        # Require public key authentification for shell requests
        if process.get_extra_info("password_auth_used"):
            show_add_authorized_keys_help(process)
            return process.exit(1)

        # Require a pseudo-terminal for shell requests
        if process.get_terminal_type() is None:
            print(
                "Please use a terminal to access the interactive interface.",
                file=process.stdout,
            )
            return process.exit(1)

        # Run the shell handler
        result = await self._authenticated_process_factory(process)

        # Exit with the proper result code
        return process.exit(result or 0)


async def create_user_claimable_ssh_server(
    authenticated_process_factory,
    bind="localhost",
    port=8022,
    user_claim_password=None,
    external_address=None,
    server_host_keys=[],
    authorized_keys_dir=None,
    extra_config=None,
):
    def instanciate_ssh_server():
        return UserClaimableSSHServer(
            authenticated_process_factory,
            user_claim_password=user_claim_password,
            external_address=external_address,
            authorized_keys_dir=authorized_keys_dir,
            extra_config=extra_config,
        )

    return await asyncssh.create_server(
        instanciate_ssh_server,
        bind,
        port,
        server_host_keys=server_host_keys,
    )
