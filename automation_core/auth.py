# ipam_client/auth.py
import os
import base64
import configparser
from cryptography.fernet import Fernet
import logging
import sys

def get_credential(f_section):
    f_home_env = os.getenv("HOME")
    f_config = configparser.ConfigParser()
    f_conf_file = f"{f_home_env}/.config/credential.ini"
    try:
        f_config.read(f_conf_file)
        f_crypto_key = f_config["KEY"]["crypto_key"]
        f_crypto = Fernet(f_crypto_key)
        f_decrypted_usr = f_crypto.decrypt(f_config[f_section]["hash_usr"].encode()).decode("UTF-8")
        f_decrypted_pwd = f_crypto.decrypt(f_config[f_section]["hash_pwd"].encode()).decode("UTF-8")
        f_encode_usr = base64.b64encode(f_decrypted_usr.encode()).decode("UTF-8")
        f_encode_pwd = base64.b64encode(f_decrypted_pwd.encode()).decode("UTF-8")
    except Exception as f_error:
        logging.error(f"Retrieve credential failed. Error: {f_error}")
        sys.exit(1)
    return f_encode_usr, f_encode_pwd