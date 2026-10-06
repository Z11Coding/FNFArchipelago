import os
import sys
import logging
import json
import webbrowser
from typing import Optional, Dict, Any
from pathlib import Path
import time

logger = logging.getLogger(__name__)


class UploadError(Exception):
    pass


class UploadNetworkError(UploadError):
    pass


class UploadValidationError(UploadError):
    pass


class UploadAuthError(UploadError):
    pass


def upload_multiworld_to_site(
    zip_path: str,
    session_key: str,
    domain: str = "https://archipelago.gg",
    timeout: int = 30,
    create_room: bool = False
) -> Dict[str, Any]:
    if not os.path.exists(zip_path):
        raise UploadValidationError(f"Zip file not found: {zip_path}")
    
    if not zip_path.lower().endswith(('.zip', '.archipelago')):
        raise UploadValidationError(f"File must be .zip or .archipelago: {zip_path}")
    
    file_size = os.path.getsize(zip_path)
    if file_size == 0:
        raise UploadValidationError("Zip file is empty")
    
    logger.info(f"[ArchipelagoUploader] Uploading {zip_path} ({file_size} bytes) to {domain}")
    try:
        import requests
    except ImportError:
        raise UploadNetworkError("requests library not available. Install it with: pip install requests")
    
    try:
        logger.debug(f"Establishing session with key {session_key[:8]}...")
        session_url = f"{domain}/session/{session_key}"
        
        session = requests.Session()
        session_response = session.get(session_url, timeout=timeout, allow_redirects=False)
        
        if session_response.status_code not in (200, 302, 303):
            # Session key might be invalid
            logger.warning(f"[ArchipelagoUploader] Session establishment: {session_response.status_code}")
        
        logger.debug(f"Session established, uploading...")
        upload_url = f"{domain}/uploads"
        with open(zip_path, 'rb') as f:
            files = {'file': (os.path.basename(zip_path), f, 'application/zip')}
            headers = {'User-Agent': 'ArchipelagoUploader/1.0'}
            logger.debug(f"POST {upload_url}...")
            
            response = session.post(
                upload_url,
                files=files,
                headers=headers,
                timeout=timeout,
                allow_redirects=False  # Don't follow redirects, we want to see the response
            )
        
        logger.debug(f"Response status: {response.status_code}")
        if response.status_code in (302, 303):
            location = response.headers.get('Location', '')
            seed_id = None
            
            if '/view_seed/' in location:
                seed_id = location.split('/view_seed/')[-1].strip('/')
                logger.info(f"[ArchipelagoUploader] Upload successful! Seed ID: {seed_id}")
            elif '/seed/' in location:
                seed_id = location.split('/seed/')[-1].strip('/')
                logger.info(f"[ArchipelagoUploader] Upload successful! Seed hash: {seed_id}")
            else:
                raise UploadError(f"Unexpected redirect location: {location}")
            if create_room:
                logger.info(f"[ArchipelagoUploader] Creating room for seed {seed_id}")
                room_result = create_room_for_seed(domain, seed_id, session, timeout)
                if room_result:
                    return room_result
                else:
                    logger.warning("[ArchipelagoUploader] Room creation failed, returning seed page")
            
            return _build_response(domain, seed_id, session, create_room=create_room)
        
        elif response.status_code == 200:
            if 'error' in response.text.lower() or 'invalid' in response.text.lower():
                logger.debug(f"Upload returned HTML (possible error)")
                raise UploadValidationError("Upload failed - check file format and size")
            else:
                raise UploadError("Unexpected response from upload endpoint")
        
        elif response.status_code == 401 or response.status_code == 403:
            raise UploadAuthError(f"Session key is invalid or expired. Get a new one at: {domain}/session")
        
        else:
            logger.debug(f"Response content: {response.text[:500]}")
            raise UploadNetworkError(f"Unexpected response: {response.status_code}")
        
    except requests.exceptions.Timeout:
        raise UploadNetworkError("Upload request timed out. Check your internet connection.")
    except requests.exceptions.ConnectionError as e:
        raise UploadNetworkError(f"Failed to connect to {domain}: {e}")
    except requests.exceptions.RequestException as e:
        raise UploadNetworkError(f"Upload failed: {e}")


