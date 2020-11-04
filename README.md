MCQ Terminal Application
========================

An MCQ terminal application served over SSH.

Requires [glow](https://github.com/charmbracelet/glow/releases) to be installed and accessible.

Example usage:

```bash
# Installation
[server side]$ python3.8 -m pip install .

# Run the SSH server
[server side]$ python -m mcqterm --user-claim-password c@t example/mcq-example.md
Running an SSH server on 127.0.0.1:8022...

# Claim a username
[client side]$ ssh-copy-id -p 8022 mark@localhost
password: <enter c@t>
[...]

# Mark's public key has been stored in the `authorized_keys` directory
[server side]$ ls authorized_keys
mark

# Connect to the MCQ terminal application
[client side]$ ssh -p 8022 mark@localhost

# Mark's answers have been stored in the `results` directory
[server-side]$ ls results
mark.json
```
