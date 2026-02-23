"""
Worker functions for fingerprint registration and match.
In a separate module so multiprocessing spawn (PyInstaller exe) can import them by name.
"""
import base64


def _registration_worker_process(progress_queue, result_queue):
    """
    Run in a separate process so device handles are fully released when process exits.
    progress_queue: put progress messages (str). result_queue: put ('ok', template_b64) or ('error', message).
    """
    try:
        from pyzkfp import ZKFP2
        progress_queue.put("🔧 Initializing fingerprint device...")
        zkfp2 = ZKFP2()
        zkfp2.Init()
        progress_queue.put("⚙️ Opening device...")
        zkfp2.OpenDevice(0)
        progress_queue.put("✅ Device connected successfully")
        templates = []
        for i in range(3):
            progress_queue.put(f"👆 Place finger {i+1}/3 - Waiting for finger on scanner...")
            while True:
                capture = zkfp2.AcquireFingerprint()
                if capture:
                    templates.append(capture[0])
                    progress_queue.put(f"✅ Finger {i+1}/3 captured successfully! Please lift your finger.")
                    break
        progress_queue.put("🔄 Processing fingerprint template...")
        reg_temp, _ = zkfp2.DBMerge(*templates)
        template_b64 = base64.b64encode(bytes(reg_temp)).decode('utf-8')
        try:
            zkfp2.Terminate()
        except Exception:
            pass
        result_queue.put(('ok', template_b64))
    except Exception as e:
        result_queue.put(('error', str(e)))


def _match_worker_process(progress_queue, result_queue, stored_template_b64):
    """
    Run in a separate process so device handles are fully released when process exits.
    progress_queue: progress messages (str). result_queue: ('ok', True/False) or ('error', message).
    stored_template_b64: base64 string of the stored template to match against.
    """
    try:
        from pyzkfp import ZKFP2
        stored_template = base64.b64decode(stored_template_b64)
        progress_queue.put("🔧 Initializing fingerprint device...")
        zkfp2 = ZKFP2()
        zkfp2.Init()
        progress_queue.put("⚙️ Opening device...")
        zkfp2.OpenDevice(0)
        progress_queue.put("✅ Device connected successfully")
        templates = []
        for i in range(3):
            progress_queue.put(f"👆 Place finger {i+1}/3 - Waiting for finger on scanner...")
            while True:
                capture = zkfp2.AcquireFingerprint()
                if capture:
                    templates.append(capture[0])
                    progress_queue.put(f"✅ Finger {i+1}/3 captured successfully! Please lift your finger.")
                    break
        progress_queue.put("🔄 Processing captured fingerprint...")
        live_template, _ = zkfp2.DBMerge(*templates)
        progress_queue.put("🔍 Comparing fingerprints...")
        match_result = zkfp2.DBMatch(stored_template, live_template)
        try:
            zkfp2.Terminate()
        except Exception:
            pass
        result_queue.put(('ok', match_result > 0))
    except Exception as e:
        result_queue.put(('error', str(e)))
