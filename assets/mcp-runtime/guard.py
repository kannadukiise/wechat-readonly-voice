"""Defense in depth for reviewed Python code, not a native-code sandbox."""
import os, pathlib, urllib.parse, subprocess

class Guard:
    def __init__(self,scratch):self.scratch=pathlib.Path(scratch).resolve()
    def inside(self,path):
        return pathlib.Path(os.fsdecode(path)).resolve().is_relative_to(self.scratch)
    def audit(self,event,args):
        if event.startswith('socket.') or event in ('os.system','os.startfile'):
            raise PermissionError('network and shell disabled')
        if event=='subprocess.Popen':
            expected=['tasklist','/FI','IMAGENAME eq Weixin.exe','/FO','CSV','/NH']
            if args[1] not in (expected,subprocess.list2cmdline(expected)):
                raise PermissionError('subprocess disabled')
        if event=='ctypes.dlsym' and str(args[1]) in {'WriteProcessMemory','VirtualProtectEx','CreateRemoteThread','SendInput','keybd_event','mouse_event'}:
            raise PermissionError('mutation API disabled')
        if event=='open' and not isinstance(args[0],int):
            mode,flags=args[1:3]
            writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            if writing and not self.inside(args[0]):raise PermissionError('write outside scratch disabled')
        if event in ('os.remove','os.rmdir','os.mkdir') and not self.inside(args[0]):
            raise PermissionError('mutation outside scratch disabled')
        if event in ('os.rename','os.replace') and not (self.inside(args[0]) and self.inside(args[1])):
            raise PermissionError('move outside scratch disabled')
        if event=='sqlite3.connect':
            uri=str(args[0])
            if not uri.startswith('file:') or urllib.parse.parse_qs(urllib.parse.urlsplit(uri).query).get('mode')!=['ro']:
                raise PermissionError('SQLite must use mode=ro')
            path=urllib.parse.unquote(uri[5:].split('?',1)[0])
            if not self.inside(path):raise PermissionError('SQLite outside scratch disabled')
