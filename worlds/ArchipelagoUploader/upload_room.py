#!/usr/bin/env python3
import sys
import argparse
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description='Upload multiworld zip to Archipelago',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        'zip_file',
        type=str,
        help='Path to the .zip or .archipelago file to upload'
    )
    
    parser.add_argument(
        '--session-key',
        type=str,
        default=None,
        help='Session UUID for authentication. If not provided, reads from config'
    )
    
    parser.add_argument(
        '--domain',
        type=str,
        default=None,
        help='Archipelago website domain (default: https://archipelago.gg or from config)'
    )
    
    parser.add_argument(
        '--wait',
        action='store_true',
        help='Wait for generation to complete before returning'
    )
    
    parser.add_argument(
        '--open',
        action='store_true',
        help='Open the room URL in the default browser after generation'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("[ArchipelagoUploader] Verbose logging enabled")
    try:
        from worlds.ArchipelagoUploader.UploadUtils import (
            upload_multiworld_to_site,
            wait_for_generation,
            construct_room_url,
            open_room_in_browser,
            UploadError
        )
        from worlds.ArchipelagoUploader.UploaderConfig import (
            get_session_key,
            get_upload_domain
        )
    except ImportError as e:
        logger.error(f"[ArchipelagoUploader] Failed to import uploader modules: {e}")
        logger.error("Make sure you're running this from the Archipelago directory")
        return 1
    zip_path = args.zip_file
    if not Path(zip_path).exists():
        logger.error(f"[ArchipelagoUploader] File not found: {zip_path}")
        return 1
    session_key = args.session_key
    if not session_key:
        session_key = get_session_key()
        if session_key:
            logger.info("Using session key from config")
        else:
            logger.error("[ArchipelagoUploader] No session key provided and none found in config")
            logger.error("To get your session key:")
            logger.error("  1. Log into https://archipelago.gg")
            logger.error("  2. Visit: https://archipelago.gg/session")
            logger.error("  3. Copy the UUID displayed")
            logger.error("  4. Use: --session-key <your-uuid>")
            logger.error("  Or add to ~/.archipelago/archipelago-uploader.yaml")
            return 1
    if not (len(session_key) > 10 and '-' in session_key or len(session_key) > 20):
        logger.warning(f"[ArchipelagoUploader] Session key looks suspicious (length: {len(session_key)})")
    domain = args.domain or get_upload_domain()
    
    try:
        result = upload_multiworld_to_site(
            zip_path=zip_path,
            session_key=session_key,
            domain=domain
        )
        
        logger.info(f"[ArchipelagoUploader] Upload successful!")
        logger.info(f"[ArchipelagoUploader] Seed ID: {result['seed_id']}")
        logger.info(f"[ArchipelagoUploader] Status URL: {result['status_url']}")
        room_id = result.get('room_id')
        if args.wait and not room_id:
            logger.info("[ArchipelagoUploader] Waiting for generation to complete...")
            room_id = wait_for_generation(
                domain=domain,
                seed_id=result['seed_id'],
                timeout=300
            )
            
            if not room_id:
                logger.warning(f"[ArchipelagoUploader] Generation did not complete in time")
                logger.info(f"[ArchipelagoUploader] Check status at: {result['status_url']}")
                return 1
        if args.open and room_id:
            room_url = construct_room_url(domain, room_id)
            logger.info(f"[ArchipelagoUploader] Room URL: {room_url}")
            if open_room_in_browser(room_url):
                logger.info("[ArchipelagoUploader] Browser opened successfully")
            else:
                logger.warning(f"[ArchipelagoUploader] Could not open browser. Room URL: {room_url}")
        elif room_id:
            room_url = construct_room_url(domain, room_id)
            logger.info(f"[ArchipelagoUploader] Room URL: {room_url}")
        
    except UploadError as e:
        logger.error(f"[ArchipelagoUploader] Upload failed: {e}")
        return 1
    except Exception as e:
        logger.error(f"[ArchipelagoUploader] Unexpected error: {e}", exc_info=args.verbose)
        return 1


if __name__ == '__main__':
    sys.exit(main())