def create_room_for_seed(
    domain: str,
    seed_id: str,
    session=None,
    timeout: int = 30
) -> Optional[Dict[str, Any]]:
    try:
        if session is None:
            import requests
            session = requests.Session()
        new_room_url = f"{domain}/new_room/{seed_id}"
        response = session.get(new_room_url, timeout=timeout, allow_redirects=True)
        if response.status_code == 200:
            final_url = response.url
            logger.debug(f"Final URL after redirect: {final_url}")
            if '/room/' in final_url:
                room_id = final_url.split('/room/')[-1].strip('/')
                room_url = f"{domain}/room/{room_id}"
                logger.info(f"[ArchipelagoUploader] Room created! Room ID: {room_id}")
                
                return {
                    'seed_id': seed_id,
                    'room_id': room_id,
                    'status_url': room_url,
                    'wait_api_url': f"{domain}/api/room_status/{room_id}",
                    'room_url': room_url,
                }
        
        logger.warning(f"[ArchipelagoUploader] Room creation: {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"[ArchipelagoUploader] Failed to create room: {type(e).__name__}: {e}")
        return None


def _build_response(domain: str, seed_id: str, session=None, create_room: bool = False) -> Dict[str, Any]:
    seed_page_url = f"{domain}/seed/{seed_id}"
    
    logger.debug(f"Seed page URL: {seed_page_url}")
    return {
        'seed_id': seed_id,
        'room_id': None,
        'status_url': seed_page_url,
        'wait_api_url': f"{domain}/api/status/{seed_id}",
        'room_url': seed_page_url,
    }


def get_room_status(
    domain: str,
    seed_id: str,
    timeout: int = 30
) -> Optional[Dict[str, Any]]:
    try:
        import requests
    except ImportError:
        logger.warning("requests library not available, cannot check status")
        return None
    
    try:
        status_url = f"{domain}/api/status/{seed_id}"
        response = requests.get(status_url, timeout=timeout)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return None
        else:
            logger.warning(f"Status check failed: {response.status_code}")
            return None
            
    except Exception as e:
        logger.warning(f"[ArchipelagoUploader] Failed to check status: {e}")
        return None


def construct_room_url(domain: str, room_id: str) -> str:
    domain = domain.rstrip('/')
    return f"{domain}/room/{room_id}"


def open_room_in_browser(url: str) -> bool:
    try:
        logger.info(f"Opening {url} in browser")
        webbrowser.open(url)
        return True
    except Exception as e:
        logger.error(f"Failed to open browser: {e}")
        return False


def wait_for_generation(
    domain: str,
    seed_id: str,
    timeout: int = 300,
    poll_interval: int = 2
) -> Optional[str]:
    logger.info(f"Waiting for generation to complete (timeout: {timeout}s)...")
    start_time = time.time()
    poll_count = 0
    
    while time.time() - start_time < timeout:
        status = get_room_status(domain, seed_id)
        poll_count += 1
        
        if status:
            if 'room' in status and status['room']:
                room_id = status['room']
                logger.info(f"Generation complete! Room ID: {room_id}")
                return room_id
            elif 'status' in status:
                logger.debug(f"Status: {status['status']} (poll #{poll_count})")
        
        time.sleep(poll_interval)
    
    logger.warning(f"Generation did not complete within {timeout} seconds")
    return None


def extract_and_open_local(zip_path: str, output_dir: str = "local_server") -> Optional[str]:
    try:
        import zipfile
        from pathlib import Path
        
        # Validate zip file
        if not os.path.exists(zip_path):
            raise UploadValidationError(f"Zip file not found: {zip_path}")
        
        if not zipfile.is_zipfile(zip_path):
            raise UploadValidationError(f"File is not a valid zip: {zip_path}")
        
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Extracting {zip_path} to {output_dir}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(output_path)
        
        logger.info(f"Successfully extracted to {output_dir}")
        server_file = None
        
        for file in output_path.glob("**/*.archipelago"):
            server_file = file
            break
        if not server_file:
            for file in output_path.glob("*.archipelago"):
                server_file = file
                break
        
        if not server_file:
            logger.warning(f"Could not find .archipelago server file in {output_dir}")
            logger.info(f"Extracted files to {output_dir}")
            logger.info("Please open the .archipelago file with Archipelago Launcher to host the room")
            return None
        
        logger.info(f"Opening server file: {server_file}")
        try:
            if os.name == 'nt':
                os.startfile(str(server_file))
            else:
                import subprocess
                subprocess.Popen(['open', str(server_file)]) if sys.platform == 'darwin' else subprocess.Popen(['xdg-open', str(server_file)])
            
            logger.info(f"Opened server file with default application")
            return str(server_file)
        except Exception as e:
            logger.error(f"Failed to open server file: {e}")
            logger.info(f"Server file is at: {server_file}")
            logger.info("Please open it manually with Archipelago Launcher")
            return None
        
    except UploadValidationError:
        raise
    except Exception as e:
        logger.error(f"Failed to extract local server: {type(e).__name__}: {e}")
        raise UploadError(f"Local server extraction failed: {e}")


def extract_and_launch_local(zip_path: str, output_dir: str = "local_server") -> bool:
    logger.debug("extract_and_launch_local() called (deprecated, use extract_and_open_local)")
    result = extract_and_open_local(zip_path, output_dir)
    return result is not None
