import logging
import os

__version__ = "1.0.0"

logger = logging.getLogger(__name__)
_session_key_cache = None
_upload_mode_cache = None
_upload_initialized = False
_session_key_init = False
_launcher_patched = False
_multiserver_patched = False


def _initialize_configuration():
    global _session_key_cache, _upload_mode_cache, _session_key_init
    if _session_key_init:
        return _session_key_cache, _upload_mode_cache
    _session_key_init = True
    try:
        from .UploaderConfig import is_enabled, get_session_key, get_upload_mode, load_uploader_config
        load_uploader_config()
        if not is_enabled():
            _session_key_cache = None
            _upload_mode_cache = None
            return None, None
        _upload_mode_cache = get_upload_mode()
        _session_key_cache = get_session_key()
        return _session_key_cache, _upload_mode_cache
    except Exception as e:
        logger.error("[ArchipelagoUploader] Failed to initialize configuration")
        _session_key_cache = None
        _upload_mode_cache = None
        return None, None


def _patch_main_for_upload():
    global _upload_initialized
    if _upload_initialized:
        return
    _upload_initialized = True
    try:
        import Main
        original_main = Main.main
        def patched_main(args, seed=None, baked_server_options=None):
            result = original_main(args, seed, baked_server_options)
            try:
                if result:
                    multiworld = result
                    zipfilename = f"output/AP_{multiworld.seed_name}.zip"
                    _attempt_auto_upload(multiworld, zipfilename)
            except Exception as e:
                pass
            return result
        Main.main = patched_main
        logger.info("[ArchipelagoUploader] Patched Main.main()")
    except Exception as e:
        logger.error(f"[ArchipelagoUploader] Failed to patch Main: {e}")


def _attempt_auto_upload(multiworld, filename: str):
    import glob
    try:
        from .UploaderConfig import is_enabled
        if not is_enabled():
            return
    except Exception as e:
        logger.debug(f"Failed to check if uploader is enabled: {e}")
    upload_mode = _upload_mode_cache
    session_key = _session_key_cache
    zip_path = None
    if filename and os.path.exists(filename):
        zip_path = filename
    if not zip_path:
        try:
            zip_files = glob.glob("output/AP_*.zip")
            if zip_files:
                zip_path = max(zip_files, key=lambda f: os.path.getmtime(f))
        except Exception as e:
            logger.debug(f"Could not search for zip files: {e}")
    if not zip_path:
        return
    if upload_mode == "prompt":
        from .SessionKeyDialog import show_upload_mode_dialog
        try:
            upload_mode = show_upload_mode_dialog()
        except Exception as e:
            pass
            return
    if upload_mode == "none":
        return
    if upload_mode in ("online", "online-room"):
        if not session_key:
            from .SessionKeyDialog import show_session_key_dialog
            try:
                session_key = show_session_key_dialog(first_time=False)
            except Exception as e:
                pass
                return
            if not session_key:
                if upload_mode == "online-room":
                    logger.error("[ArchipelagoUploader] Session key is required for online-room mode")
                return
    if upload_mode == "online":
        _handle_online_upload(zip_path, session_key)
    elif upload_mode == "online-room":
        _handle_online_room_upload(zip_path, session_key)
    elif upload_mode == "local":
        _handle_local_upload(zip_path)


def _handle_online_upload(zip_path: str, session_key: str):
    try:
        from .UploadUtils import upload_multiworld_to_site, open_room_in_browser
        from .UploaderConfig import get_upload_domain
        domain = get_upload_domain()
        result = upload_multiworld_to_site(zip_path=zip_path, session_key=session_key, domain=domain)
        logger.info("[ArchipelagoUploader] Upload successful")
        open_room_in_browser(result['room_url'])
    except Exception as e:
        logger.warning(f"[ArchipelagoUploader] Online upload failed: {e}")


