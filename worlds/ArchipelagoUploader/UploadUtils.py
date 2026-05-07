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
    """Base exception for upload-related errors"""
    pass


class UploadNetworkError(UploadError):
    """Raised when network communication fails"""
    pass


class UploadValidationError(UploadError):
    """Raised when the zip file fails validation"""
    pass


class UploadAuthError(UploadError):
    """Raised when authentication (session key) fails"""
    pass


def upload_multiworld_to_site(
    zip_path: str,
    session_key: str,
    domain: str = "https://archipelago.gg",
    timeout: int = 30,
    create_room: bool = False
) -> Dict[str, Any]:
    """
    Upload a multiworld zip file to the Archipelago website.
    
    Args:
        zip_path: Path to the .zip file to upload
        session_key: Session UUID for authentication (obtained from /session page)
        domain: Archipelago website domain (default: official website)
        timeout: Request timeout in seconds
        create_room: If True, automatically create a room after upload and return room URL
    
    Returns:
        Dictionary containing:
        - seed_id: ID of the generated seed
        - room_id: ID of the created room (if create_room=True)
        - status_url: URL to check generation status
        - room_url: URL to the created room (if create_room=True), or seed page URL
        - wait_api_url: API URL to poll for generation completion
    
    Raises:
        UploadValidationError: If zip file is invalid
        UploadAuthError: If session key is invalid or rejected
        UploadNetworkError: If network communication fails
        UploadError: For other upload errors
    """
    
    # Validate zip file exists
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
        # First, establish the session by visiting /session/{key}
        logger.debug(f"Establishing session with key {session_key[:8]}...")
        session_url = f"{domain}/session/{session_key}"
        
        session = requests.Session()
        session_response = session.get(session_url, timeout=timeout, allow_redirects=False)
        
        if session_response.status_code not in (200, 302, 303):
            # Session key might be invalid
            logger.warning(f"[ArchipelagoUploader] Session establishment: {session_response.status_code}")
        
        logger.debug(f"Session established, uploading...")
        
        upload_url = f"{domain}/uploads"
        
        # Prepare the file for upload
        # The session is now established via the requests.Session() object
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
        
        # The /uploads endpoint returns a redirect (302 or 303) on success
        # It can point to either /view_seed/{seed_id} or /seed/{seed_hash}
        if response.status_code in (302, 303):
            # Success! Extract seed ID/hash from Location header
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
            
            # If create_room is requested, attempt to create a room automatically
            if create_room:
                logger.info(f"[ArchipelagoUploader] Creating room for seed {seed_id}")
                room_result = create_room_for_seed(domain, seed_id, session, timeout)
                if room_result:
                    return room_result
                else:
                    # Fall back to seed page if room creation failed
                    logger.warning("[ArchipelagoUploader] Room creation failed, returning seed page")
            
            return _build_response(domain, seed_id, session, create_room=create_room)
        
        elif response.status_code == 200:
            # Render HTML - check if there was an error message
            if 'error' in response.text.lower() or 'invalid' in response.text.lower():
                # Extract error message from HTML if possible
                logger.debug(f"Upload returned HTML (possible error)")
                raise UploadValidationError("Upload failed - check file format and size")
            else:
                # Likely a re-render of the form without a redirect (shouldn't happen)
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
    """
    Create a room for a seed and return the room URL.
    
    Args:
        domain: Archipelago website domain
        seed_id: The seed ID to create a room from
        session: Optional requests.Session object for maintaining authentication
        timeout: Request timeout in seconds
    
    Returns:
        Dictionary with room info if successful, None otherwise
    """
    try:
        if session is None:
            import requests
            session = requests.Session()
        
        new_room_url = f"{domain}/new_room/{seed_id}"
        logger.debug(f"Creating room: GET {new_room_url}")
        
        # /new_room/{seed} redirects to the actual room page
        # Follow the redirect to get the final URL
        response = session.get(new_room_url, timeout=timeout, allow_redirects=True)
        
        if response.status_code == 200:
            # Extract room ID from the final URL
            final_url = response.url
            logger.debug(f"Final URL after redirect: {final_url}")
            
            # The final URL should be /room/{room_id}
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
    """
    Build a normalized response dictionary for successful uploads.
    
    Args:
        domain: Archipelago website domain
        seed_id: The seed ID/hash from successful upload
        session: Optional requests.Session object for opening authenticated URLs
        create_room: Whether a room was created (affects response structure)
    
    Returns:
        Dictionary with upload results
    """
    # Construct seed page URL - this is where "create new room" button will be
    seed_page_url = f"{domain}/seed/{seed_id}"
    
    logger.debug(f"Seed page URL: {seed_page_url}")
    
    return {
        'seed_id': seed_id,
        'room_id': None,  # Not available for regular uploads
        'status_url': seed_page_url,
        'wait_api_url': f"{domain}/api/status/{seed_id}",
        'room_url': seed_page_url,  # This is where user creates the room
    }


