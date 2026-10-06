import logging

__version__ = "1.0.0"

logger = logging.getLogger(__name__)
_patched = False


def _apply_swap_slot_patch():
    global _patched
    if _patched:
        return
    _patched = True
    
    try:
        from CommonClient import ClientCommandProcessor
        
        if hasattr(ClientCommandProcessor, '_cmd_swap_slot'):
            logger.info("[ClientQuickSwap] Already patched")
            return
        
        def _cmd_swap_slot(self, new_slot: str = "") -> bool:
            if not self.ctx.server_address:
                self.output("Not connected to a server.")
                return False
            
            self.ctx.auth = None
            if new_slot:
                self.ctx.auth = new_slot
            
            from Utils import async_start
            async_start(self.ctx.connect(self.ctx.server_address), name="swapping_slot")
            return True
        
        _cmd_swap_slot.__doc__ = "Change the connected slot"
        ClientCommandProcessor._cmd_swap_slot = _cmd_swap_slot
        
        logger.info("[ClientQuickSwap] Patched CommonClient")
    except ImportError as e:
        logger.info(f"[ClientQuickSwap] CommonClient not yet imported: {e}")
    except Exception as e:
        logger.error(f"[ClientQuickSwap] Failed to patch: {e}", exc_info=True)


def _patch_main_for_client_swap():
    try:
        import Main
        original_main = Main.main
        
        def patched_main(args, seed=None, baked_server_options=None):
            logger.info("[ClientQuickSwap] Main.main called, applying patch...")
            _apply_swap_slot_patch()
            return original_main(args, seed, baked_server_options)
        
        Main.main = patched_main
        logger.info("[ClientQuickSwap] Patched Main.main")
    except Exception as e:
        logger.error(f"[ClientQuickSwap] Failed to patch Main: {e}", exc_info=True)


_apply_swap_slot_patch()
_patch_main_for_client_swap()
