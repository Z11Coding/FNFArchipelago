"""
Session Key Dialog for Archipelago Uploader.
Shows a Kivy window for session key input or falls back to console input.
"""

from typing import Optional
import logging
import sys
import threading
import time

logger = logging.getLogger(__name__)


def show_session_key_dialog(first_time: bool = False) -> Optional[str]:
    """
    Display a dialog prompting the user to enter their Archipelago session key.
    
    If running in a Kivy app context (like the launcher), shows a separate window.
    Otherwise falls back to console input.
    
    Args:
        first_time: If True, shows additional info about Auto-Uploader on first setup
    
    Returns:
        The session key string if the user enters one,
        None if the user dismisses the dialog or skips.
    """
    try:
        from kivy.app import App
        app = App.get_running_app()
        if app is not None:
            return _show_kivy_dialog_threaded(first_time=first_time)
        else:
            return _show_kivy_standalone_app(first_time=first_time)
    except (ImportError, Exception):
        pass
    return _show_console_prompt(first_time=first_time)


def _show_kivy_dialog_threaded(first_time: bool = False) -> Optional[str]:
    """
    Display Kivy dialog in a separate thread while keeping the main app responsive.
    Used when called from within a running Kivy app (like the launcher).
    
    Args:
        first_time: If True, shows additional info about Auto-Uploader on first setup
    """
    result = [None]
    error = [None]
    event = threading.Event()
    def run_dialog():
        try:
            result[0] = _show_kivy_standalone_app(first_time=first_time)
        except Exception as e:
            error[0] = e
        finally:
            event.set()
    thread = threading.Thread(target=run_dialog, daemon=False)
    thread.start()
    event.wait(timeout=600)
    if error[0]:
        raise error[0]
    return result[0]


def _show_kivy_standalone_app(first_time: bool = False) -> Optional[str]:
    """
    Display a standalone Kivy app window for session key input.
    Blocks until the user responds.
    
    Args:
        first_time: If True, shows additional info about Auto-Uploader on first setup
    
    Raises:
        ImportError: If Kivy is not available
        Exception: If window creation fails
    """
    from kivy.app import App
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.textinput import TextInput
    from kivy.uix.label import Label
    from kivy.uix.button import Button
    from kivy.metrics import dp
    from kivy.core.window import Window
    
    result = [None]
    
    class SessionKeyDialogApp(App):
        """Standalone app for session key input"""
        
        def build(self):
            try:
                self.title = 'Archipelago Auto-Upload Setup'
                
                root = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(15))
                
                # Title label
                title_label = Label(
                    text='Enter Archipelago Session Key',
                    size_hint_y=0.15,
                    bold=True,
                    font_size='18sp'
                )
                root.add_widget(title_label)
                
                # Build instructions text
                if first_time:
                    instructions_text = (
                        'You have installed Auto-Uploader!\n\n'
                        'This tool automatically uploads your generated seeds to\n'
                        'archipelago.gg and opens them in your browser.\n\n'
                        'To enable this, we need your Website Session Key to\n'
                        'tag the upload as yours so you can access the console.\n\n'
                        'To obtain your session key:\n'
                        '1. Log into archipelago.gg\n'
                        '2. Visit: https://archipelago.gg/session\n'
                        '3. Copy the UUID displayed\n\n'
                        'Tip: You can add this key to host.yaml in the\n'
                        'archipelago_uploader section to skip this prompt.\n\n'
                        'Or leave blank to skip.'
                    )
                else:
                    instructions_text = (
                        'To obtain your session key:\n\n'
                        '1. Log into archipelago.gg\n'
                        '2. Visit: https://archipelago.gg/session\n'
                        '3. Copy the UUID displayed\n\n'
                        'Tip: You can add this key to host.yaml in the\n'
                        'archipelago_uploader section to skip this prompt.\n\n'
                        'Or leave blank to skip.'
                    )
                
                # Instructions label
                instructions = Label(
                    text=instructions_text,
                    size_hint_y=0.5 if first_time else 0.45,
                    text_size=(dp(350), None)
                )
                root.add_widget(instructions)
                
                # Input field
                self.text_input = TextInput(
                    hint_text='Paste your session UUID here',
                    multiline=False,
                    size_hint_y=0.12
                )
                root.add_widget(self.text_input)
                
                # Buttons layout
                buttons_layout = BoxLayout(size_hint_y=0.15, spacing=dp(10))
                
                ok_button = Button(text='OK', size_hint_x=0.5)
                ok_button.bind(on_press=self.on_ok_press)
                buttons_layout.add_widget(ok_button)
                
                skip_button = Button(text='Skip', size_hint_x=0.5)
                skip_button.bind(on_press=self.on_skip_press)
                buttons_layout.add_widget(skip_button)
                
                root.add_widget(buttons_layout)
                
                # Set window size
                Window.size = (400, 400)
                
                logger.debug("Dialog window built successfully")
                return root
            except Exception as e:
                logger.error(f"[ArchipelagoUploader] Error building dialog: {e}", exc_info=True)
                raise
        
        def on_ok_press(self, instance):
            """Handler for OK button press"""
            try:
                result[0] = self.text_input.text.strip() if self.text_input.text.strip() else None
                logger.debug(f"OK pressed - result set to: {bool(result[0])}") 
            except Exception as e:
                logger.error(f"[ArchipelagoUploader] Error in on_ok_press: {e}", exc_info=True)
            finally:
                self.stop()
        
        def on_skip_press(self, instance):
            """Handler for Skip button press"""
            try:
                result[0] = None
                logger.debug("Skip pressed - result set to None")
            except Exception as e:
                logger.error(f"[ArchipelagoUploader] Error in on_skip_press: {e}", exc_info=True)
            finally:
                self.stop()
    
    # Create and run the dialog app
    try:
        logger.debug("Creating SessionKeyDialogApp")
        dialog_app = SessionKeyDialogApp()
        logger.debug("Running dialog app")
        dialog_app.run()
        logger.debug(f"Dialog app closed, result: {bool(result[0])}")
    except Exception as e:
        logger.error(f"[ArchipelagoUploader] Exception in Kivy dialog: {type(e).__name__}: {e}", exc_info=True)
        raise
    
    logger.debug("Session key dialog closed")
    return result[0]


