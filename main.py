# FastAPI agent for ZKTeco via pyzkfp
# Endpoints:
#   POST /enroll  -> { template_b64, finger_index, device_sn, algorithm }
#   POST /verify  -> body: { candidates: [{user_id, template_b64}, ...] } -> { matched_user_id, score }

import base64, json
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="ZKT Local Agent", version="0.1")

# --- ZKFP init helpers -------------------------------------------------------
_zk = None
_db_inited = False

def _zk_init():
    global _zk, _db_inited
    if _zk is not None:
        return
    try:
        from pyzkfp import ZKFP2  # pip install pyzkfp
    except Exception as e:
        print(e)
        raise RuntimeError(f"pyzkfp not available: {e}")
    _zk = ZKFP2()
    if not _zk.Init():
        raise RuntimeError("ZKFP init() failed (check DLLs/drivers).")
    if not _zk.open_device(0):
        raise RuntimeError("open_device(0) failed (is the scanner connected?).")
    if not _zk.db_init():  # in-memory matcher
        raise RuntimeError("db_init() failed.")
    _db_inited = True

def _zk_close():
    global _zk
    if _zk:
        try:
            _zk.close_device()
            _zk.terminate()
        except:  # noqa
            pass
        _zk = None

# --- Schemas -----------------------------------------------------------------
class Candidate(BaseModel):
    user_id: str
    template_b64: str

class VerifyReq(BaseModel):
    candidates: List[Candidate]

# --- Endpoints ---------------------------------------------------------------
@app.post("/enroll")
def enroll():
    """Capture one finger; return template."""
    try:
        _zk_init()
        print("zk init done")
        # capture returns (template_bytes, image_bytes) or just template; depends on SDK
        tpl, _img = _zk.acquire_fingerprint()  # may bslock until finger captured
        if not tpl:
            raise HTTPException(500, "Failed to acquire fingerprint (try again).")
        tpl_b64 = base64.b64encode(tpl).decode()
        resp = {
            "template_b64": tpl_b64,
            "finger_index": "RIGHT_THUMB",  # set by UI if you want
            "device_sn": _zk.get_device_sn() or "",
            "algorithm": "ANSI-378"         # typical; adjust per SDK/device config
        }
        return resp
    except Exception as e:
        raise HTTPException(500, f"Enroll error: {e}")

@app.post("/verify")
def verify(req: VerifyReq):
    """1:N identify against provided candidates; returns best match."""
    try:
        _zk_init()
        if not req.candidates:
            raise HTTPException(400, "No candidates provided.")

        # capture probe template
        probe_tpl, _ = _zk.acquire_fingerprint()
        if not probe_tpl:
            raise HTTPException(500, "Failed to capture probe fingerprint.")

        # (Re)build in-memory DB for this request
        _zk.db_clear()
        idmap = []
        for idx, c in enumerate(req.candidates, start=1):
            try:
                tpl = base64.b64decode(c.template_b64)
                _zk.db_add(idx, tpl)   # assign an integer id inside matcher DB
                idmap.append((idx, c.user_id))
            except Exception:
                continue

        # Identify best match
        match_id, score = _zk.db_identify(probe_tpl)  # returns (int_id, score) or (0, 0) if no match
        if match_id <= 0:
            return { "matched_user_id": None, "score": 0 }

        # map back to user_id
        uid = next((u for i,u in idmap if i == match_id), None)
        return { "matched_user_id": uid, "score": int(score) }
    except Exception as e:
        raise HTTPException(500, f"Verify error: {e}")


_zk_init()