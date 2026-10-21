"""Windows child job: closing the parent-owned handle kills the DB worker."""
import ctypes
from ctypes import wintypes as W

def process_alive(pid):
    k=ctypes.WinDLL('kernel32',use_last_error=True)
    k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
    k.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD]
    k.CloseHandle.argtypes=[W.HANDLE]
    h=k.OpenProcess(0x100000,False,pid) # SYNCHRONIZE only
    if not h:return ctypes.get_last_error()!=87 # access denied => leave intact
    try:return k.WaitForSingleObject(h,0)!=0 # only confirmed termination permits cleanup
    finally:k.CloseHandle(h)

class Basic(ctypes.Structure):
    _fields_=[('per_process',ctypes.c_int64),('per_job',ctypes.c_int64),('flags',W.DWORD),
              ('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('active',W.DWORD),
              ('affinity',ctypes.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]
class IO(ctypes.Structure):
    _fields_=[(n,ctypes.c_uint64) for n in ('ro','wo','oo','rt','wt','ot')]
class Extended(ctypes.Structure):
    _fields_=[('basic',Basic),('io',IO),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),
              ('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]

class ChildJob:
    def __init__(self,pid):
        k=ctypes.WinDLL('kernel32',use_last_error=True);self.k=k;self.handle=None
        k.CreateJobObjectW.argtypes=[ctypes.c_void_p,W.LPCWSTR];k.CreateJobObjectW.restype=W.HANDLE
        k.SetInformationJobObject.argtypes=[W.HANDLE,ctypes.c_int,ctypes.c_void_p,W.DWORD]
        k.AssignProcessToJobObject.argtypes=[W.HANDLE,W.HANDLE]
        k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];k.OpenProcess.restype=W.HANDLE
        k.CloseHandle.argtypes=[W.HANDLE]
        self.handle=k.CreateJobObjectW(None,None)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        try:
            info=Extended();info.basic.flags=0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not k.SetInformationJobObject(self.handle,9,ctypes.byref(info),ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            process=k.OpenProcess(0x0100|0x0001,False,pid) # SET_QUOTA | TERMINATE, worker only
            if not process:raise ctypes.WinError(ctypes.get_last_error())
            try:
                if not k.AssignProcessToJobObject(self.handle,process):raise ctypes.WinError(ctypes.get_last_error())
            finally:k.CloseHandle(process)
        except BaseException:
            self.close();raise
    def close(self):
        if self.handle:self.k.CloseHandle(self.handle);self.handle=None