def _show_console_prompt(first_time: bool = False) -> Optional[str]:
    """
    Display a console-based prompt for session key input.
    Used when Kivy is not available or not running.
    
    Args:
        first_time: If True, shows additional info about Auto-Uploader on first setup
    
    Returns:
        Session key if provided, None otherwise
    """
    print("\n" + "="*60)
    if first_time:
        print("You have installed Auto-Uploader!")
        print("="*60)
        print("\nThis tool automatically uploads your generated seeds to")
        print("archipelago.gg and opens them in your browser.")
        print("\nTo enable this, we need your Website Session Key to")
        print("tag the upload as yours so you can access the console.")
        print("\nTo obtain your session key:")
    else:
        print("Archipelago Auto-Upload: Session Key Required")
        print("="*60)
        print("\nTo enable auto-upload, provide your Archipelago session key:")
        print("\nTo obtain your session key:")
    print("\n1. Log into https://archipelago.gg")
    print("2. Visit: https://archipelago.gg/session")
    print("3. Copy the UUID displayed")
    print("\nTip: You can add this key to host.yaml in the")
    print("archipelago_uploader section to skip this prompt.")
    print("\n" + "-"*60)
    
    try:
        key = input("Paste your session UUID (or press Enter to skip): ").strip()
        print("-"*60 + "\n")
        
        if key:
            logger.debug("Session key provided via console")
            return key
        else:
            logger.debug("User skipped session key entry")
            return None
    
    except (EOFError, KeyboardInterrupt):
        logger.debug("Session key prompt cancelled")
        return None


def show_upload_mode_dialog() -> str:
    """
    Display a dialog prompting the user to choose how to handle auto-upload.
    
    NOTE: This dialog is informational only - the "prompt" setting will persist
    in host.yaml unless manually changed. To change modes permanently, edit host.yaml
    and set upload_mode to "online", "online-room", "local", or "none".
    
    Returns:
        One of: "online", "online-room", "local", "none"
        (Default to "none" if user cancels)
    """
    # Try Kivy first if we're in a Kivy app context
    try:
        from kivy.app import App
        app = App.get_running_app()
        if app is not None:
            # We're in Kivy context, show dialog in a separate thread
            logger.debug("Attempting to show Kivy mode dialog in separate window")
            return _show_kivy_mode_dialog_threaded()
        else:
            logger.debug("No Kivy app running - trying standalone mode dialog")
            return _show_kivy_mode_standalone_app()
    except ImportError as e:
        logger.debug(f"Kivy not available: {e}")
    except Exception as e:
        logger.debug(f"Kivy mode dialog failed: {type(e).__name__}: {e}")
    
    # Fall back to console input
    return _show_console_mode_prompt()


def _show_kivy_mode_dialog_threaded() -> str:
    """
    Display Kivy mode dialog in a separate thread while keeping the main app responsive.
    
    Returns:
        One of: "online", "online-room", "local", "none"
    """
    result = ["none"]  # Default
    error = [None]
    event = threading.Event()
    
    def run_dialog():
        try:
            result[0] = _show_kivy_mode_standalone_app()
        except Exception as e:
            error[0] = e
            logger.debug(f"Mode dialog thread error: {e}")
        finally:
            event.set()
    
    thread = threading.Thread(target=run_dialog, daemon=False)
    thread.start()
    
    # Wait for dialog to complete (with timeout)
    event.wait(timeout=300)  # 5 minute timeout
    
    if error[0]:
        logger.debug(f"Error in mode dialog: {error[0]}")
    
    return result[0]


