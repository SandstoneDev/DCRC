"""Errors shared by the CLI, GUI and local build stages."""
class ConverterError(RuntimeError):
    def __init__(self, code, message, hint=''):
        self.code, self.message, self.hint = str(code), str(message), str(hint)
        super().__init__(self.message)


class Cancelled(ConverterError):
    def __init__(self, message='Conversion cancelled. Completed stages are retained.'):
        super().__init__('cancelled', message)
