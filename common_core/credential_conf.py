# ipam_sdk/utils/credential_config.py
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

def interactive_credential_setup():
    """Interactive credential setup with user prompts."""
    import getpass
    
    print("🔐 IPAM Client Credential Configuration")
    print("=" * 40)
    print("This tool will create an encrypted credential file for secure authentication.")
    print("Your credentials will be encrypted and stored in ~/.config/credential.ini\n")
    
    # Default config path
    home = os.getenv("HOME", "")
    config_file = os.path.join(home, ".config", "credential.ini")
    
    # Check if file already exists
    if os.path.exists(config_file):
        overwrite = input(f"⚠️  Credential file already exists at {config_file}\nOverwrite? (y/N): ").strip().lower()
        if overwrite != 'y':
            print("❌ Setup cancelled.")
            return
    
    # Ensure config directory exists
    os.makedirs(os.path.dirname(config_file), exist_ok=True)
    
    # Generate encryption key
    crypto_key = generate_key()
    
    # Collect credentials interactively
    credentials = {}
    
    # IPAM credentials (required)
    print("\n📋 IPAM Server Credentials (Required)")
    print("-" * 35)
    ipam_user = input("IPAM Username: ").strip()
    if not ipam_user:
        print("❌ IPAM username is required!")
        return
    
    ipam_pass = getpass.getpass("IPAM Password: ")
    if not ipam_pass:
        print("❌ IPAM password is required!")
        return
    
    credentials["IPAM"] = (ipam_user, ipam_pass)
    
    # Optional: HPE OOB credentials
    print("\n📋 HPE OOB Credentials (Optional)")
    print("-" * 32)
    add_oob = input("Add HPE OOB credentials? (y/N): ").strip().lower()
    if add_oob == 'y':
        oob_user = input("HPE OOB Username: ").strip()
        oob_pass = getpass.getpass("HPE OOB Password: ")
        if oob_user and oob_pass:
            credentials["HPE_OOB"] = (oob_user, oob_pass)
    
    # Write config file
    write_config_file(config_file, crypto_key, credentials)
    
    # Set secure permissions
    try:
        os.chmod(config_file, 0o600)
        print(f"🔒 File permissions set to 600 (owner read/write only)")
    except Exception as e:
        print(f"⚠️  Could not set file permissions: {e}")
        print(f"Please run manually: chmod 600 {config_file}")
    
    print(f"\n✅ Setup complete! Credentials securely stored in:")
    print(f"   {config_file}")
    print(f"\n🚀 You can now use: from ipam_client.core.auth import get_credential")

def main():
    """Main entry point for credential configuration."""
    try:
        interactive_credential_setup()
    except KeyboardInterrupt:
        print("\n❌ Setup cancelled by user.")
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        logging.error(f"Credential setup error: {e}")

if __name__ == "__main__":
    main()