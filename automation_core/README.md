🔐 Setting Up Credentials for IPAM Access

The auth.py module retrieves encrypted credentials from a local configuration file located at:

    ~/.config/credential.ini

This file must be created manually and securely stored. It contains:
- A cryptographic key used for encryption/decryption
- One or more credential sections (e.g., [IPAM], [HPE_OOB])

Example credential.ini Structure:
```
	[KEY]
	crypto_key = my-generated-fernet-keystring

	[IPAM]
	hash_usr = gAAAAABk...
	hash_pwd = gAAAAABl...

	[HPE_OOB]
	hash_usr = gAAAAABm...
	hash_pwd = gAAAAABn...
```

🔐 How to Generate and Encrypt Credentials:
1.  Generate a cryptographic key (only once):
```
	from cryptography.fernet import Fernet
	key = Fernet.generate_key()
	print(key.decode())  # copy this string to your [KEY] section
```
2.  Encrypt your username and password:
```
	from cryptography.fernet import Fernet
	key = b'your-copied-key-from-above'
	f = Fernet(key)

	encrypted_usr = f.encrypt(b'your-username').decode()
	encrypted_pwd = f.encrypt(b'your-password').decode()

	print(encrypted_usr)
	print(encrypted_pwd)
```
3. Paste the encrypted values into the corresponding section of your credential.ini file.

🔒 Security Notes
- Store credential.ini under the current user’s home directory: ~/.config/credential.ini
- Set restrictive permissions:
```
	chmod 600 ~/.config/credential.ini
```
- Never commit this file to Git. Add the following to your .gitignore:
```
	*.ini
```
    
