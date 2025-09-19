# ipam_sdk/utils/auth_cli.py
"""Get IPAM credentials via CLI, useful for testing and debugging."""

import sys
from base64 import b64encode
from getpass import getpass


def ipam_credential_cli():
    """
    Read IPAM credentials from command line interface with secure password input.
    
    Returns:
        tuple: Base64 encoded (username, password) tuple
        
    Raises:
        SystemExit: If user cancels input with Ctrl+C
    """
    try:
        f_usrname = input("Username: ")
        f_passwd = getpass("Password: ")
        f_usr = b64encode(f_usrname.encode("UTF-8")).decode("UTF-8")
        f_pwd = b64encode(f_passwd.encode("UTF-8")).decode("UTF-8")
        return f_usr, f_pwd
    except KeyboardInterrupt:
        print("User ends the program!")
        sys.exit()