def _show_kivy_mode_standalone_app() -> str:
    """
    Display a standalone Kivy app window for upload mode selection.
    Blocks until the user responds.
    
    Returns:
        One of: "online", "online-room", "local", "none"
    """
    from kivy.app import App
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.label import Label
    from kivy.uix.button import Button
    from kivy.metrics import dp
    from kivy.core.window import Window
    
    result = ["none"]  # Default
    
    class ModeDialogApp(App):
        """Standalone app for upload mode selection"""
        
        def build(self):
            try:
                self.title = 'Choose Upload Method'
                
                root = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(10))
                
                # Title label
                title_label = Label(
                    text='How should generated seeds be handled?',
                    size_hint_y=0.15,
                    bold=True,
                    font_size='16sp'
                )
                root.add_widget(title_label)
                
                # Info text
                info_text = (
                    'Choose your preference:\n\n'
                    '• Online: Upload and show seed page\n'
                    '• Online-Room: Upload and create room\n'
                    '• Local: Extract and open in launcher\n'
                    '• None: Disable auto-upload\n\n'
                    'NOTE: to change this prompt to not show up,\n'
                    'change this setting in host.yaml to one of the above options instead of "prompt".'
                )
                info_label = Label(
                    text=info_text,
                    size_hint_y=0.4,
                    text_size=(dp(350), None)
                )
                root.add_widget(info_label)
                
                # Buttons layout (4 buttons now)
                buttons_layout = BoxLayout(orientation='vertical', size_hint_y=0.45, spacing=dp(8))
                
                online_button = Button(text='Online: Upload & Show Seed', size_hint_y=0.25)
                online_button.bind(on_press=lambda x: self.on_mode_selected('online'))
                buttons_layout.add_widget(online_button)
                
                online_room_button = Button(text='Online-Room: Upload & Create Room', size_hint_y=0.25)
                online_room_button.bind(on_press=lambda x: self.on_mode_selected('online-room'))
                buttons_layout.add_widget(online_room_button)
                
                local_button = Button(text='Local: Extract & Open', size_hint_y=0.25)
                local_button.bind(on_press=lambda x: self.on_mode_selected('local'))
                buttons_layout.add_widget(local_button)
                
                none_button = Button(text='None: Disable Auto-Upload', size_hint_y=0.25)
                none_button.bind(on_press=lambda x: self.on_mode_selected('none'))
                buttons_layout.add_widget(none_button)
                
                root.add_widget(buttons_layout)
                
                # Set window size
                Window.size = (450, 500)
                
                logger.debug("Mode dialog window built successfully")
                return root
            except Exception as e:
                logger.error(f"Error building mode dialog: {e}", exc_info=True)
                raise
        
        def on_mode_selected(self, mode):
            """Handler for mode selection"""
            try:
                result[0] = mode
                logger.debug(f"Mode selected: {mode}")
            except Exception as e:
                logger.error(f"Error in on_mode_selected: {e}", exc_info=True)
            finally:
                self.stop()
    
    # Create and run the dialog app
    try:
        logger.debug("Creating ModeDialogApp")
        dialog_app = ModeDialogApp()
        logger.debug("Running mode dialog app")
        dialog_app.run()
        logger.debug(f"Mode dialog app closed, result: {result[0]}")
    except Exception as e:
        logger.error(f"Exception in Kivy mode dialog: {type(e).__name__}: {e}", exc_info=True)
        # Return default on error
        return "online"
    
    logger.debug("Mode selection dialog closed")
    return result[0]


def _show_console_mode_prompt() -> str:
    """
    Display a console-based prompt for upload mode selection.
    Used when Kivy is not available or not running.
    
    Returns:
        One of: "online", "online-room", "local", "none"
    """
    print("\n" + "="*70)
    print("Choose Upload Method")
    print("="*70)
    print("\nHow should generated seeds be handled?")
    print("\n1. online        - Upload and show seed page")
    print("2. online-room   - Upload and automatically create room")
    print("3. local         - Extract and open in Archipelago Launcher")
    print("4. none          - Disable auto-upload")
    print("\nNOTE: The 'prompt' setting will be retained in host.yaml")
    print("unless you manually change upload_mode to one of the above options.")
    print("\n" + "-"*70)
    
    try:
        while True:
            choice = input("Enter choice (1-4, or press Enter for 'online'): ").strip().lower()
            
            if not choice:
                choice = "1"
            
            if choice == "1" or choice == "online":
                logger.debug("User selected: online")
                print("-"*70 + "\n")
                return "online"
            elif choice == "2" or choice == "online-room":
                logger.debug("User selected: online-room")
                print("-"*70 + "\n")
                return "online-room"
            elif choice == "3" or choice == "local":
                logger.debug("User selected: local")
                print("-"*70 + "\n")
                return "local"
            elif choice == "4" or choice == "none":
                logger.debug("User selected: none")
                print("-"*70 + "\n")
                return "none"
            else:
                print("Invalid choice. Please enter 1, 2, 3, or 4.")
    
    except (EOFError, KeyboardInterrupt):
        logger.debug("Mode prompt cancelled, defaulting to online")
        print("\n")
        return "online"
