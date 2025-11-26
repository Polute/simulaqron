from cqc.pythonLib import CQCConnection

print("[DEBUG] >>> Inicio prueba.py")

emisor = "node_alice"
try:
    conn = CQCConnection(emisor)
    print("[DEBUG] Objeto conexión literal:", conn)
    print("[DEBUG] __dict__ de la conexión:", conn.__dict__)
    conn.close()
except Exception as e:
    print("[DEBUG] Excepción al crear CQCConnection:", type(e).__name__, "-", e)

print("[DEBUG] <<< Fin prueba.py")