def _handle_online_room_upload(zip_path: str, session_key: str):
    if not session_key:
        logger.error("[ArchipelagoUploader] Session key is required for online-room mode")
        return
    try:
        from .UploadUtils import upload_multiworld_to_site, open_room_in_browser
        from .UploaderConfig import get_upload_domain
        domain = get_upload_domain()
        result = upload_multiworld_to_site(zip_path=zip_path, session_key=session_key, domain=domain, create_room=True)
        open_room_in_browser(result['room_url'])
    except Exception as e:
        logger.warning(f"[ArchipelagoUploader] Online-room upload failed: {e}")


def _handle_local_upload(zip_path: str):
    try:
        from .UploadUtils import extract_and_open_local
        server_file = extract_and_open_local(zip_path)
        if not server_file:
            logger.info("ArchipelagoUploader: Extracted to local_server directory")
    except Exception as e:
        logger.warning(f"[ArchipelagoUploader] Local upload failed: {e}")


def _is_first_time_install() -> bool:
    try:
        from .UploaderConfig import _load_host_yaml
        config = _load_host_yaml()
        return "archipelago_uploader" not in config
    except Exception:
        return False


def _patch_launcher_for_first_time_prompt():
    global _launcher_patched
    if _launcher_patched:
        return
    _launcher_patched = True
    if not _is_first_time_install():
        return
    try:
        import Launcher
        original_run_gui = Launcher.run_gui
        def patched_run_gui(launch_components=None, args=None):
            result = original_run_gui(launch_components, args)
            return result
        Launcher.run_gui = patched_run_gui
        _show_first_time_in_launcher()
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"[ArchipelagoUploader] Failed to patch Launcher: {e}")


def _show_first_time_in_launcher():
    import threading, time
    def show_prompt():
        time.sleep(1)
        try:
            from Utils import messagebox
            messagebox("Auto-Uploader Installed", "The Archipelago Auto-Uploader has been installed!\n\nTo configure it, edit your host.yaml file and look for the 'archipelago_uploader' section.\n\nNote: online-room mode requires a valid session key to create rooms on your behalf.", error=False)
        except Exception:
            pass
    thread = threading.Thread(target=show_prompt, daemon=True)
    thread.start()


def _patch_multiserver_for_auto_local():
    global _multiserver_patched
    if _multiserver_patched:
        return
    _multiserver_patched = True
    
    try:
        import MultiServer
        import atexit
        import shutil
        original_parse_args = MultiServer.parse_args
        def patched_parse_args():
            args = original_parse_args()
            if not hasattr(args, 'auto_local'):
                args.auto_local = False
            return args
        MultiServer.parse_args = patched_parse_args
        original_main = MultiServer.main
        async def patched_main(args):
            if hasattr(args, 'auto_local') and args.auto_local:
                local_server_path = os.path.join(os.getcwd(), 'local_server')
                if os.path.exists(local_server_path):
                    try:
                        shutil.rmtree(local_server_path)
                    except Exception as e:
                        logger.warning(f"Failed to cleanup {local_server_path}: {e}")
                args.multidata = local_server_path
                def cleanup_local_server():
                    try:
                        if os.path.exists(local_server_path):
                            shutil.rmtree(local_server_path)
                    except Exception as e:
                        logger.warning(f"Failed to cleanup: {e}")
                atexit.register(cleanup_local_server)
            else:
                local_server_path = os.path.join(os.getcwd(), 'local_server')
                if os.path.exists(local_server_path):
                    def cleanup_local_server():
                        try:
                            if os.path.exists(local_server_path):
                                shutil.rmtree(local_server_path)
                        except Exception as e:
                            logger.warning(f"Failed to cleanup: {e}")
                    atexit.register(cleanup_local_server)
            return await original_main(args)
        MultiServer.main = patched_main
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"[ArchipelagoUploader] Failed to patch MultiServer: {e}")
    
    _multiserver_patched = True


# Initialize on module import
_initialize_configuration()
_patch_main_for_upload()
_patch_launcher_for_first_time_prompt()
_patch_multiserver_for_auto_local()
logger.info("[ArchipelagoUploader] Ready")

__all__ = [
    "UploadUtils",
    "SessionKeyDialog",
    "UploaderConfig",
]