def get_room_status(
    domain: str,
    seed_id: str,
    timeout: int = 30
) -> Optional[Dict[str, Any]]:
    """
    Check the status of a seed/generation on the website.
    
    Args:
        domain: Archipelago website domain
        seed_id: Seed ID to check
        timeout: Request timeout in seconds
    
    Returns:
        Dictionary with room/seed status, or None if not ready
    """
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
    """
    Construct the URL to access a room on the website.
    
    Args:
        domain: Archipelago website domain
        room_id: Room ID
    
    Returns:
        Full URL to the room
    """
    # Remove trailing slashes
    domain = domain.rstrip('/')
    return f"{domain}/room/{room_id}"


def open_room_in_browser(url: str) -> bool:
    """
    Open a room URL in the default web browser.
    
    Args:
        url: Full URL to open
    
    Returns:
        True if browser opened successfully, False otherwise
    """
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
    """
    Poll the website until a seed generation is complete and a room is created.
    
    Args:
        domain: Archipelago website domain
        seed_id: Seed ID to wait for
        timeout: Maximum time to wait in seconds
        poll_interval: Seconds between status checks
    
    Returns:
        Room ID if generation completed, None if timeout or error
    """
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
    """
    Extract the multiworld zip and open the server file with the default application.
    The file should be associated with the Archipelago Launcher for hosting.
    
    Args:
        zip_path: Path to the .zip file to extract
        output_dir: Directory to extract contents to (default: local_server)
    
    Returns:
        Path to the extracted server file if successful, None otherwise
    """
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
        
        # Extract the zip
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(output_path)
        
        logger.info(f"Successfully extracted to {output_dir}")
        
        # Find the .archipelago server file (not the launcher)
        # This file should be associated to the Archipelago Launcher
        server_file = None
        
        for file in output_path.glob("**/*.archipelago"):
            server_file = file
            break
        
        if not server_file:
            # Fallback: look for any .archipelago file in the root
            for file in output_path.glob("*.archipelago"):
                server_file = file
                break
        
        if not server_file:
            logger.warning(f"Could not find .archipelago server file in {output_dir}")
            logger.info(f"Extracted files to {output_dir}")
            logger.info("Please open the .archipelago file with Archipelago Launcher to host the room")
            return None
        
        logger.info(f"Opening server file: {server_file}")
        
        # Open the file with the default application (should be Archipelago Launcher)
        try:
            if os.name == 'nt':  # Windows
                os.startfile(str(server_file))
            else:  # macOS and Linux
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
    """
    DEPRECATED: Use extract_and_open_local() instead.
    
    This function is kept for backward compatibility but now just calls extract_and_open_local.
    
    Args:
        zip_path: Path to the .zip file to extract
        output_dir: Directory to extract contents to (default: local_server)
    
    Returns:
        True if extraction succeeded, False otherwise
    """
    logger.debug("extract_and_launch_local() called (deprecated, use extract_and_open_local)")
    result = extract_and_open_local(zip_path, output_dir)
    return result is not None
