"""Logged no-shell commands, including cancellation of silent child processes."""
import os,signal,subprocess,threading,queue,time,json
from pathlib import Path
from .errors import ConverterError,Cancelled

class _WindowsJob:
    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w
        class Basic(c.Structure):
            _fields_=[('process_time',c.c_int64),('job_time',c.c_int64),('flags',w.DWORD),
                ('min_ws',c.c_size_t),('max_ws',c.c_size_t),('active_limit',w.DWORD),
                ('affinity',c.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
        class IO(c.Structure):_fields_=[(n,c.c_uint64) for n in ('r','w','o','rb','wb','ob')]
        class Extended(c.Structure):
            _fields_=[('basic',Basic),('io',IO),('process_memory',c.c_size_t),
                ('job_memory',c.c_size_t),('peak_process',c.c_size_t),('peak_job',c.c_size_t)]
        self.k=c.WinDLL('kernel32',use_last_error=True)
        self.k.CreateJobObjectW.argtypes=[c.c_void_p,w.LPCWSTR];self.k.CreateJobObjectW.restype=w.HANDLE
        self.k.SetInformationJobObject.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD];self.k.SetInformationJobObject.restype=w.BOOL
        self.k.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];self.k.AssignProcessToJobObject.restype=w.BOOL
        self.k.CloseHandle.argtypes=[w.HANDLE];self.k.CloseHandle.restype=w.BOOL
        self.handle=self.k.CreateJobObjectW(None,None)
        if not self.handle:raise OSError(c.get_last_error(),'CreateJobObjectW')
        info=Extended();info.basic.flags=0x2000  # KILL_ON_JOB_CLOSE
        if not self.k.SetInformationJobObject(self.handle,9,c.byref(info),c.sizeof(info)):
            self.close();raise OSError(c.get_last_error(),'SetInformationJobObject')
    def assign(self,proc):
        if not self.k.AssignProcessToJobObject(self.handle,int(proc._handle)):
            raise OSError('Cannot assign converter process to its cancellation job.')
    def close(self):
        if getattr(self,'handle',None):self.k.CloseHandle(self.handle);self.handle=None

class CommandRunner:
    def __init__(self,log_path,event=None,cancel_event=None):
        self.log_path=Path(log_path);self.log_path.parent.mkdir(parents=True,exist_ok=True)
        self.event=event or (lambda v:None);self.cancel_event=cancel_event or threading.Event()
        self.lock=threading.Lock()
    def _log(self,text,label):
        with self.lock:
            with self.log_path.open('a',encoding='utf-8',newline='\n') as f:f.write(text.rstrip()+'\n')
        if text.startswith('DCRC_EVENT '):
            try:
                value=json.loads(text[len('DCRC_EVENT '):])
                progress=value.get('progress')
                if value.get('type')=='progress' and type(progress) in (int,float) and 0<=progress<=1:
                    self.event({'type':'progress','stage':str(value.get('stage',label))[:64],
                                'message':str(value.get('message',''))[:4096],'progress':progress})
                    return
            except (ValueError,AttributeError):pass
        self.event({'type':'log','stage':label,'message':text.rstrip()})
    def run(self,argv,cwd=None,env=None,label=''):
        if self.cancel_event.is_set():raise Cancelled()
        argv=[str(v) for v in argv]
        if not argv:raise ConverterError('command','An empty command cannot be run.')
        self._log('$ '+subprocess.list2cmdline(argv),label)
        # A toolchain supplies an exact sanitized environment. Re-merging the
        # parent would reintroduce GCC_EXEC_PREFIX/CPATH from another SDK.
        child_env=dict(os.environ if env is None else env)
        child_env.update(PYTHONUTF8='1',PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1')
        opts={'creationflags':subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP} if os.name=='nt' else {'start_new_session':True}
        proc=None;job=None;lines=queue.Queue();reader=None
        try:
            if os.name=='nt':job=_WindowsJob()
            proc=subprocess.Popen(argv,cwd=cwd,env=child_env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                text=True,encoding='utf-8',errors='replace',bufsize=1,**opts)
            if job:job.assign(proc)
            def pump():
                try:
                    for line in proc.stdout:lines.put(line)
                finally:lines.put(None)
            reader=threading.Thread(target=pump,daemon=True);reader.start();eof=False
            while not eof or proc.poll() is None:
                if self.cancel_event.is_set():raise Cancelled()
                try:
                    value=lines.get(timeout=.05)
                    if value is None:eof=True
                    else:self._log(value,label)
                except queue.Empty:pass
            code=proc.wait()
            if code:raise ConverterError('command_failed',f'{label or Path(argv[0]).name} failed (exit {code}).',f'Log: {self.log_path}')
        except OSError as e:
            raise ConverterError('command_start',f'Cannot run {argv[0]}: {e}',f'Log: {self.log_path}') from e
        finally:
            if job:job.close()
            if proc is not None:
                if proc.poll() is None:
                    if os.name=='nt':
                        # Exact PID belongs to this invocation; never kill by program name.
                        try:subprocess.run([str(Path(os.environ['WINDIR'])/'System32/taskkill.exe'),'/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW,timeout=3)
                        except (OSError,subprocess.TimeoutExpired):proc.kill()
                    else:
                        try:os.killpg(proc.pid,signal.SIGKILL)
                        except ProcessLookupError:pass
                    try:proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=3)
                if reader:reader.join(timeout=2)
                if proc.stdout:proc.stdout.close()
