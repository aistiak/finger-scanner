import requests

url = "http://127.0.0.1:18080/enroll"

try:
    response = requests.post(url, timeout=30)  # waits until finger is placed
    response.raise_for_status()
    data = response.json()
    print("Enroll success!")
    print("User finger template (Base64):", data["template_b64"][:80], "...")  # truncated
    print("Finger index:", data["finger_index"])
    print("Device SN:", data["device_sn"])
    print("Algorithm:", data["algorithm"])
except Exception as e:
    print("Error:", e)
