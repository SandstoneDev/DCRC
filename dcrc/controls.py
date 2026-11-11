"""Physical PSP buttons mapped only to Dreamcast guest input."""
from .errors import ConverterError
BUTTONS = ('cross','circle','square','triangle','l','r','start','select','up','down','left','right')
ACTIONS = ('disabled','a','b','x','y','ltrigger','rtrigger','start','up','down','left','right')
DEFAULT_CONTROL_MAP = dict(zip(BUTTONS, ('a','b','x','y','ltrigger','rtrigger','start','disabled','up','down','left','right')))

def validate_control_map(mapping=None):
    if mapping is None: return DEFAULT_CONTROL_MAP.copy()
    if not isinstance(mapping,dict) or set(mapping)-set(BUTTONS):
        raise ConverterError('controls','Unknown PSP control mapping key.')
    result=DEFAULT_CONTROL_MAP.copy()
    for key,value in mapping.items():
        if not isinstance(value,str) or value not in ACTIONS:
            raise ConverterError('controls','Unknown Dreamcast control action.')
        result[key]=value
    return result

def parse_bindings(bindings):
    result={}
    for binding in bindings or []:
        key,sep,value=binding.partition('=')
        if not sep: raise ConverterError('controls','Use --control physical=action.')
        result[key]=value
    return validate_control_map(result)
