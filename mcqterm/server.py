"""
An SSH server running the MCQ terminal application.
"""

import asyncio
import argparse
from pathlib import Path

import structlog

from .mcq import run_mcq
from .ptutils import process_to_app_session
from .ssh import create_user_claimable_ssh_server

LOGGER = structlog.get_logger()


async def run_mcq_in_ssh_process(process):
    log_info = process.get_extra_info("log_info")

    # AsyncSSH process to prompt-toolkit app session
    async with process_to_app_session(process):

        # Run a prompt-toolkit application
        try:
            config = process.get_extra_info("extra_config")
            username = process.get_extra_info("username")
            result = await run_mcq(config.mcq_filename, config.result_dir, username)

        # Make sure dangerous exceptions do not leak out of the app session
        except KeyboardInterrupt:
            LOGGER.info("User exited with a keyboard interrupt", **log_info)
            return 1
        except EOFError:
            LOGGER.info("User exited by closing the stream", **log_info)
            return 1
        except SystemExit:
            LOGGER.info("User exited by closing the stream", **log_info)
            return 1
        except Exception:
            LOGGER.exception("User exited with an unexpected error", **log_info)
            return 1
        else:
            LOGGER.info(f"User exited with result {result!r}", **log_info)

    # Cast the result to an integer
    try:
        result = int(result)
    except TypeError:
        result = bool(result)

    # Exit the SSH process
    return process.exit(result)


async def run_mcq_ssh_server(
    bind="localhost",
    port=8022,
    user_claim_password=None,
    external_address=None,
    authorized_keys_dir=Path("authorized_keys"),
    server_host_key=None,
    extra_config=None,
):
    if server_host_key is None:
        server_host_key = Path("~/.ssh/id_rsa").expanduser()
    if authorized_keys_dir is None:
        authorized_keys_dir = Path("authorized_keys")

    server = await create_user_claimable_ssh_server(
        run_mcq_in_ssh_process,
        bind=bind,
        port=port,
        external_address=external_address,
        user_claim_password=user_claim_password,
        server_host_keys=[server_host_key],
        authorized_keys_dir=authorized_keys_dir,
        extra_config=extra_config,
    )
    bind, port = server.sockets[0].getsockname()
    print(f"Running an SSH server on {bind}:{port}...")

    while True:
        await asyncio.sleep(60)


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", "-p", type=int, default=8022)
    parser.add_argument("--bind", "-b", type=str, default="localhost")
    parser.add_argument("--user-claim-password", "-u", type=str, default=None)
    parser.add_argument("--external-address", "-e", type=str, default=None)
    parser.add_argument("--authorized-keys-dir", "-a", type=Path, default=Path("authorized_keys"))
    parser.add_argument("--server-host-key", "-s", type=Path, default=None)
    parser.add_argument("--result-dir", "-r", type=Path, default=Path("results"))
    parser.add_argument("mcq_filename", metavar="MCQ_FILE", type=Path, default=None)
    namespace = parser.parse_args(args)
    assert namespace.mcq_filename.exists()
    return asyncio.run(
        run_mcq_ssh_server(
            bind=namespace.bind,
            port=namespace.port,
            user_claim_password=namespace.user_claim_password,
            external_address=namespace.external_address,
            authorized_keys_dir=namespace.authorized_keys_dir,
            server_host_key=namespace.server_host_key,
            extra_config=namespace,
        )
    )


if __name__ == "__main__":
    main()
