# credential_config.py
from cryptography.fernet import Fernet
import configparser
import logging
import os

# encrypt_credentials.py
def generate_key():
    return Fernet.generate_key()

def encrypt_value(fernet, value):
    return fernet.encrypt(value.encode()).decode()

def write_config_file(config_path, key, credentials):
    config = configparser.ConfigParser()
    config['KEY'] = {"crypto_key": key.decode()}

    for section, (username, password) in credentials.items():
        fernet = Fernet(key)
        config[section] = {
            "hash_usr": encrypt_value(fernet, username),
            "hash_pwd": encrypt_value(fernet, password)
        }

    with open(config_path, 'w') as configfile:
        config.write(configfile)
    print(f"Credential file written to: {config_path}")

if __name__ == "__main__":
    # Default config path
    home = os.getenv("HOME")
    config_file = os.path.join(home, ".config", "credential.ini")

    # Ensure config directory exists
    os.makedirs(os.path.dirname(config_file), exist_ok=True)

    # Generate encryption key
    crypto_key = generate_key()

    # Define credentials to write (you can customize this input method)
    credentials = {
        "IPAM": ("your-ipam-username", "your-ipam-password"),
        "HPE_OOB": ("your-oob-username", "your-oob-password")
    }

    # Write config file
    write_config_file(config_file, crypto_key, credentials)

    print("Done. Remember to set permissions:")
    print(f"chmod 600 {config_file}")