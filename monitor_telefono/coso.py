from cryptography.fernet import Fernet

# 1. Generar una nueva clave segura
clave = Fernet.generate_key()
print(f"Clave generada: {clave.decode()}")